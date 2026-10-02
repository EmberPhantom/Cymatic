"""Specs sub-router (split from specs.py, no logic change)."""

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import require_creator, require_viewer
from app.db.session import get_db
from app.models.project import Project
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User
from app.core.queue import job_queue, Job, JobPriority, JobStatus
from cymatic_shared.ids import new_job_id
from .schemas import (
    SpecResponse,
    JobResponse,
)

router = APIRouter()


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
        id=new_job_id("validate", spec.id, int(time.monotonic())),
        type="validate_spec",
        payload={"spec_id": spec.id},
        priority=JobPriority.NORMAL,
    )

    await job_queue.enqueue(job, "spec")

    spec.status = SpecStatus.VALIDATING
    await db.commit()

    return JobResponse(
        job_id=job.id, status=JobStatus.QUEUED.value, message="Spec validation queued"
    )


@router.get("/{project_id}/specs", response_model=List[SpecResponse])
async def list_specs(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(SimulationSpec)
        .where(SimulationSpec.project_id == project_id)
        .order_by(SimulationSpec.version.desc())
        .offset(skip)
        .limit(limit)
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
            SimulationSpec.id == spec_id, SimulationSpec.project_id == project_id
        )
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return spec
