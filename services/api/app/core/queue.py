"""Job Queue Infrastructure - Redis-based task queue with distributed locking"""
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
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
    # For distributed locking
    lock_token: Optional[str] = None
    lock_expires_at: Optional[datetime] = None


class JobQueue:
    """Redis-based job queue with priority support and distributed locking."""
    
    # Lock TTL for running jobs (seconds)
    LOCK_TTL = 300  # 5 minutes
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
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
        """Add job to queue with priority."""
        await self.connect()
        
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        job_json = job.model_dump_json()
        
        # Use sorted set for priority queue (score = -priority for max-heap behavior)
        await self.client.zadd(
            queue_key,
            {job_json: -job.priority.value}
        )
        
        # Store job details in hash for quick lookup
        await self.client.hset(
            f"job:{job.id}",
            mapping={
                "data": job_json,
                "status": job.status.value,
                "queue": queue_name,
            }
        )
        
        # Set TTL for job data (7 days)
        await self.client.expire(f"job:{job.id}", 604800)
        
        logger.info("job_enqueued", job_id=job.id, queue=queue_name, priority=job.priority.name)
        return job.id
    
    async def acquire_job_lock(self, job_id: str, worker_id: str, ttl: int = None) -> bool:
        """Acquire distributed lock for job processing."""
        ttl = ttl or self.LOCK_TTL
        lock_token = str(uuid.uuid4())
        
        lock_key = f"job:lock:{job_id}"
        # Use SET NX EX for atomic lock acquisition
        acquired = await self.client.set(
            lock_key,
            lock_token,
            nx=True,
            ex=ttl
        )
        
        if acquired:
            # Store lock token in job data
            await self.client.hset(
                f"job:{job_id}",
                mapping={
                    "lock_token": lock_token,
                    "lock_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
                    "worker_id": worker_id,
                }
            )
            return True
        return False
    
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
    
    async def renew_job_lock(self, job_id: str, lock_token: str, ttl: int = None) -> bool:
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
    
    async def dequeue(self, queue_name: str = "generation", worker_id: str = None) -> Optional[Job]:
        """Get highest priority job from queue with distributed locking."""
        await self.connect()
        
        queue_key = self._queues.get(queue_name, f"queue:{queue_name}")
        
        # Use Lua script for atomic pop and lock acquisition
        lua_script = """
        local job = redis.call('ZPOPMAX', KEYS[1])
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
        
        # Try to acquire lock for this job
        lock_acquired = await self.acquire_job_lock(job.id, worker_id or "unknown")
        if not lock_acquired:
            # Re-queue the job if we couldn't get the lock
            await self.enqueue(job, queue_name)
            return None
        
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = worker_id
        job.updated_at = datetime.now(timezone.utc)
        job.lock_token = job.lock_token  # Will be set by acquire_job_lock
        job.lock_expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.LOCK_TTL)
        
        # Update job status with lock info
        await self.client.hset(
            f"job:{job.id}",
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            }
        )
        
        return job
    
    async def complete_job(self, job: Job, result: dict = None):
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
            }
        )
        
        logger.info("job_completed", job_id=job.id)
    
    async def fail_job(self, job: Job, error: str):
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
            logger.warning("job_retry", job_id=job.id, attempt=job.retry_count, error=error)
        
        await self.client.hset(
            f"job:{job.id}",
            mapping={
                "data": job.model_dump_json(),
                "status": job.status.value,
            }
        )
        
        if job.status == JobStatus.RETRY:
            # Re-queue after delay (exponential backoff)
            import asyncio
            delay = min(2 ** job.retry_count * 5, 300)  # max 5 minutes
            await asyncio.sleep(delay)
            await self.enqueue(job, job.type)
    
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
        
        # Remove from queue if queued
        queue_key = self._queues.get(job.type, f"queue:{job.type}")
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
            }
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
            
            job_id = key.split(":")[-1]
            job_data = await self.client.hget(f"job:{job_id}", "data")
            if not job_data:
                await self.client.delete(key)
                cleaned += 1
                continue
            
            job = Job(**json.loads(job_data))
            if job.lock_expires_at and datetime.now(timezone.utc) > job.lock_expires_at:
                # Lock expired, release it
                await self.release_job_lock(job_id, lock_token)
                cleaned += 1
                logger.warning("cleaned_stale_lock", job_id=job_id)
        
        return cleaned
    
    async def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get job status by ID."""
        await self.connect()
        
        job_data = await self.client.hget(f"job:{job_id}", "data")
        if not job_data:
            return None
        
        return Job(**json.loads(job_data))
    
    async def get_queue_stats(self, queue_name: str = "generation") -> dict:
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


async def process_job(job: Job) -> dict:
    """Process a job using registered handlers."""
    handler = JOB_HANDLERS.get(job.type)
    if not handler:
        raise ValueError(f"No handler registered for job type: {job.type}")
    
    return await handler(job.payload)