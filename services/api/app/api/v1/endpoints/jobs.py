from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import require_viewer
from app.core.queue import job_queue
from app.models.user import User

router = APIRouter()


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(require_viewer),
):
    """Get job status by ID.

    Returns the frontend JobStatus shape {job_id,status,message,result,error,
    progress} plus run_id when the job payload carries one, so the builder
    can poll either jobs or generation-runs without field mismatches.
    """
    job = await job_queue.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
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
    payload = job.payload if isinstance(job.payload, dict) else {}
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
    current_user: User = Depends(require_viewer),
):
    """Cancel a queued or running job (called by the builder Cancel button)"""
    cancelled = await job_queue.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="Job not found or already in a terminal state",
        )
    return {"job_id": job_id, "status": "cancelled"}
