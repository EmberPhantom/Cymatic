"""CYMATIC Worker - Background job processor"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.queue import job_queue, process_job, JOB_HANDLERS, Job
from app.db.session import init_db, close_db
from cymatic_shared.auth import configure_logging, verify_admin_key_dependency
import structlog
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger()
settings = get_settings()

configure_logging("worker", getattr(settings, "LOG_FORMAT", "json"))
verify_admin_key = verify_admin_key_dependency(lambda: settings.ADMIN_API_KEY or "")

worker_id = str(uuid.uuid4())[:8]
running = False
worker_task: asyncio.Task | None = None


async def worker_loop():
    """Main worker loop - processes jobs from queues.

    Intentionally SERIAL: one job at a time, one process. This process must
    be the single owner of the loop (uvicorn --workers is pinned to 1 in the
    Dockerfile; WORKER_CONCURRENCY in config is reserved/unused). N uvicorn
    processes would each run this loop over the same Redis ZPOPMAX queues —
    dequeue itself is atomic (Lua), so jobs would not be lost, but the loops
    would compete, duplicate heartbeats/lock renewals, and multiply LLM
    traffic. Scale by running more worker containers, not uvicorn fan-out.

    Consecutive job failures trip a circuit breaker (LLM_BUDGET_* settings):
    instead of spinning dequeue->fail at full rate against a downed router,
    the loop sleeps out a cooldown, giving the downstream time to recover.
    """
    global running
    running = True
    logger.info("worker_started", worker_id=worker_id)

    from cymatic_shared.agents.llm_budget import CircuitBreaker

    queues = [q.strip() for q in settings.WORKER_QUEUES.split(",")]
    failure_breaker = CircuitBreaker(
        max_consecutive_failures=int(
            getattr(settings, "LLM_BUDGET_MAX_CONSECUTIVE_FAILURES", 5)
        ),
        cooldown_seconds=float(getattr(settings, "LLM_BUDGET_COOLDOWN_S", 30.0)),
    )

    while running:
        try:
            job_processed = False

            for queue_name in queues:
                if not running:
                    break

                job = await job_queue.dequeue(queue_name, worker_id)
                if job:
                    logger.info(
                        "processing_job",
                        worker_id=worker_id,
                        job_id=job.id,
                        type=job.type,
                    )

                    async def _heartbeat(j: Job):
                        while True:
                            await asyncio.sleep(job_queue.LOCK_TTL // 2)
                            try:
                                if j.lock_token:
                                    await job_queue.renew_job_lock(j.id, j.lock_token)
                            except Exception:
                                break

                    heartbeat_task = asyncio.create_task(_heartbeat(job))
                    try:
                        result = await asyncio.wait_for(
                            process_job(job),
                            timeout=settings.WORKER_JOB_TIMEOUT_SECONDS,
                        )
                        await job_queue.complete_job(job, result)
                        failure_breaker.record_success()
                    except asyncio.TimeoutError:
                        logger.error("job_timeout", worker_id=worker_id, job_id=job.id)
                        await job_queue.fail_job(
                            job,
                            f"Job timeout after {settings.WORKER_JOB_TIMEOUT_SECONDS}s",
                            queue_name=queue_name,
                        )
                        if failure_breaker.record_failure():
                            logger.warning(
                                "worker_loop_cooling_down",
                                consecutive_failures=failure_breaker.consecutive_failures,
                                cooldown_s=failure_breaker.cooldown_seconds,
                            )
                            await asyncio.sleep(failure_breaker.cooldown_seconds)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.error(
                            "job_failed",
                            worker_id=worker_id,
                            job_id=job.id,
                            error=str(e),
                            exc_info=True,
                        )
                        await job_queue.fail_job(job, str(e), queue_name=queue_name)
                        if failure_breaker.record_failure():
                            logger.warning(
                                "worker_loop_cooling_down",
                                consecutive_failures=failure_breaker.consecutive_failures,
                                cooldown_s=failure_breaker.cooldown_seconds,
                            )
                            await asyncio.sleep(failure_breaker.cooldown_seconds)
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

                    job_processed = True
                    break

            if not job_processed:
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(
                "worker_error", worker_id=worker_id, error=str(e), exc_info=True
            )
            await asyncio.sleep(5)

    logger.info("worker_stopped", worker_id=worker_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task
    await init_db()
    await job_queue.connect()

    # Crash recovery: re-enqueue jobs left in RETRY whose retry_at passed
    # (the process may have died during fail_job's delayed-requeue sleep).
    try:
        recovered = await job_queue.sweep_stale_retries()
        if recovered:
            logger.info("stale_retries_recovered", count=recovered)
    except Exception as sweep_exc:  # noqa: BLE001
        logger.error("stale_retry_sweep_failed", error=str(sweep_exc))

    worker_task = asyncio.create_task(worker_loop())

    yield

    global running
    running = False
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await job_queue.disconnect()
    await close_db()


app = FastAPI(
    title="CYMATIC Worker",
    version="0.1.0",
    description="Background job worker for CYMATIC",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "worker",
        "worker_id": worker_id,
        "running": running,
        "registered_handlers": list(JOB_HANDLERS.keys()),
    }


@app.get("/metrics")
async def metrics(_admin: None = Depends(verify_admin_key)):
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {"name": "CYMATIC Worker", "version": "0.1.0"}


@app.get("/stats")
async def worker_stats(_admin: None = Depends(verify_admin_key)):
    """Get worker and queue statistics (admin only)."""
    stats: dict[str, Any] = {"worker_id": worker_id, "running": running, "queues": {}}
    queues = stats["queues"]
    for queue_name in settings.WORKER_QUEUES.split(","):
        queue_name = queue_name.strip()
        queues[queue_name] = await job_queue.get_queue_stats(queue_name)
    return stats


from app.tasks import generation  # noqa: F401, E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
