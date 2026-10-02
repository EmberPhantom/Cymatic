"""Specs sub-router (split from specs.py, no logic change)."""

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import require_creator, require_viewer
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User
from app.core.queue import job_queue, Job, JobPriority, JobStatus
from app.models.scene_package import ScenePackage
from app.services.minio_client import get_minio_client
from app.services.scene_packages import get_latest_scene_package_json
from app.models import GenerationRun
from cymatic_shared.ids import new_job_id
from cymatic_shared.model_enums import RunStatus, RunStage
from .schemas import (
    JobResponse,
    GenerationRunResponse,
    ScenePackageResponse,
)

router = APIRouter()


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
            Project.organization_id == current_user.organization_id,
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
        raise HTTPException(
            status_code=400, detail="No spec found. Generate a spec first."
        )

    if spec.status != SpecStatus.VALID:
        raise HTTPException(
            status_code=400,
            detail=f"Spec must be valid to generate scene. Current status: {spec.status.value}",
        )

    # Enqueue scene generation job
    run = await db.scalar(
        select(GenerationRun)
        .where(
            GenerationRun.project_id == project_id,
            GenerationRun.status.in_([RunStatus.SPEC_READY, RunStatus.READY_FOR_SPEC]),
        )
        .order_by(GenerationRun.created_at.desc())
    )
    job = Job(
        id=new_job_id("scene", project_id, spec.id),
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
        run.status = RunStatus.GENERATING_SCENE
        run.stage = RunStage.SCENE
        run.progress = 75
    await db.commit()

    return JobResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
        message="Scene generation queued",
        run_id=run.id if run else None,
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
            Project.organization_id == current_user.organization_id,
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
        raise HTTPException(
            status_code=400, detail="No scene package found. Generate a scene first."
        )

    if scene_pkg.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Scene package must be ready to publish. Current status: {scene_pkg.status}",
        )

    try:
        artifact = get_minio_client().get_object_info(scene_pkg.storage_key)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Scene package artifact is unavailable"
        ) from exc
    if not artifact:
        raise HTTPException(
            status_code=503, detail="Scene package artifact is unavailable"
        )

    # Enqueue publish job
    job = Job(
        id=new_job_id("publish", project_id, int(time.monotonic())),
        type="publish_scene",
        payload={
            "project_id": project_id,
            "scene_package_id": scene_pkg.id,
        },
        priority=JobPriority.NORMAL,
    )

    await job_queue.enqueue(job, "generation")

    return JobResponse(
        job_id=job.id, status=JobStatus.QUEUED.value, message="Publish queued"
    )


@router.get("/{project_id}/generation-runs", response_model=List[GenerationRunResponse])
async def list_generation_runs(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(GenerationRun)
        .where(
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        )
        .order_by(GenerationRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return [
        GenerationRunResponse(
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
        for run in result.scalars().all()
    ]


@router.get("/{project_id}/scene-packages", response_model=List[ScenePackageResponse])
async def list_scene_packages(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(ScenePackage)
        .where(ScenePackage.project_id == project_id)
        .order_by(ScenePackage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{project_id}/scene-package/view", response_model=Dict[str, Any])
async def view_scene_package(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight read path for the mobile browser walkthrough viewer.

    Proxies the scene package JSON server-side (no presigned MinIO URL handed
    to the browser - no bucket CORS policy exists) and doesn't require
    creating a WebRTC StreamSession, unlike the Unity render-server path.
    """
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != ProjectStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Project must be published to view")

    from app.services.scene_packages import ScenePackageUnavailable

    try:
        scene_package = await get_latest_scene_package_json(db, project_id)
    except ScenePackageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Scene package temporarily unavailable"
        ) from exc
    if scene_package is None:
        raise HTTPException(status_code=404, detail="No scene package ready yet")

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "domain": project.domain,
        },
        "scene_package": scene_package,
    }
