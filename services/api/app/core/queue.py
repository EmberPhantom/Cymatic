"""Job Queue Infrastructure - Redis-based task queue with distributed locking"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from enum import Enum
from pydantic import BaseModel, Field
import redis.asyncio as redis
from app.core.config import get_settings
import structlog
import uuid

logger = structlog.get_logger()
settings = get_settings()


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
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    worker_id: str | None = None
    # For distributed locking
    lock_token: str | None = None
    lock_expires_at: datetime | None = None


class JobQueue:
    """Redis-based job queue with priority support and distributed locking."""

    # Lock TTL for running jobs (seconds)
    LOCK_TTL = 300  # 5 minutes

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: redis.Redis | None = None
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
        """Add job to queue with priority."""
        await self.connect()

        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        job_json = job.model_dump_json()

        async with self.client.pipeline(transaction=True) as pipe:
            pipe.zadd(queue_key, {job_json: job.priority.value})
            pipe.hset(
                f"job:{job.id}",
                mapping={
                    "data": job_json,
                    "status": job.status.value,
                    "queue": queue_name,
                },
            )
            pipe.expire(f"job:{job.id}", 604800)
            await pipe.execute()

        logger.info(
            "job_enqueued", job_id=job.id, queue=queue_name, priority=job.priority.name
        )
        return job.id

    async def acquire_job_lock(
        self, job_id: str, worker_id: str, ttl: int | None = None
    ) -> str | None:
        """Acquire distributed lock for job processing."""
        ttl = ttl or self.LOCK_TTL
        lock_token = str(uuid.uuid4())

        lock_key = f"job:lock:{job_id}"
        # Use SET NX EX for atomic lock acquisition
        acquired = await self.client.set(lock_key, lock_token, nx=True, ex=ttl)

        if acquired:
            # Store lock token in job data
            await self.client.hset(
                f"job:{job_id}",
                mapping={
                    "lock_token": lock_token,
                    "lock_expires_at": (
                        datetime.now(timezone.utc) + timedelta(seconds=ttl)
                    ).isoformat(),
                    "worker_id": worker_id,
                },
            )
            return lock_token
        return None

    async def release_job_lock(self, job_id: str, lock_token: str) -> bool:
        """Release distributed lock for job."""
        lock_key = f"job:lock:{job_id}"

        # Lua script for atomic lock release (only if token matches)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        result = await self.client.eval(lua_script, 1, lock_key, lock_token)
        return result == 1

    async def renew_job_lock(
        self, job_id: str, lock_token: str, ttl: int | None = None
    ) -> bool:
        """Renew distributed lock for job processing."""
        ttl = ttl or self.LOCK_TTL
        lock_key = f"job:lock:{job_id}"

        # Lua script for atomic lock renewal (only if token matches)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("EXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.client.eval(lua_script, 1, lock_key, lock_token, ttl)
        return result == 1

    async def dequeue(
        self, queue_name: str = "generation", worker_id: str | None = None
    ) -> Job | None:
        """Get highest priority job from queue with distributed locking."""
        await self.connect()

        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")

        # Atomic ZPOPMAX + lock acquisition to avoid lost jobs and requeue storms
        lua_script = """
        local res = redis.call('ZPOPMAX', KEYS[1], 1)
        if not res or #res == 0 then
            return nil
        end
        local job_json = res[1]
        local job_data = cjson.decode(job_json)
        local job_id = job_data.id
        local lock_key = 'job:lock:' .. job_id
        local token = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local worker = ARGV[3]
        local acquired = redis.call('SET', lock_key, token, 'NX', 'EX', ttl)
        if not acquired then
            local prio = tonumber(job_data.priority) or tonumber(ARGV[4])
            redis.call('ZADD', KEYS[1], prio, job_json)
            return nil
        end
        redis.call('HSET', 'job:'..job_id, 'lock_token', token, 'lock_expires_at', ARGV[5], 'worker_id', worker, 'status', 'running')
        return job_json
        """
        lock_token = str(uuid.uuid4())
        ttl = self.LOCK_TTL
        expires_iso = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        result = await self.client.eval(
            lua_script,
            1,
            queue_key,
            lock_token,
            str(ttl),
            worker_id or "unknown",
            str(JobPriority.NORMAL.value),
            expires_iso,
        )

        if not result:
            return None

        job_data = json.loads(result)
        job = Job(**job_data)

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = worker_id
        job.updated_at = datetime.now(timezone.utc)
        job.lock_token = lock_token
        job.lock_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        # Update job status with lock info
        await self.client.hset(
            f"job:{job.id}",
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            },
        )

        return job

    async def complete_job(self, job: Job, result: dict[str, Any] | None = None) -> None:
        """Mark job as completed and release lock."""
        await self.connect()

        # Release lock
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
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            },
        )

        logger.info("job_completed", job_id=job.id)

    async def fail_job(self, job: Job, error: str, queue_name: str | None = None) -> None:
        """Mark job as failed, handle retries with lock release."""
        await self.connect()

        # Release lock
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
            logger.warning(
                "job_retry", job_id=job.id, attempt=job.retry_count, error=error
            )

        await self.client.hset(
            f"job:{job.id}",
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            },
        )

        if job.status == JobStatus.RETRY:
            # Non-blocking delayed requeue; resolve original queue to avoid fragmentation
            import asyncio

            delay = min(2**job.retry_count * 5, 300)  # max 5 minutes
            stored_queue: str | None = queue_name
            if not stored_queue:
                try:
                    raw = await self.client.hget(f"job:{job.id}", "queue")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    stored_queue = raw
                except Exception:
                    stored_queue = None
            target_queue = stored_queue or job.type

            async def _delayed_requeue():
                await asyncio.sleep(delay)
                try:
                    await self.enqueue(job, target_queue)
                except Exception as e:
                    logger.error("delayed_requeue_failed", job_id=job.id, error=str(e))

            asyncio.create_task(_delayed_requeue())

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job."""
        await self.connect()

        # Check job status
        job_data = await self.client.hget(f"job:{job_id}", "data")
        if not job_data:
            return False

        job = Job(**json.loads(job_data))

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        # Release lock if running
        if job.lock_token:
            await self.release_job_lock(job_id, job.lock_token)

        # Remove from queue if queued — resolve the ORIGINAL queue name stored
        # at enqueue time (e.g. "spec"), not job.type (e.g. "generate_spec"),
        # otherwise ZREM misses and cancel appears to work while worker runs on.
        stored_queue: str | None = None
        try:
            raw = await self.client.hget(f"job:{job_id}", "queue")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            stored_queue = raw
        except Exception:
            stored_queue = None
        queue_key = self._queues.get(
            stored_queue or "", f"queue:{stored_queue or job.type}"
        )
        # Best-effort removal from all known queues: job JSON changes across
        # state transitions (status/retries), so exact-match ZREM often misses.
        # Scan known queues and remove any member whose parsed id matches.
        removed = 0
        queues_to_try = [queue_key, *self._queues.values()]
        seen_keys: set[str] = set()
        for qk in queues_to_try:
            if qk in seen_keys:
                continue
            seen_keys.add(qk)
            try:
                members = await self.client.zrange(qk, 0, -1)
                for m in members:
                    try:
                        mid = json.loads(m).get("id")
                    except Exception:
                        continue
                    if mid == job_id:
                        await self.client.zrem(qk, m)
                        removed += 1
            except Exception:
                continue
        if removed == 0:
            # Fallback: exact-match attempt for legacy payloads
            await self.client.zrem(queue_key, job.model_dump_json())

        # Mark as cancelled
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.lock_token = None
        job.lock_expires_at = None

        await self.client.hset(
            f"job:{job_id}",
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            },
        )

        logger.info("job_cancelled", job_id=job_id)
        return True

    async def cleanup_stale_locks(self, max_age_seconds: int = 3600) -> int:
        """Clean up stale locks (jobs that have been running too long)."""
        await self.connect()

        # Scan for job locks
        pattern = "job:lock:*"
        cleaned = 0

        async for key in self.client.scan_iter(match=pattern):
            lock_token = await self.client.get(key)
            if not lock_token:
                continue

            key_str: str = key if isinstance(key, str) else key.decode("utf-8")
            job_id = key_str.split(":")[-1]
            job_data = await self.client.hget(f"job:{job_id}", "data")
            if not job_data:
                await self.client.delete(key_str)
                cleaned += 1
                continue

            job = Job(**json.loads(job_data))
            if job.lock_expires_at and datetime.now(timezone.utc) > job.lock_expires_at:
                # Lock expired, release it
                token_str: str = lock_token if isinstance(lock_token, str) else lock_token.decode("utf-8")
                await self.release_job_lock(job_id, token_str)
                cleaned += 1
                logger.warning("cleaned_stale_lock", job_id=job_id)

        return cleaned

    async def get_job_status(self, job_id: str) -> Job | None:
        """Get job status by ID."""
        await self.connect()

        job_data = await self.client.hget(f"job:{job_id}", "data")
        if not job_data:
            return None

        return Job(**json.loads(job_data))

    async def get_queue_stats(self, queue_name: str = "generation") -> dict[str, Any]:
        """Get queue statistics."""
        await self.connect()

        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        pending = await self.client.zcard(queue_key)

        return {
            "queue": queue_name,
            "pending_jobs": pending,
        }


# Global job queue instance
job_queue = JobQueue()


# Job type registry for workers
JOB_HANDLERS: dict[str, Callable] = {}


def register_job_handler(job_type: str):
    """Decorator to register job handlers."""

    def decorator(func: Callable):
        JOB_HANDLERS[job_type] = func
        return func

    return decorator


async def process_job(job: Job) -> dict[str, Any]:
    """Process a job using registered handlers."""
    handler = JOB_HANDLERS.get(job.type)
    if not handler:
        raise ValueError(f"No handler registered for job type: {job.type}")

    return await handler(job.payload)
