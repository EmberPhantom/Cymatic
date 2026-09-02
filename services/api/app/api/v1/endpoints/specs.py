from datetime import datetime
import asyncio
import hashlib
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_current_user, require_creator, require_viewer
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User, UserRole
from app.core.queue import job_queue, Job, JobPriority, JobStatus
from cymatic_shared.agents.intake_agent import process_intake
from cymatic_shared.agents.clarification_agent import process_clarification_answers
from app.models.scene_package import ScenePackage
from app.services.minio_client import get_minio_client
from app.models import GenerationRun

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
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    payload_json: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class SpecGenerateRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = {}
    run_id: Optional[str] = None
    clarification_answers: Dict[str, Any] = {}


class SpecClarifyRequest(BaseModel):
    answers: Dict[str, str]
    run_id: Optional[str] = None
    current_intake: Dict[str, Any] = {}


class SpecValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    run_id: Optional[str] = None


class GenerationRunResponse(BaseModel):
    id: str
    project_id: int
    stage: str
    status: str
    progress: int
    intake: Optional[Dict[str, Any]] = None
    clarification: Dict[str, Any] = {}
    error: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScenePackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    spec_id: int
    storage_key: str
    status: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


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
    
    # Use Intake Agent and persist the result for the subsequent stages.
    intake_result = await process_intake(request.prompt, request.context)
    input_hash = hashlib.sha256(json.dumps({"prompt": request.prompt, "context": request.context}, sort_keys=True).encode()).hexdigest()
    run = GenerationRun(
        id=f"run_{uuid.uuid4().hex}", project_id=project_id,
        organization_id=project.organization_id, prompt=request.prompt,
        context_json=request.context, intake_json=intake_result.model_dump(),
        clarification_json={}, input_hash=input_hash,
        stage="clarification" if intake_result.missing_fields else "spec",
        status="needs_clarification" if intake_result.missing_fields else "ready_for_spec",
        progress=15 if intake_result.missing_fields else 25,
    )
    db.add(run)
    await db.commit()
    
    return {
        "detected_domain": intake_result.detected_domain,
        "objective": intake_result.objective,
        "missing_fields": intake_result.missing_fields,
        "suggested_questions": intake_result.suggested_questions,
        "extracted_entities": intake_result.extracted_entities,
        "confidence": intake_result.confidence,
        "run_id": run.id,
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
    
    run = None
    if request.run_id:
        run = await db.scalar(select(GenerationRun).where(
            GenerationRun.id == request.run_id,
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        ))
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
    current_answers = dict((run.clarification_json if run else {}) or {})
    current_answers.update(request.current_intake.get("extracted_entities", {}))
    
    clarification_result = await process_clarification_answers(
        domain=project.domain,
        current_answers=current_answers,
        new_answers=request.answers
    )
    
    if run:
        run.clarification_json = clarification_result.updated_fields
        run.stage = "spec" if clarification_result.ready_for_generation else "clarification"
        run.status = "ready_for_spec" if clarification_result.ready_for_generation else "needs_clarification"
        run.progress = 30 if clarification_result.ready_for_generation else 20
        await db.commit()

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
        ],
        "run_id": run.id if run else None,
    }


@router.post("/{project_id}/generate-spec", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(rate_limit("50/minute"))])
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
    
    run = None
    if request.run_id:
        run = await db.scalar(select(GenerationRun).where(
            GenerationRun.id == request.run_id,
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        ))
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
    else:
        input_hash = hashlib.sha256(json.dumps({"prompt": request.prompt, "context": request.context, "answers": request.clarification_answers}, sort_keys=True).encode()).hexdigest()
        run = await db.scalar(select(GenerationRun).where(
            GenerationRun.project_id == project_id,
            GenerationRun.input_hash == input_hash,
            GenerationRun.status.in_(["queued", "generating_spec", "validating_spec", "spec_ready", "generating_scene", "scene_ready"]),
        ).order_by(GenerationRun.created_at.desc()))
        if not run:
            run = GenerationRun(
                id=f"run_{uuid.uuid4().hex}", project_id=project_id,
                organization_id=project.organization_id, prompt=request.prompt,
                context_json=request.context, clarification_json=request.clarification_answers,
                input_hash=input_hash, stage="spec", status="queued", progress=30,
            )
            db.add(run)
        else:
            return JobResponse(job_id=f"run_{run.id}", status=run.status, message="Generation already queued", run_id=run.id)

    # Enqueue spec generation job
    job = Job(
        id=f"spec_{run.id}",
        type="generate_spec",
        payload={
            "project_id": project_id,
            "prompt": request.prompt,
            "context": request.context,
            "clarification_answers": request.clarification_answers or run.clarification_json or {},
            "run_id": run.id,
        },
        priority=JobPriority.HIGH,
    )
    
    await job_queue.enqueue(job, "spec")
    
    # Update project status
    project.status = ProjectStatus.SPEC_GENERATING
    run.status = "queued"
    run.stage = "spec"
    await db.commit()
    
    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Spec generation queued", run_id=run.id
    )


@router.get("/{project_id}/generation-runs/{run_id}", response_model=GenerationRunResponse)
async def get_generation_run(
    project_id: int,
    run_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    run = await db.scalar(select(GenerationRun).where(
        GenerationRun.id == run_id,
        GenerationRun.project_id == project_id,
        GenerationRun.organization_id == current_user.organization_id,
    ))
    if not run:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return GenerationRunResponse(
        id=run.id, project_id=run.project_id, stage=run.stage, status=run.status,
        progress=run.progress, intake=run.intake_json,
        clarification=run.clarification_json or {}, error=run.error_json,
        result=run.result_json, created_at=run.created_at, updated_at=run.updated_at,
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
        .limit(1)
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
    project = await db.scalar(select(Project).where(
        Project.id == project_id,
        Project.organization_id == current_user.organization_id,
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
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
        .limit(1)
    )
    spec = spec_result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=400, detail="No spec found. Generate a spec first.")

    if spec.status != SpecStatus.VALID:
        raise HTTPException(status_code=400, detail=f"Spec must be valid to generate scene. Current status: {spec.status.value}")

    # Enqueue scene generation job
    run = await db.scalar(select(GenerationRun).where(
        GenerationRun.project_id == project_id,
        GenerationRun.status.in_(["spec_ready", "ready_for_spec"]),
    ).order_by(GenerationRun.created_at.desc()))
    job = Job(
        id=f"scene_{project_id}_{spec.id}",
        type="generate_scene",
        payload={
            "project_id": project_id,
            "spec_id": spec.id,
            "run_id": run.id if run else None,
        },
        priority=JobPriority.HIGH,
    )

    await job_queue.enqueue(job, "generation")

    # Update project status
    project.status = ProjectStatus.SCENE_GENERATING
    if run:
        run.status = "generating_scene"
        run.stage = "scene"
        run.progress = 75
    await db.commit()

    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Scene generation queued", run_id=run.id if run else None
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
        .limit(1)
    )
    scene_pkg = pkg_result.scalar_one_or_none()
    if not scene_pkg:
        raise HTTPException(status_code=400, detail="No scene package found. Generate a scene first.")

    if scene_pkg.status != "ready":
        raise HTTPException(status_code=400, detail=f"Scene package must be ready to publish. Current status: {scene_pkg.status}")

    try:
        artifact = get_minio_client().get_object_info(scene_pkg.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Scene package artifact is unavailable") from exc
    if not artifact:
        raise HTTPException(status_code=503, detail="Scene package artifact is unavailable")

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


@router.get("/{project_id}/generation-runs", response_model=List[GenerationRunResponse])
async def list_generation_runs(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    project = await db.scalar(select(Project).where(
        Project.id == project_id,
        Project.organization_id == current_user.organization_id,
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(GenerationRun)
        .where(
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        )
        .order_by(GenerationRun.created_at.desc())
    )
    return [GenerationRunResponse(
        id=run.id, project_id=run.project_id, stage=run.stage, status=run.status,
        progress=run.progress, intake=run.intake_json,
        clarification=run.clarification_json or {}, error=run.error_json,
        result=run.result_json, created_at=run.created_at, updated_at=run.updated_at,
    ) for run in result.scalars().all()]


@router.get("/{project_id}/scene-packages", response_model=List[ScenePackageResponse])
async def list_scene_packages(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    project = await db.scalar(select(Project).where(
        Project.id == project_id,
        Project.organization_id == current_user.organization_id,
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(ScenePackage)
        .where(ScenePackage.project_id == project_id)
        .order_by(ScenePackage.created_at.desc())
    )
    return result.scalars().all()


class ClarifyWithStateRequest(BaseModel):
    answers: Dict[str, str]
    current_intake: Dict[str, Any] = {}
    run_id: Optional[str] = None


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

    if request.run_id:
        run = await db.scalar(select(GenerationRun).where(
            GenerationRun.id == request.run_id,
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        ))
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
        run.clarification_json = clarification_result.updated_fields
        run.stage = "spec" if clarification_result.ready_for_generation else "clarification"
        run.status = "ready_for_spec" if clarification_result.ready_for_generation else "needs_clarification"
        run.progress = 30 if clarification_result.ready_for_generation else 20
        await db.commit()
    
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
        ],
        "run_id": request.run_id,
    }
