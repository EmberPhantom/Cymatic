"""CYMATIC Worker - Background job processor"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.queue import job_queue, process_job, JOB_HANDLERS
from app.db.session import init_db, close_db
import structlog

logger = structlog.get_logger()
settings = get_settings()

worker_id = str(uuid.uuid4())[:8]
running = False
worker_task: asyncio.Task | None = None


def verify_admin_key(x_api_key: str = Header(None)):
    """Simple API key check for admin endpoints."""
    if not settings.ADMIN_API_KEY:
        return
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")


async def worker_loop():
    """Main worker loop - processes jobs from queues."""
    global running
    running = True
    logger.info("worker_started", worker_id=worker_id)

    queues = [q.strip() for q in settings.WORKER_QUEUES.split(",")]

    while running:
        try:
            job_processed = False

            for queue_name in queues:
                if not running:
                    break

                job = await job_queue.dequeue(queue_name, worker_id)
                if job:
                    logger.info("processing_job", worker_id=worker_id, job_id=job.id, type=job.type)
                    try:
                        result = await process_job(job)
                        await job_queue.complete_job(job, result)
                    except Exception as e:
                        logger.error("job_failed", worker_id=worker_id, job_id=job.id, error=str(e))
                        await job_queue.fail_job(job, str(e))

                    job_processed = True
                    break

            if not job_processed:
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("worker_error", worker_id=worker_id, error=str(e))
            await asyncio.sleep(5)

    logger.info("worker_stopped", worker_id=worker_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task
    await init_db()
    await job_queue.connect()

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


@app.get("/")
async def root():
    return {"name": "CYMATIC Worker", "version": "0.1.0"}


@app.get("/stats")
async def worker_stats(_admin: None = Depends(verify_admin_key)):
    """Get worker and queue statistics (admin only)."""
    stats = {"worker_id": worker_id, "running": running, "queues": {}}
    for queue_name in settings.WORKER_QUEUES.split(","):
        queue_name = queue_name.strip()
        stats["queues"][queue_name] = await job_queue.get_queue_stats(queue_name)
    return stats


from app.tasks import generation  # noqa: F401


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
