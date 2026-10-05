"""Worker queue - configured instance from shared package."""

from cymatic_shared.queue import (  # noqa: F401
    Job,
    JobStatus,
    JobPriority,
    JobQueue,
    JOB_HANDLERS,
    register_job_handler,
    process_job,
)
from app.core.config import get_settings

settings = get_settings()
job_queue = JobQueue(redis_url=settings.REDIS_URL)
