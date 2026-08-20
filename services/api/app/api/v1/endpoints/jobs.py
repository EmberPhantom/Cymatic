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
    """Get job status by ID"""
    job = await job_queue.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
