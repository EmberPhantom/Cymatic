"""Specs sub-router (split from specs.py, no logic change)."""
import copy
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import get_settings
from app.core.dependencies import require_creator, require_viewer
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.core.queue import job_queue, Job, JobPriority, JobStatus
from app.models import GenerationRun
from cymatic_shared.ids import new_run_id
from cymatic_shared.model_enums import RunStatus, RunStage
from .schemas import (
    SpecGenerateRequest, JobResponse, GenerationRunResponse,
)

settings = get_settings()

router = APIRouter()

@router.post(
    "/{project_id}/generate-spec",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_GENERATE))],
)
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
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run = None
    if request.run_id:
        run = await db.scalar(
            select(GenerationRun).where(
                GenerationRun.id == request.run_id,
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == current_user.organization_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
    else:
        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "prompt": request.prompt,
                    "context": request.context,
                    "answers": request.clarification_answers,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        run = await db.scalar(
            select(GenerationRun)
            .where(
                GenerationRun.project_id == project_id,
                GenerationRun.input_hash == input_hash,
                GenerationRun.status.in_(
                    [
                        RunStatus.QUEUED,
                        RunStatus.GENERATING_SPEC,
                        RunStatus.VALIDATING_SPEC,
                        RunStatus.SPEC_READY,
                        RunStatus.GENERATING_SCENE,
                        RunStatus.SCENE_READY,
                    ]
                ),
            )
            .order_by(GenerationRun.created_at.desc())
        )
        if not run:
            run = GenerationRun(
                id=new_run_id(),
                project_id=project_id,
                organization_id=project.organization_id,
                prompt=request.prompt,
                context_json=copy.deepcopy(request.context) if request.context else {},
                clarification_json=copy.deepcopy(request.clarification_answers)
                if request.clarification_answers
                else {},
                input_hash=input_hash,
                stage="spec",
                status=RunStatus.QUEUED,
                progress=30,
            )
            db.add(run)
        else:
            return JobResponse(
                job_id=f"spec_{run.id}",
                status=run.status,
                message="Generation already queued",
                run_id=run.id,
            )

    # Enqueue spec generation job - deep copy to prevent mutation and ensure job_id matches
    job = Job(
        id=f"spec_{run.id}",
        type="generate_spec",
        payload={
            "project_id": project_id,
            "prompt": request.prompt,
            "context": copy.deepcopy(request.context) if request.context else {},
            "clarification_answers": copy.deepcopy(request.clarification_answers)
            if request.clarification_answers
            else copy.deepcopy(run.clarification_json)
            if run.clarification_json
            else {},
            "run_id": run.id,
        },
        priority=JobPriority.HIGH,
    )

    await job_queue.enqueue(job, "spec")

    # Update project status
    project.status = ProjectStatus.SPEC_GENERATING
    run.status = RunStatus.QUEUED
    run.stage = RunStage.SPEC
    await db.commit()

    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Spec generation queued",
        run_id=run.id,
    )


@router.get(
    "/{project_id}/generation-runs/{run_id}", response_model=GenerationRunResponse
)
async def get_generation_run(
    project_id: int,
    run_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    run = await db.scalar(
        select(GenerationRun).where(
            GenerationRun.id == run_id,
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return GenerationRunResponse(
        id=run.id,
        project_id=run.project_id,
        stage=run.stage,
        status=run.status,
        progress=run.progress,
        intake=run.intake_json,
        clarification=run.clarification_json or {},
        error=run.error_json,
        result=run.result_json,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


