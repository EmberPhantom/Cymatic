import asyncio
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
from app.core.queue import job_queue, Job, JobPriority, JobStatus
from cymatic_shared.agents.intake_agent import process_intake
from cymatic_shared.agents.clarification_agent import process_clarification_answers
from app.models.scene_package import ScenePackage

router = APIRouter()


class SpecPayload(BaseModel):
    """Base simulation specification payload"""
    domain: str
    metadata: Dict[str, Any] = {}
    entities: List[Dict[str, Any]] = []
    navigation: Dict[str, Any] = {}
    lighting: Dict[str, Any] = {}
    copilot_policy: Dict[str, Any] = {}
    performance_budget: Dict[str, Any] = {}


class SpecCreate(BaseModel):
    payload_json: SpecPayload


class SpecUpdate(BaseModel):
    payload_json: Optional[SpecPayload] = None
    status: Optional[str] = None


class SpecResponse(BaseModel):
    id: int
    project_id: int
    version: int
    payload_json: Dict[str, Any]
    status: str
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class SpecGenerateRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = {}


class SpecClarifyRequest(BaseModel):
    answers: Dict[str, str]


class SpecValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("/{project_id}/intake", response_model=Dict[str, Any])
async def intake_prompt(
    project_id: int,
    request: SpecGenerateRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Parse initial prompt and detect domain/missing fields using Intake Agent"""
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
    
    # Use Intake Agent
    intake_result = process_intake(request.prompt, request.context)
    
    return {
        "detected_domain": intake_result.detected_domain,
        "objective": intake_result.objective,
        "missing_fields": intake_result.missing_fields,
        "suggested_questions": intake_result.suggested_questions,
        "extracted_entities": intake_result.extracted_entities,
        "confidence": intake_result.confidence
    }


@router.post("/{project_id}/clarify", response_model=Dict[str, Any])
async def clarify_requirements(
    project_id: int,
    request: SpecClarifyRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Process clarification answers using Clarification Agent"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get current intake state from request (client should send it)
    # For now, we'll use the project domain and empty current answers
    # In practice, frontend would maintain intake state
    
    clarification_result = await process_clarification_answers(
        domain=project.domain,
        current_answers={},  # Frontend should provide this
        new_answers=request.answers
    )
    
    return {
        "updated_fields": clarification_result.updated_fields,
        "ready_for_generation": clarification_result.ready_for_generation,
        "completion_percentage": clarification_result.completion_percentage,
        "remaining_questions": [
            {
                "field": q.field,
                "question": q.question,
                "type": q.type,
                "options": q.options,
                "required": q.required
            }
            for q in clarification_result.questions
        ]
    }


@router.post("/{project_id}/generate-spec", response_model=JobResponse)
async def generate_spec(
    project_id: int,
    request: SpecGenerateRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Generate structured simulation specification from prompt (async job)"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enqueue spec generation job
    job = Job(
        id=f"spec_{project_id}_{int(asyncio.get_event_loop().time())}",
        type="generate_spec",
        payload={
            "project_id": project_id,
            "prompt": request.prompt,
            "context": request.context,
        },
        priority=JobPriority.HIGH,
    )
    
    await job_queue.enqueue(job, "spec")
    
    # Update project status
    project.status = ProjectStatus.SPEC_GENERATING
    await db.commit()
    
    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Spec generation queued"
    )


@router.post("/{project_id}/validate-spec", response_model=JobResponse)
async def validate_spec(
    project_id: int,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Validate the latest spec for the project (async job)"""
    result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="No spec found for project")
    
    # Enqueue validation job
    job = Job(
        id=f"validate_{spec.id}_{int(asyncio.get_event_loop().time())}",
        type="validate_spec",
        payload={"spec_id": spec.id},
        priority=JobPriority.NORMAL,
    )
    
    await job_queue.enqueue(job, "spec")
    
    spec.status = SpecStatus.VALIDATING
    await db.commit()
    
    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Spec validation queued"
    )


@router.get("/{project_id}/specs", response_model=List[SpecResponse])
async def list_specs(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}/specs/{spec_id}", response_model=SpecResponse)
async def get_spec(
    project_id: int,
    spec_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SimulationSpec).where(
            SimulationSpec.id == spec_id,
            SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    return spec


@router.post("/{project_id}/generate-scene", response_model=JobResponse)
async def generate_scene(
    project_id: int,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Generate scene package from the latest valid spec (async job)"""
    # Verify project exists and user has access
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get latest spec
    spec_result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
    )
    spec = spec_result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=400, detail="No spec found. Generate a spec first.")

    if spec.status != SpecStatus.VALID:
        raise HTTPException(status_code=400, detail=f"Spec must be valid to generate scene. Current status: {spec.status.value}")

    # Enqueue scene generation job
    job = Job(
        id=f"scene_{project_id}_{int(asyncio.get_event_loop().time())}",
        type="generate_scene",
        payload={
            "project_id": project_id,
            "spec_id": spec.id,
        },
        priority=JobPriority.HIGH,
    )

    await job_queue.enqueue(job, "generation")

    # Update project status
    project.status = ProjectStatus.SCENE_GENERATING
    await db.commit()

    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Scene generation queued"
    )


@router.post("/{project_id}/publish", response_model=JobResponse)
async def publish_scene(
    project_id: int,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Publish a generated scene package for streaming (async job)"""
    # Verify project
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get scene package
    pkg_result = await db.execute(
        select(ScenePackage)
        .where(ScenePackage.project_id == project_id)
        .order_by(ScenePackage.created_at.desc())
    )
    scene_pkg = pkg_result.scalar_one_or_none()
    if not scene_pkg:
        raise HTTPException(status_code=400, detail="No scene package found. Generate a scene first.")

    if scene_pkg.status != "ready":
        raise HTTPException(status_code=400, detail=f"Scene package must be ready to publish. Current status: {scene_pkg.status}")

    # Enqueue publish job
    job = Job(
        id=f"publish_{project_id}_{int(asyncio.get_event_loop().time())}",
        type="publish_scene",
        payload={
            "project_id": project_id,
            "scene_package_id": scene_pkg.id,
        },
        priority=JobPriority.NORMAL,
    )

    await job_queue.enqueue(job, "generation")

    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Publish queued"
    )


class ClarifyWithStateRequest(BaseModel):
    answers: Dict[str, str]
    current_intake: Dict[str, Any] = {}


@router.post("/{project_id}/clarify-with-state", response_model=Dict[str, Any])
async def clarify_with_state(
    project_id: int,
    request: ClarifyWithStateRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Process clarification with full intake state"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Use Clarification Agent with full state
    clarification_result = await process_clarification_answers(
        domain=project.domain,
        current_answers=request.current_intake.get("extracted_entities", {}),
        new_answers=request.answers
    )
    
    return {
        "updated_fields": clarification_result.updated_fields,
        "ready_for_generation": clarification_result.ready_for_generation,
        "completion_percentage": clarification_result.completion_percentage,
        "remaining_questions": [
            {
                "field": q.field,
                "question": q.question,
                "type": q.type,
                "options": q.options,
                "required": q.required
            }
            for q in clarification_result.questions
        ]
    }