"""Worker scene task handlers (split from tasks/generation.py, no logic change)."""
import structlog

from datetime import datetime, timezone
from app.core.queue import register_job_handler
from cymatic_shared.models import Project, ProjectStatus
from cymatic_shared.models import SimulationSpec as SimulationSpecModel, SpecStatus
from cymatic_shared.models import ScenePackage as ScenePackageModel
from cymatic_shared.schemas.simulation_spec import SimulationSpec as SimulationSpecSchema
from app.agents.scene_package import ScenePackage as ScenePackageSchema, scene_package_to_json
from app.services.minio_client import get_minio_client
from typing import Any

from sqlalchemy import select, text
import hashlib
from minio.error import S3Error
from cymatic_shared.models import GenerationRun
from cymatic_shared.model_enums import RunStatus, RunStage

# DB sessions resolve via the generation package namespace so tests
# can patch app.tasks.generation.AsyncSessionLocal.
from app.tasks import generation as _gen

logger = structlog.get_logger()


@register_job_handler("generate_scene")
async def generate_scene_task(payload: dict) -> dict:
    """Generate 3D scene package from validated spec using Scene Package Generator."""
    project_id = payload.get("project_id")
    spec_id = payload.get("spec_id")
    run_id = payload.get("run_id")
    
    logger.info("generate_scene_started", project_id=project_id, spec_id=spec_id)
    
    async with _gen.AsyncSessionLocal() as db:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        
        spec_result = await db.execute(select(SimulationSpecModel).where(SimulationSpecModel.id == spec_id))
        spec = spec_result.scalar_one_or_none()
        
        if not project or not spec or spec.project_id != project_id:
            raise ValueError("Project or spec not found")
        if spec.status != SpecStatus.VALID:
            raise ValueError("Scene generation requires a valid specification")

        # Idempotency: check for existing ready package first (HIGH: 219 idempotency)
        # Use advisory lock to avoid race where two workers both see no existing and insert duplicate
        try:
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(spec_id) * 100000 + int(project_id) % 100000})
        except Exception:
            pass
        existing = await db.scalar(select(ScenePackageModel).where(
            ScenePackageModel.project_id == project_id,
            ScenePackageModel.spec_id == spec_id,
            ScenePackageModel.status == "ready",
        ).order_by(ScenePackageModel.created_at.desc()))
        if existing:
            project.status = ProjectStatus.SCENE_READY
            if run_id:
                run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
                if run:
                    run.status = RunStatus.SCENE_READY
                    run.stage = RunStage.ARTIFACT_VERIFICATION
                    run.progress = 100
                    run.result_json = {"scene_package_id": existing.id, "storage_key": existing.storage_key}
            await db.commit()
            return {"scene_package_id": existing.id, "storage_key": existing.storage_key, "idempotent": True}
        
        project.status = ProjectStatus.SCENE_GENERATING
        if run_id:
            run = await db.scalar(select(GenerationRun).where(
                GenerationRun.id == run_id, GenerationRun.project_id == project_id
            ))
            if run:
                run.status = RunStatus.GENERATING_SCENE
                run.stage = RunStage.SCENE
                run.progress = 70
        await db.commit()
        
        # Generate scene package using our generator
        from app.agents.scene_package import generate_scene_package
        from app.agents.asset_agent import select_assets

        # Select assets first - ensure entities are proper Entity objects (HIGH: 258 dict vs Entity)
        raw_payload = spec.payload_json if isinstance(spec.payload_json, dict) else {}
        raw_entities = raw_payload.get("entities", []) if isinstance(raw_payload, dict) else []
        spec_entities: list[Any] = []
        try:
            from cymatic_shared.schemas.simulation_spec import Entity as EntitySchema
            for e in raw_entities:
                if isinstance(e, EntitySchema):
                    spec_entities.append(e)
                elif isinstance(e, dict):
                    try:
                        spec_entities.append(EntitySchema(**e))
                    except Exception:
                        # Skip malformed entity but log; fallback to raw for robustness
                        logger.warning("entity_parse_skipped", entity=e.get("id", "unknown"))
                        continue
                else:
                    # Unexpected type, skip
                    continue
            # If all entities failed to parse and we had raw, fallback to raw dict handling via select_assets duck typing
            if not spec_entities and raw_entities:
                logger.warning("all_entities_parse_failed_fallback_raw", count=len(raw_entities))
                # Keep raw for next attempt but filter to dicts
                spec_entities = [e for e in raw_entities if isinstance(e, dict)]  # type: ignore[assignment]
        except Exception as parse_err:  # noqa: BLE001
            logger.warning("entity_conversion_failed", error=str(parse_err))
            spec_entities = raw_entities  # type: ignore[assignment]
        asset_result = select_assets(
            spec_entities=spec_entities,  # type: ignore[arg-type]
            domain=project.domain,
            performance_budget=raw_payload.get("performance_budget", {}) if isinstance(raw_payload, dict) else {},
        )

        # Generate scene package with validated SimulationSpec
        validated_spec = SimulationSpecSchema.model_validate(raw_payload) if isinstance(raw_payload, dict) else SimulationSpecSchema(**raw_payload)
        scene_package = generate_scene_package(
            spec=validated_spec,
            spec_version=spec.version,
            asset_manifest=asset_result.manifest.model_dump() if asset_result else {}
        )

        # Validate the renderer-neutral package before storage (HIGH: 272 model_validate).
        # Use class-level validate to avoid instance-method confusion.
        ScenePackageSchema.model_validate(scene_package.model_dump())
        # Serialize to JSON
        scene_json = scene_package_to_json(scene_package)
        checksum = hashlib.sha256(scene_json.encode("utf-8")).hexdigest()
        
        # Upload to MinIO
        storage_key = f"orgs/{project.organization_id}/projects/{project_id}/scenes/spec_{spec_id}_v{spec.version}.cymatic"
        
        try:
            get_minio_client().upload_data(
                object_name=storage_key,
                data=scene_json.encode('utf-8'),
                content_type="application/json",
                metadata={
                    "project_id": str(project_id),
                    "spec_id": str(spec_id),
                    "domain": project.domain,
                    "format": "cymatic_v1",
                    "sha256": checksum,
                }
            )
            logger.info("scene_package_uploaded", storage_key=storage_key)
        except S3Error as e:
            logger.error("minio_upload_failed", error=str(e))
            raise
        
        # Confirm the object is readable before exposing it as ready (HIGH: 299 get_object_info missing)
        try:
            object_info = get_minio_client().get_object_info(storage_key)
        except AttributeError:
            # Fallback if client lacks method (should not happen after fix)
            object_info = None
            if get_minio_client().object_exists(storage_key):
                object_info = {"size": len(scene_json.encode("utf-8"))}
        if not object_info or int(object_info.get("size", 0)) != len(scene_json.encode("utf-8")):
            raise ValueError("Scene package artifact verification failed")

        # Create DB record
        scene_package_record = ScenePackageModel(
            project_id=project_id,
            spec_id=spec_id,
            storage_key=storage_key,
            status="ready",
            metadata_json={
                "format": "cymatic_v1",
                "spec_version": spec.version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "entity_count": len(scene_package.entities),
                "navigation_points": len(scene_package.navigation.points),
                "sha256": checksum,
                "size": len(scene_json.encode("utf-8")),
                "verified": True,
            }
        )
        db.add(scene_package_record)
        
        project.status = ProjectStatus.SCENE_READY
        if run_id:
            run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
            if run:
                run.status = RunStatus.SCENE_READY
                run.stage = RunStage.ARTIFACT_VERIFICATION
                run.progress = 95
                run.result_json = {"scene_package_id": scene_package_record.id, "storage_key": storage_key, "sha256": checksum}
        await db.commit()
        await db.refresh(scene_package_record)
        
        logger.info("generate_scene_completed", project_id=project_id, scene_package_id=scene_package_record.id)
        
        return {"scene_package_id": scene_package_record.id, "storage_key": storage_key}


@register_job_handler("publish_scene")
async def publish_scene_task(payload: dict) -> dict:
    """Publish scene package for streaming with precondition checks."""
    project_id = payload.get("project_id")
    scene_package_id = payload.get("scene_package_id")

    logger.info("publish_scene_started", project_id=project_id, scene_package_id=scene_package_id)

    if not project_id or not scene_package_id:
        raise ValueError("Both project_id and scene_package_id are required")

    async with _gen.AsyncSessionLocal() as db:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        scene_result = await db.execute(
            select(ScenePackageModel).where(
                ScenePackageModel.id == scene_package_id,
                ScenePackageModel.project_id == project_id,
            )
        )
        scene_pkg = scene_result.scalar_one_or_none()
        if not scene_pkg:
            raise ValueError(
                f"Scene package {scene_package_id} not found or does not belong to project {project_id}"
            )

        if scene_pkg.status != "ready":
            raise ValueError(
                f"Scene package status is '{scene_pkg.status}', must be 'ready' to publish"
            )

        spec_result = await db.execute(
            select(SimulationSpecModel).where(SimulationSpecModel.id == scene_pkg.spec_id)
        )
        spec = spec_result.scalar_one_or_none()
        if not spec or spec.status not in (SpecStatus.VALID,):
            raise ValueError("Referenced spec is missing or not valid")

        try:
            artifact = get_minio_client().get_object_info(scene_pkg.storage_key)
        except (S3Error, OSError) as exc:
            raise ValueError("Scene package artifact is unavailable") from exc
        if not artifact:
            raise ValueError("Scene package artifact is unavailable")

        project.status = ProjectStatus.PUBLISHED
        await db.commit()

        logger.info("publish_scene_completed", project_id=project_id, scene_package_id=scene_package_id)

        return {"project_id": project_id, "scene_package_id": scene_package_id, "status": "published"}


