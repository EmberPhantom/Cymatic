from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import require_viewer, require_creator
from app.core.queue import job_queue
from app.db.session import get_db
from app.models.project import Project
from app.models.simulation_spec import SimulationSpec
from app.models.asset import Asset
from app.models.user import User

router = APIRouter()


async def _assert_job_ownership(job_payload: dict, current_user: User, db: AsyncSession) -> None:
    """Fail-closed ownership check: job must belong to caller's org.

    Jobs carry project_id, spec_id, or asset_id. Resolve to project org;
    deny when unresolvable or cross-org to prevent IDOR poll/cancel.
    """
    if not isinstance(job_payload, dict):
        raise HTTPException(status_code=404, detail="Job not found")
    project_id = job_payload.get("project_id")
    project = None
    if project_id is not None:
        project = await db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == current_user.organization_id,
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return
    spec_id = job_payload.get("spec_id")
    if spec_id is not None:
        spec = await db.scalar(
            select(SimulationSpec).where(SimulationSpec.id == spec_id)
        )
        if spec is None:
            raise HTTPException(status_code=404, detail="Job not found")
        project = await db.scalar(
            select(Project).where(
                Project.id == spec.project_id,
                Project.organization_id == current_user.organization_id,
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return
    asset_id = job_payload.get("asset_id")
    if asset_id is not None:
        asset = await db.scalar(select(Asset).where(Asset.id == asset_id))
        if asset is None or asset.organization_id != current_user.organization_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return
    # No resolvable scope (e.g., legacy job): deny to avoid cross-tenant leak.
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Get job status by ID.

    Returns the frontend JobStatus shape {job_id,status,message,result,error,
    progress} plus run_id when the job payload carries one, so the builder
    can poll either jobs or generation-runs without field mismatches.
    """
    job = await job_queue.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = job.payload if isinstance(job.payload, dict) else {}
    await _assert_job_ownership(payload, current_user, db)
    status = job.status.value if hasattr(job.status, "value") else str(job.status)
    progress_map = {
        "pending": 5,
        "queued": 10,
        "running": 50,
        "retry": 30,
        "completed": 100,
        "failed": 100,
        "cancelled": 100,
    }
    message_map = {
        "pending": "Job pending",
        "queued": "Job queued",
        "running": "Job running",
        "retry": f"Job retrying (attempt {job.retry_count})",
        "completed": "Job completed",
        "failed": job.error or "Job failed",
        "cancelled": "Job cancelled",
    }
    return {
        "job_id": job.id,
        "job_type": job.type,
        "status": status,
        "message": message_map.get(status, status),
        "result": job.result,
        "error": job.error,
        "progress": progress_map.get(status, 0),
        "retry_count": job.retry_count,
        "run_id": payload.get("run_id"),
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or running job (called by the builder Cancel button)"""
    existing = await job_queue.get_job_status(job_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Job not found or already in a terminal state",
        )
    await _assert_job_ownership(
        existing.payload if isinstance(existing.payload, dict) else {},
        current_user,
        db,
    )
    cancelled = await job_queue.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="Job not found or already in a terminal state",
        )
    return {"job_id": job_id, "status": "cancelled"}
