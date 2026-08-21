"""Worker Tasks - Background job implementations using pipelines"""
from datetime import datetime
from app.core.queue import register_job_handler, Job, JobPriority, JobStatus
from app.db.session import AsyncSessionLocal
from cymatic_shared.models import Project, ProjectStatus
from cymatic_shared.models import SimulationSpec, SpecStatus
from cymatic_shared.models import Asset, AssetStatus
from cymatic_shared.models import ScenePackage as ScenePackageModel
from app.agents.scene_package import generate_scene_package, ScenePackage, scene_package_to_json
from app.services.minio_client import get_minio_client
from sqlalchemy import select, func
import structlog
import asyncio
import json
from minio.error import S3Error

logger = structlog.get_logger()


@register_job_handler("generate_spec")
async def generate_spec_task(payload: dict) -> dict:
    """Generate simulation specification from prompt using pipeline."""
    project_id = payload.get("project_id")
    prompt = payload.get("prompt")
    context = payload.get("context", {})
    clarification_answers = payload.get("clarification_answers", {})
    
    logger.info("generate_spec_started", project_id=project_id)
    
    async with AsyncSessionLocal() as db:
        # Get project with row lock to prevent concurrent version assignment
        result = await db.execute(
            select(Project)
            .where(Project.id == project_id)
            .with_for_update()  # Lock the project row
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Update project status
        project.status = ProjectStatus.SPEC_GENERATING
        await db.commit()
    
    # Run appropriate pipeline based on domain
    if project.domain == "real_estate":
        from app.pipelines.real_estate import generate_real_estate_spec
        pipeline_result = await generate_real_estate_spec(
            project_id=project_id,
            prompt=prompt,
            context=context,
            clarification_answers=clarification_answers
        )
    elif project.domain == "heritage":
        from app.pipelines.heritage import generate_heritage_spec
        pipeline_result = await generate_heritage_spec(
            project_id=project_id,
            prompt=prompt,
            context=context,
            clarification_answers=clarification_answers
        )
    else:
        raise ValueError(f"Unknown domain: {project.domain}")
    
    # Handle pipeline result
    if pipeline_result.status == "awaiting_clarification":
        # Return clarification questions
        return {
            "status": "awaiting_clarification",
            "questions": [q.model_dump() for q in pipeline_result.clarification.questions] if pipeline_result.clarification else [],
            "current_answers": pipeline_result.clarification.updated_fields if pipeline_result.clarification else {},
            "completion": pipeline_result.clarification.completion_percentage if pipeline_result.clarification else 0
        }
    
    if pipeline_result.status != "completed" or not pipeline_result.spec:
        raise ValueError(f"Pipeline failed: {pipeline_result.error}")
    
    # Save spec to database with atomic version assignment
    async with AsyncSessionLocal() as db:
        spec = pipeline_result.spec
        
        # Get next version atomically using subquery with FOR UPDATE
        # This ensures atomic version assignment even under concurrent load
        result = await db.execute(
            select(func.coalesce(func.max(SimulationSpec.version), 0) + 1)
            .where(SimulationSpec.project_id == project_id)
            .with_for_update()  # Lock the version assignment
        )
        next_version = result.scalar_one()
        
        # Create spec record
        db_spec = SimulationSpec(
            project_id=project_id,
            version=next_version,
            payload_json=spec.model_dump(),
            status=SpecStatus.VALID,
        )
        db.add(db_spec)
        
        # Update project status
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.SPEC_READY
        
        await db.commit()
        await db.refresh(db_spec)
        
        logger.info("generate_spec_completed", project_id=project_id, spec_id=db_spec.id, version=db_spec.version)
        
        return {
            "spec_id": db_spec.id,
            "version": db_spec.version,
            "pipeline_details": {
                "intake": pipeline_result.intake.model_dump() if pipeline_result.intake else None,
                "research": pipeline_result.research.model_dump() if pipeline_result.research else None,
                "domain_check_score": pipeline_result.domain_check.compliance_score if pipeline_result.domain_check else None,
                "validation_score": pipeline_result.validation.spec_score if pipeline_result.validation else None,
            }
        }


@register_job_handler("validate_spec")
async def validate_spec_task(payload: dict) -> dict:
    """Validate simulation specification using validation agent."""
    spec_id = payload.get("spec_id")
    
    logger.info("validate_spec_started", spec_id=spec_id)
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SimulationSpec).where(SimulationSpec.id == spec_id))
        spec = result.scalar_one_or_none()
        if not spec:
            raise ValueError(f"Spec {spec_id} not found")
        
        spec.status = SpecStatus.VALIDATING
        await db.commit()
        
        # Run validation agent
        from app.agents.validation_agent import validate_simulation_spec
        validation_result = validate_simulation_spec(spec.payload_json)
        
        spec.status = SpecStatus.VALID if validation_result.valid else SpecStatus.INVALID
        await db.commit()
        
        logger.info("validate_spec_completed", spec_id=spec_id, valid=validation_result.valid, score=validation_result.spec_score)
        
        return validation_result.model_dump()


@register_job_handler("generate_scene")
async def generate_scene_task(payload: dict) -> dict:
    """Generate 3D scene package from validated spec using Scene Package Generator."""
    project_id = payload.get("project_id")
    spec_id = payload.get("spec_id")
    
    logger.info("generate_scene_started", project_id=project_id, spec_id=spec_id)
    
    async with AsyncSessionLocal() as db:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        
        spec_result = await db.execute(select(SimulationSpec).where(SimulationSpec.id == spec_id))
        spec = spec_result.scalar_one_or_none()
        
        if not project or not spec:
            raise ValueError("Project or spec not found")
        
        project.status = ProjectStatus.SCENE_GENERATING
        await db.commit()
        
        # Generate scene package using our generator
        from app.agents.scene_package import generate_scene_package
        from app.agents.asset_agent import select_assets
        
        # Select assets first
        asset_result = select_assets(
            spec_entities=spec.payload_json.get("entities", []),
            domain=project.domain,
            performance_budget=spec.payload_json.get("performance_budget", {})
        )
        
        # Generate scene package
        scene_package = generate_scene_package(
            spec=SimulationSpec(**spec.payload_json),
            spec_version=spec.version,
            asset_manifest=asset_result.manifest.model_dump() if asset_result else {}
        )
        
        # Serialize to JSON
        scene_json = scene_package_to_json(scene_package)
        
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
                }
            )
            logger.info("scene_package_uploaded", storage_key=storage_key)
        except S3Error as e:
            logger.error("minio_upload_failed", error=str(e))
            raise
        
        # Create DB record
        scene_package_record = ScenePackageModel(
            project_id=project_id,
            spec_id=spec_id,
            storage_key=storage_key,
            status="ready",
            metadata_json={
                "format": "cymatic_v1",
                "spec_version": spec.version,
                "generated_at": datetime.utcnow().isoformat(),
                "entity_count": len(scene_package.entities),
                "navigation_points": len(scene_package.navigation.points),
            }
        )
        db.add(scene_package_record)
        
        project.status = ProjectStatus.SCENE_READY
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

    async with AsyncSessionLocal() as db:
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
            select(SimulationSpec).where(SimulationSpec.id == scene_pkg.spec_id)
        )
        spec = spec_result.scalar_one_or_none()
        if not spec or spec.status not in (SpecStatus.VALID,):
            raise ValueError("Referenced spec is missing or not valid")

        project.status = ProjectStatus.PUBLISHED
        await db.commit()

        logger.info("publish_scene_completed", project_id=project_id, scene_package_id=scene_package_id)

        return {"project_id": project_id, "scene_package_id": scene_package_id, "status": "published"}


@register_job_handler("process_asset")
async def process_asset_task(payload: dict) -> dict:
    """Process uploaded asset based on type: extract metadata from MinIO, validate, mark ready."""
    asset_id = payload.get("asset_id")

    logger.info("process_asset_started", asset_id=asset_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()

        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        asset.status = AssetStatus.PROCESSING
        asset.metadata_json = asset.metadata_json or {}
        await db.commit()

        asset_type = asset.type.value if hasattr(asset.type, "value") else str(asset.type)
        file_ext = asset.filename.rsplit(".", 1)[-1].lower() if asset.filename and "." in asset.filename else "unknown"

        try:
            info = get_minio_client().get_object_info(asset.storage_key)

            asset.metadata_json["processed"] = True
            asset.metadata_json["size"] = info.get("size")
            asset.metadata_json["etag"] = info.get("etag")
            asset.metadata_json["content_type"] = info.get("content_type")
            asset.metadata_json["format"] = file_ext

            if asset_type == "image":
                asset.metadata_json["note"] = "Image metadata extracted; thumbnail generation requires Pillow (not yet available)"

            elif asset_type == "model_3d":
                asset.metadata_json["note"] = "3D model metadata extracted; LOD generation requires mesh processing (not yet available)"

            elif asset_type == "audio":
                asset.metadata_json["note"] = "Audio stored as-is for MVP"

            else:
                asset.metadata_json["note"] = f"No specific processing for type '{asset_type}'"

            asset.status = AssetStatus.READY
            await db.commit()

            logger.info("process_asset_completed", asset_id=asset_id, asset_type=asset_type, size=info.get("size"))
            return {"asset_id": asset_id, "status": "ready", "type": asset_type, "size": info.get("size")}

        except (S3Error, OSError) as e:
            asset.status = AssetStatus.FAILED
            asset.metadata_json["error"] = str(e)
            await db.commit()
            logger.error("process_asset_failed", asset_id=asset_id, error=str(e))
            raise


@register_job_handler("analytics_aggregation")
async def analytics_aggregation_task(payload: dict) -> dict:
    """Aggregate analytics data for a project: session counts, event totals, durations."""
    project_id = payload.get("project_id")

    logger.info("analytics_aggregation_started", project_id=project_id)

    from cymatic_shared.models import StreamSession, StreamSessionStatus
    from cymatic_shared.models import RuntimeEvent

    async with AsyncSessionLocal() as db:
        sessions_result = await db.execute(
            select(StreamSession).where(StreamSession.project_id == project_id)
        )
        sessions = sessions_result.scalars().all()

        total_sessions = len(sessions)
        active_sessions = sum(1 for s in sessions if s.status == StreamSessionStatus.ACTIVE)
        completed_sessions = sum(1 for s in sessions if s.status == StreamSessionStatus.DISCONNECTED)

        total_duration_seconds = 0.0
        for s in sessions:
            if s.started_at and s.ended_at:
                total_duration_seconds += (s.ended_at - s.started_at).total_seconds()

        session_ids = [s.id for s in sessions]
        if session_ids:
            events_result = await db.execute(
                select(RuntimeEvent).where(RuntimeEvent.session_id.in_(session_ids))
            )
            events = events_result.scalars().all()
        else:
            events = []

        event_counts = {}
        total_events = len(events)
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        aggregated = {
            "project_id": project_id,
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "total_duration_seconds": round(total_duration_seconds, 2),
            "total_events": total_events,
            "event_counts_by_type": event_counts,
        }

        logger.info("analytics_aggregation_completed", project_id=project_id, total_sessions=total_sessions, total_events=total_events)

        return aggregated