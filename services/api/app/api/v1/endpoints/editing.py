from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_current_user, require_creator, require_viewer
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User, UserRole
from app.core.config import get_settings
from app.core.queue import job_queue, Job, JobPriority, JobStatus
import structlog

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()


def _ensure_manual_editing():
    if not settings.ENABLE_MANUAL_EDITING:
        raise HTTPException(status_code=403, detail="Manual editing is disabled by feature flag")


class EditOperation(BaseModel):
    operation: str  # move, rotate, delete, change_material, add_entity, duplicate
    entity_id: str
    params: Dict[str, Any]


class EditRequest(BaseModel):
    operations: List[EditOperation]


class EditResponse(BaseModel):
    success: bool
    message: str
    spec_id: Optional[int] = None
    new_version: Optional[int] = None


class EntityPatch(BaseModel):
    position: Optional[List[float]] = None
    rotation: Optional[List[float]] = None
    scale: Optional[List[float]] = None
    properties: Optional[Dict[str, Any]] = None


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
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify spec access
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id,
            SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    
    # Apply edits to spec payload
    payload = spec.payload_json.copy()
    entities = payload.get("entities", [])
    entity_map = {e["id"]: e for e in entities}
    
    for operation in request.operations:
        if operation.entity_id not in entity_map:
            raise HTTPException(status_code=404, detail=f"Entity {operation.entity_id} not found")
        
        entity = entity_map[operation.entity_id]
        
        if operation.operation == "move":
            if "position" in operation.params:
                entity["position"] = operation.params["position"]
        elif operation.operation == "rotate":
            if "rotation" in operation.params:
                entity["rotation"] = operation.params["rotation"]
        elif operation.operation == "scale":
            if "scale" in operation.params:
                entity["scale"] = operation.params["scale"]
        elif operation.operation == "change_material":
            if "material" in operation.params:
                entity.setdefault("properties", {})["material"] = operation.params["material"]
        elif operation.operation == "delete":
            entities.remove(entity)
        elif operation.operation == "duplicate":
            new_entity = entity.copy()
            new_entity["id"] = f"{entity['id']}_copy_{len(entities)}"
            if "position" in operation.params:
                new_entity["position"] = operation.params["position"]
            entities.append(new_entity)
        elif operation.operation == "add_entity":
            new_entity = {
                "id": operation.params.get("id", f"entity_{len(entities)}"),
                "type": operation.params.get("type", "entity"),
                "name": operation.params.get("name", "New Entity"),
                "position": operation.params.get("position", [0, 0, 0]),
                "rotation": operation.params.get("rotation", [0, 0, 0]),
                "scale": operation.params.get("scale", [1, 1, 1]),
                "properties": operation.params.get("properties", {}),
            }
            entities.append(new_entity)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {operation.operation}")
    
    payload["entities"] = entities
    
    # Create new spec version
    result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
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
        id=f"validate_{new_spec.id}_{int(__import__('asyncio').get_event_loop().time())}",
        type="validate_spec",
        payload={"spec_id": new_spec.id},
        priority=JobPriority.NORMAL,
    )
    await job_queue.enqueue(job, "spec")
    
    logger.info("spec_edited", project_id=project_id, spec_id=spec_id, new_spec_id=new_spec.id)
    
    return EditResponse(
        success=True,
        message="Edit applied successfully. Validation queued.",
        spec_id=new_spec.id,
        new_version=next_version,
    )


@router.patch("/{project_id}/specs/{spec_id}/entities/{entity_id}", response_model=Dict[str, Any])
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
    
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id,
            SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    
    payload = spec.payload_json.copy()
    entities = payload.get("entities", [])
    entity = next((e for e in entities if e["id"] == entity_id), None)
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    if patch.position is not None:
        entity["position"] = patch.position
    if patch.rotation is not None:
        entity["rotation"] = patch.rotation
    if patch.scale is not None:
        entity["scale"] = patch.scale
    if patch.properties is not None:
        entity["properties"] = {**entity.get("properties", {}), **patch.properties}
    
    payload["entities"] = entities
    spec.payload_json = payload
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
    
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id,
            SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    
    # Enqueue validation job
    job = Job(
        id=f"validate_{spec_id}_{int(__import__('asyncio').get_event_loop().time())}",
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
    
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id.in_([spec_id, other_spec_id]),
            SimulationSpec.project_id == project_id
        )
    )
    specs = result.scalars().all()
    
    if len(specs) != 2:
        raise HTTPException(status_code=404, detail="One or both specs not found")
    
    spec1 = next(s for s in specs if s.id == spec_id)
    spec2 = next(s for s in specs if s.id == other_spec_id)
    
    # Simple diff
    diff = {
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
            diff["entities_modified"].append({
                "id": eid,
                "old": entities1[eid],
                "new": entities2[eid]
            })
    
    return diff