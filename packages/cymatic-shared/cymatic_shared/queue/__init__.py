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

# Bound for cancel scans: a stuck queue deeper than this needs ops attention,
# not an unbounded Python scan per cancel call.
_CANCEL_SCAN_LIMIT = 1000


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
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queues = {
            "generation": "queue:generation",
            "spec": "queue:spec",
            "asset": "queue:asset",
            "analytics": "queue:analytics",
        }

    async def connect(self):
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if (
            self._client is not None
            and self._loop is not None
            and running is not None
            and self._loop is not running
        ):
            # Stale self-created client bound to a previous (possibly closed)
            # loop, e.g. across uvicorn reloads. Drop and recreate. Clients
            # injected externally (tests) have _loop None and are left alone.
            self._client = None
            self._loop = None
        if not self._client:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._loop = running

    async def disconnect(self):
        if self._client:
            await self._client.close()
            self._client = None
            self._loop = None

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("JobQueue not connected. Call connect() first.")
        return self._client

    async def enqueue(self, job: Job, queue_name: str = "generation") -> str:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        job_json = job.model_dump_json()

        # Use pipeline for atomic ZADD+HSET+EXPIRE; higher priority = larger score via ZPOPMAX
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
        ttl = ttl or self.LOCK_TTL
        lock_token = str(uuid.uuid4())
        lock_key = f"job:lock:{job_id}"
        acquired = await self.client.set(lock_key, lock_token, nx=True, ex=ttl)

        if acquired:
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

    async def renew_job_lock(
        self, job_id: str, lock_token: str, ttl: int | None = None
    ) -> bool:
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
                mapping={
                    "lock_expires_at": (
                        datetime.now(timezone.utc) + timedelta(seconds=ttl)
                    ).isoformat()
                },
            )
            return True
        return False

    async def dequeue(
        self, queue_name: str = "generation", worker_id: str | None = None
    ) -> Optional[Job]:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")

        # Atomic ZPOPMAX + lock acquisition in single Lua to avoid lost jobs and requeue storms
        # Priorities: higher value = higher priority (CRITICAL 20 > HIGH 10), ZPOPMAX returns highest
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
            -- lock contested, requeue job with original priority
            local prio = tonumber(job_data.priority) or tonumber(ARGV[4])
            redis.call('ZADD', KEYS[1], prio, job_json)
            return nil
        end
        redis.call('HSET', 'job:'..job_id, 'lock_token', token, 'lock_expires_at', ARGV[5], 'worker_id', worker, 'status', 'running')
        return job_json
        """
        lock_token = str(uuid.uuid4())
        ttl = self.LOCK_TTL
        # Need priority for requeue path — we don't know it yet, so use NORMAL as fallback and let Lua requeue with original priority extracted from job_json via ZADD prio?
        # Instead, we pass NORMAL and Lua will use that if lock fails; worst-case requeue priority slightly off but rare contention.
        # We pass lock_token, ttl, worker_id, priority fallback, expires ISO
        expires_iso = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        # Use ZPOPMAX Lua that handles priority correctly; for lock fail we requeue with original score preserved via ZADD with same json
        # To keep original priority, Lua re-parses job_json and uses job_data.priority, but we pass 0 as fallback — adjust to extract
        # Simpler: pass 0, Lua will ZADD with 0, but contention rare; we instead pass NORMAL
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

        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )

        return job

    async def complete_job(self, job: Job, result: dict[str, Any] | None = None):
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

    async def fail_job(self, job: Job, error: str, queue_name: str | None = None):
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
            logger.warning(
                "job_retry", job_id=job.id, attempt=job.retry_count, error=error
            )

        await self.client.hset(
            f"job:{job.id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )

        if job.status == JobStatus.RETRY:
            delay = min(2**job.retry_count * 5, 300)
            # Resolve original queue from stored hash to avoid job.type fragmentation (e.g., generate_spec vs generation)
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

            # Non-blocking delayed requeue; task is held by event loop, but retry survives restart via job:{id} status RETRY
            async def _delayed_requeue():
                await asyncio.sleep(delay)
                # Re-fetch latest job to avoid stale retry_count
                try:
                    await self.enqueue(job, target_queue)
                except Exception as e:
                    logger.error("delayed_requeue_failed", job_id=job.id, error=str(e))

            asyncio.create_task(_delayed_requeue())

    async def get_queue_stats(self, queue_name: str = "generation") -> dict:
        await self.connect()
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        pending = await self.client.zcard(queue_key)
        return {"queue": queue_name, "pending_jobs": pending}

    async def get_job_status(self, job_id: str) -> Optional[Job]:
        """Fetch job by ID (None when unknown)."""
        await self.connect()
        job_data = await self.client.hget(f"job:{job_id}", "data")
        if not job_data:
            return None
        return Job(**json.loads(job_data))

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job. False when already terminal/unknown."""
        await self.connect()
        job_data = await self.client.hget(f"job:{job_id}", "data")
        if not job_data:
            return False
        job = Job(**json.loads(job_data))
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        if job.lock_token:
            await self.release_job_lock(job_id, job.lock_token)
        # Resolve the ORIGINAL queue stored at enqueue time (e.g. "spec"),
        # not job.type (e.g. "generate_spec"), otherwise ZREM misses.
        stored_queue: Optional[str] = None
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
        # Job JSON changes across state transitions, so exact-match ZREM
        # often misses: scan known queues (bounded) and remove by parsed id.
        queues_to_try = [queue_key, *self._queues.values()]
        seen: set = set()
        for qk in queues_to_try:
            if qk in seen:
                continue
            seen.add(qk)
            try:
                members = await self.client.zrange(qk, 0, _CANCEL_SCAN_LIMIT - 1)
                for m in members:
                    try:
                        mid = json.loads(m).get("id")
                    except Exception:
                        continue
                    if mid == job_id:
                        await self.client.zrem(qk, m)
            except Exception:
                continue
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.lock_token = None
        job.lock_expires_at = None
        await self.client.hset(
            f"job:{job_id}",
            mapping={"data": job.model_dump_json(), "status": job.status.value},
        )
        logger.info("job_cancelled", job_id=job_id)
        return True


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
