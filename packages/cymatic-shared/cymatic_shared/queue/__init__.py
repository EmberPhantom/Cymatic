"""Shared job queue infrastructure - Redis-based task queue."""
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from enum import Enum
from pydantic import BaseModel, Field
import redis.asyncio as redis
import structlog
import uuid

logger = structlog.get_logger()


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class Job(BaseModel):
    id: str
    type: str
    payload: dict
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    result: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    lock_token: Optional[str] = None
    lock_expires_at: Optional[datetime] = None


class JobQueue:
    """Redis-based job queue with priority support and distributed locking."""

    LOCK_TTL = 300

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._queues = {
            "generation": "queue:generation",
            "spec": "queue:spec",
            "asset": "queue:asset",
            "analytics": "queue:analytics",
        }

    async def connect(self):
        if not self._client:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

    async def disconnect(self):
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("JobQueue not connected. Call connect() first.")
        return self._client

    async def enqueue(self, job: Job, queue_name: str = "generation") -> str:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        job_json = job.model_dump_json()

        await self.client.zadd(queue_key, {job_json: job.priority.value})
        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job_json, "status": job.status.value, "queue": queue_name},
        )
        await self.client.expire(f"job:{job.id}", 604800)

        logger.info("job_enqueued", job_id=job.id, queue=queue_name, priority=job.priority.name)
        return job.id

    async def acquire_job_lock(self, job_id: str, worker_id: str, ttl: int = None) -> bool:
        ttl = ttl or self.LOCK_TTL
        lock_token = str(uuid.uuid4())
        lock_key = f"job:lock:{job_id}"
        acquired = await self.client.set(lock_key, lock_token, nx=True, ex=ttl)

        if acquired:
            await self.client.hset(
                f"job:{job_id}",
                mapping={
                    "lock_token": lock_token,
                    "lock_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
                    "worker_id": worker_id,
                },
            )
            return True
        return False

    async def release_job_lock(self, job_id: str, lock_token: str) -> bool:
        lock_key = f"job:lock:{job_id}"
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        result = await self.client.eval(lua_script, 1, lock_key, lock_token)
        return result == 1

    async def renew_job_lock(self, job_id: str, lock_token: str, ttl: int = None) -> bool:
        ttl = ttl or self.LOCK_TTL
        lock_key = f"job:lock:{job_id}"
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("EXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.client.eval(lua_script, 1, lock_key, lock_token, str(ttl))
        if result == 1:
            await self.client.hset(
                f"job:{job_id}",
                mapping={"lock_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()},
            )
            return True
        return False

    async def dequeue(self, queue_name: str = "generation", worker_id: str = None) -> Optional[Job]:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")

        lua_script = """
        local job = redis.call('ZPOPMIN', KEYS[1])
        if job then
            return job[1]
        end
        return nil
        """
        result = await self.client.eval(lua_script, 1, queue_key)

        if not result:
            return None

        job_data = json.loads(result)
        job = Job(**job_data)

        lock_acquired = await self.acquire_job_lock(job.id, worker_id or "unknown")
        if not lock_acquired:
            await self.enqueue(job, queue_name)
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = worker_id
        job.updated_at = datetime.now(timezone.utc)
        job.lock_expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.LOCK_TTL)
        # Track the actual lock token so complete/fail can release it
        job.lock_token = await self.client.get(f"job:lock:{job.id}")

        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )

        return job

    async def complete_job(self, job: Job, result: dict = None):
        await self.connect()
        if job.lock_token:
            await self.release_job_lock(job.id, job.lock_token)

        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        job.lock_token = None
        job.lock_expires_at = None

        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )
        logger.info("job_completed", job_id=job.id)

    async def fail_job(self, job: Job, error: str, queue_name: str = None):
        await self.connect()
        if job.lock_token:
            await self.release_job_lock(job.id, job.lock_token)

        job.retry_count += 1
        job.error = error
        job.updated_at = datetime.now(timezone.utc)
        job.lock_token = None
        job.lock_expires_at = None

        if job.retry_count >= job.max_retries:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            logger.error("job_failed_max_retries", job_id=job.id, error=error)
        else:
            job.status = JobStatus.RETRY
            logger.warning("job_retry", job_id=job.id, attempt=job.retry_count, error=error)

        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )

        if job.status == JobStatus.RETRY:
            delay = min(2 ** job.retry_count * 5, 300)
            # Non-blocking delayed requeue
            async def _delayed_requeue():
                await asyncio.sleep(delay)
                await self.enqueue(job, queue_name or job.type)
            asyncio.create_task(_delayed_requeue())

    async def get_queue_stats(self, queue_name: str = "generation") -> dict:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        pending = await self.client.zcard(queue_key)
        return {"queue": queue_name, "pending_jobs": pending}


JOB_HANDLERS: dict[str, Callable] = {}


def register_job_handler(job_type: str):
    """Decorator to register job handlers."""
    def decorator(func: Callable):
        JOB_HANDLERS[job_type] = func
        return func
    return decorator


async def process_job(job: Job) -> dict:
    """Process a job using registered handlers."""
    handler = JOB_HANDLERS.get(job.type)
    if not handler:
        raise ValueError(f"No handler registered for job type: {job.type}")
    return await handler(job.payload)
