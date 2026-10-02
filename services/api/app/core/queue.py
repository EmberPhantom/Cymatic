"""Job queue - re-exported from shared package.

Single source: cymatic_shared.queue (cancel/sweep/status helpers were
ported here from the former api fork). The process-local singleton keeps
the api's configured REDIS_URL.
"""

from cymatic_shared.queue import (  # noqa: F401
    Job,
    JobPriority,
    JobQueue,
    JobStatus,
    JOB_HANDLERS,
    process_job,
    register_job_handler,
)
from app.core.config import get_settings

job_queue = JobQueue(get_settings().REDIS_URL)
