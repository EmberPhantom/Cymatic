from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import require_creator, require_viewer
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User
from app.core.config import get_settings
from app.core.queue import job_queue, Job, JobPriority
import copy
import time
from sqlalchemy.orm.attributes import flag_modified
import structlog

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()


def _ensure_manual_editing():
    if not settings.ENABLE_MANUAL_EDITING:
        raise HTTPException(
            status_code=403, detail="Manual editing is disabled by feature flag"
        )


async def _require_org_project(
    db: AsyncSession, project_id: int, organization_id: int
) -> Project:
    """404 unless the project belongs to the caller's organization."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


class EditOperation(BaseModel):
    operation: Literal[
        "move",
        "rotate",
        "scale",
        "change_material",
        "add_entity",
        "duplicate",
        "delete",
    ]
    entity_id: str = Field(min_length=1, max_length=128)
    params: Dict[str, Any] = Field(default_factory=dict, max_length=50)


class EditRequest(BaseModel):
    operations: List[EditOperation] = Field(min_length=1, max_length=50)


class EditResponse(BaseModel):
    success: bool
    message: str
    spec_id: Optional[int] = None
    new_version: Optional[int] = None


class EntityPatch(BaseModel):
    position: Optional[List[float]] = Field(default=None, min_length=3, max_length=3)
    rotation: Optional[List[float]] = Field(default=None, min_length=3, max_length=3)
    scale: Optional[List[float]] = Field(default=None, min_length=3, max_length=3)
    properties: Optional[Dict[str, Any]] = Field(default=None, max_length=50)

    @classmethod
    def _check_finite(
        cls, values: Optional[List[float]], name: str
    ) -> Optional[List[float]]:
        if values is None:
            return values
        import math

        for v in values:
            if not math.isfinite(v) or abs(v) > 1e6:
                raise ValueError(f"{name} must be finite within ±1e6")
        return values

    @field_validator("position", "rotation", "scale")
    @classmethod
    def _validate_vec(cls, v: Optional[List[float]], info) -> Optional[List[float]]:
        return cls._check_finite(v, info.field_name)


@router.post("/{project_id}/specs/{spec_id}/edit", response_model=EditResponse)
async def edit_spec(
    project_id: int,
    spec_id: int,
    request: EditRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Apply edit operations to a simulation specification"""
    _ensure_manual_editing()

    # Verify project access
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify spec access
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id, SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")

    # Apply edits to spec payload (deepcopy to avoid shallow mutation)
    payload = copy.deepcopy(spec.payload_json)
    entities = payload.get("entities", [])
    entity_map = {e["id"]: e for e in entities}

    for operation in request.operations:
        # add_entity is allowed when entity_id == "new" or when not in map - handle before existence check
        if operation.operation == "add_entity":
            allowed_types = {
                "room",
                "wall",
                "floor",
                "ceiling",
                "door",
                "window",
                "furniture",
                "decoration",
                "light",
                "navigation_point",
                "poi",
                "audio_zone",
                "trigger_zone",
            }
            req_type = str(operation.params.get("type", "furniture"))
            if req_type not in allowed_types:
                raise HTTPException(
                    status_code=400, detail=f"Invalid entity type: {req_type}"
                )
            new_entity = {
                "id": operation.params.get("id", f"entity_{len(entities)}"),
                "type": req_type,
                "name": operation.params.get("name", "New Entity"),
                "position": copy.deepcopy(operation.params.get("position", [0, 0, 0])),
                "rotation": copy.deepcopy(operation.params.get("rotation", [0, 0, 0])),
                "scale": copy.deepcopy(operation.params.get("scale", [1, 1, 1])),
                "properties": copy.deepcopy(operation.params.get("properties", {})),
            }
            if new_entity["id"] in entity_map:
                new_entity["id"] = f"{new_entity['id']}_{len(entities)}"
            entities.append(new_entity)
            entity_map[new_entity["id"]] = new_entity
            continue

        if operation.entity_id not in entity_map:
            raise HTTPException(
                status_code=404, detail=f"Entity {operation.entity_id} not found"
            )

        entity = entity_map[operation.entity_id]

        if operation.operation == "move":
            if "position" in operation.params:
                entity["position"] = copy.deepcopy(operation.params["position"])
        elif operation.operation == "rotate":
            if "rotation" in operation.params:
                entity["rotation"] = copy.deepcopy(operation.params["rotation"])
        elif operation.operation == "scale":
            if "scale" in operation.params:
                entity["scale"] = copy.deepcopy(operation.params["scale"])
        elif operation.operation == "change_material":
            if "material" in operation.params:
                entity.setdefault("properties", {})["material"] = copy.deepcopy(
                    operation.params["material"]
                )
        elif operation.operation == "delete":
            entities.remove(entity)
            # keep map consistent
            entity_map.pop(operation.entity_id, None)
            # Prune dangling navigation references to deleted entity.
            nav = payload.get("navigation", {})
            for key in ("points", "paths"):
                items = nav.get(key)
                if isinstance(items, list):
                    nav[key] = [
                        it
                        for it in items
                        if it != operation.entity_id
                        and not (
                            isinstance(it, dict) and it.get("id") == operation.entity_id
                        )
                        and not (
                            isinstance(it, dict)
                            and operation.entity_id
                            in (
                                it.get("from"),
                                it.get("to"),
                                it.get("from_point"),
                                it.get("to_point"),
                            )
                        )
                    ]
        elif operation.operation == "duplicate":
            new_entity = copy.deepcopy(entity)
            new_entity["id"] = f"{entity['id']}_copy_{len(entities)}"
            if "position" in operation.params:
                new_entity["position"] = copy.deepcopy(operation.params["position"])
            entities.append(new_entity)
            entity_map[new_entity["id"]] = new_entity
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown operation: {operation.operation}"
            )

    payload["entities"] = entities

    # Spec-first: synchronously validate the mutated payload before persisting.
    # Async worker re-validation still runs, but invalid edits are rejected here.
    try:
        from app.services.spec_validator import validate_spec as _validate_sync

        _vresult = _validate_sync(payload)
        if not _vresult.valid:
            first = _vresult.errors[0].to_dict() if _vresult.errors else {}
            raise HTTPException(
                status_code=400,
                detail=f"Edit produces invalid spec: {first.get('message', 'validation failed')}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("edit_sync_validation_failed", error=str(e))

    # Create new spec version
    result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
        .limit(1)
    )
    last_spec = result.scalar_one_or_none()
    next_version = (last_spec.version + 1) if last_spec else 1

    new_spec = SimulationSpec(
        project_id=project_id,
        version=next_version,
        payload_json=payload,
        status=SpecStatus.DRAFT,
    )
    db.add(new_spec)

    # Update project status
    project.status = ProjectStatus.SPEC_GENERATING
    await db.commit()
    await db.refresh(new_spec)

    # Enqueue validation job
    job = Job(
        id=f"validate_{new_spec.id}_{int(time.monotonic())}",
        type="validate_spec",
        payload={"spec_id": new_spec.id},
        priority=JobPriority.NORMAL,
    )
    await job_queue.enqueue(job, "spec")

    logger.info(
        "spec_edited", project_id=project_id, spec_id=spec_id, new_spec_id=new_spec.id
    )

    return EditResponse(
        success=True,
        message="Edit applied successfully. Validation queued.",
        spec_id=new_spec.id,
        new_version=next_version,
    )


@router.patch(
    "/{project_id}/specs/{spec_id}/entities/{entity_id}", response_model=Dict[str, Any]
)
async def patch_entity(
    project_id: int,
    spec_id: int,
    entity_id: str,
    patch: EntityPatch,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Patch a single entity in the spec"""
    _ensure_manual_editing()
    await _require_org_project(db, project_id, current_user.organization_id)

    # Validate patch shapes before mutating stored state (spec-first:
    # never persist untrusted DRAFT without a schema check).
    for vec_field, vec in (
        ("position", patch.position),
        ("rotation", patch.rotation),
        ("scale", patch.scale),
    ):
        if vec is not None:
            if (
                not isinstance(vec, (list, tuple))
                or len(vec) != 3
                or not all(isinstance(v, (int, float)) for v in vec)
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"{vec_field} must be [x, y, z] numbers",
                )
    if patch.properties is not None and not isinstance(patch.properties, dict):
        raise HTTPException(status_code=422, detail="properties must be an object")

    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id, SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")

    payload = copy.deepcopy(spec.payload_json)
    entities = payload.get("entities", [])
    entity = next((e for e in entities if e["id"] == entity_id), None)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if patch.position is not None:
        entity["position"] = copy.deepcopy(patch.position)
    if patch.rotation is not None:
        entity["rotation"] = copy.deepcopy(patch.rotation)
    if patch.scale is not None:
        entity["scale"] = copy.deepcopy(patch.scale)
    if patch.properties is not None:
        entity["properties"] = {
            **entity.get("properties", {}),
            **copy.deepcopy(patch.properties),
        }

    payload["entities"] = entities
    spec.payload_json = payload
    flag_modified(spec, "payload_json")
    spec.status = SpecStatus.DRAFT

    await db.commit()

    return {"success": True, "entity": entity}


@router.post("/{project_id}/specs/{spec_id}/validate", response_model=Dict[str, Any])
async def validate_spec_edits(
    project_id: int,
    spec_id: int,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Validate a spec after edits"""
    _ensure_manual_editing()
    await _require_org_project(db, project_id, current_user.organization_id)

    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id, SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")

    # Enqueue validation job
    job = Job(
        id=f"validate_{spec_id}_{int(time.monotonic())}",
        type="validate_spec",
        payload={"spec_id": spec_id},
        priority=JobPriority.HIGH,
    )
    await job_queue.enqueue(job, "spec")

    spec.status = SpecStatus.VALIDATING
    await db.commit()

    return {"success": True, "message": "Validation queued", "job_id": job.id}


@router.get("/{project_id}/specs/{spec_id}/diff/{other_spec_id}")
async def diff_specs(
    project_id: int,
    spec_id: int,
    other_spec_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Compare two spec versions"""
    _ensure_manual_editing()
    await _require_org_project(db, project_id, current_user.organization_id)

    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id.in_([spec_id, other_spec_id]),
            SimulationSpec.project_id == project_id,
        )
    )
    specs = result.scalars().all()

    if len(specs) != 2:
        raise HTTPException(status_code=404, detail="One or both specs not found")

    spec1 = next(s for s in specs if s.id == spec_id)
    spec2 = next(s for s in specs if s.id == other_spec_id)

    # Simple diff
    diff: dict[str, Any] = {
        "spec_a": {"id": spec1.id, "version": spec1.version},
        "spec_b": {"id": spec2.id, "version": spec2.version},
        "entities_added": [],
        "entities_removed": [],
        "entities_modified": [],
    }

    entities1 = {e["id"]: e for e in spec1.payload_json.get("entities", [])}
    entities2 = {e["id"]: e for e in spec2.payload_json.get("entities", [])}

    all_ids = set(entities1.keys()) | set(entities2.keys())

    for eid in all_ids:
        if eid in entities1 and eid not in entities2:
            diff["entities_removed"].append({"id": eid, "entity": entities1[eid]})
        elif eid not in entities1 and eid in entities2:
            diff["entities_added"].append({"id": eid, "entity": entities2[eid]})
        elif entities1[eid] != entities2[eid]:
            diff["entities_modified"].append(
                {"id": eid, "old": entities1[eid], "new": entities2[eid]}
            )

    return diff
