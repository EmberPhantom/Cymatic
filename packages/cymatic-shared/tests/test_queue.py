"""P1 - Queue edge cases with fakeredis"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

try:
    from fakeredis.aioredis import FakeRedis
    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False
    FakeRedis = None

from cymatic_shared.queue import Job, JobQueue, JobPriority, JobStatus

@pytest.fixture
def fake_redis():
    if not HAS_FAKEREDIS:
        pytest.skip("fakeredis not installed")
    return FakeRedis()

@pytest.mark.asyncio
async def test_jobqueue_enqueue_priority(fake_redis):
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job_low = Job(id="low", type="generation", payload={}, priority=JobPriority.LOW)
    job_high = Job(id="high", type="generation", payload={}, priority=JobPriority.HIGH)
    await q.enqueue(job_low, "generation")
    await q.enqueue(job_high, "generation")
    # Dequeue should get high priority first (ZPOPMIN with priority value)
    first = await q.dequeue("generation", worker_id="w1")
    assert first is not None
    assert first.id == "high"
    second = await q.dequeue("generation", worker_id="w1")
    assert second is not None
    assert second.id == "low"

@pytest.mark.asyncio
async def test_jobqueue_lock_atomic(fake_redis):
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(id="locktest", type="generation", payload={})
    await q.enqueue(job, "generation")
    j1 = await q.dequeue("generation", worker_id="w1")
    assert j1 is not None
    # Second dequeue should not get same job due to lock
    j2 = await q.dequeue("generation", worker_id="w2")
    assert j2 is None or j2.id != "locktest"

@pytest.mark.asyncio
async def test_jobqueue_fail_retry_backoff(fake_redis):
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(id="retrytest", type="generation", payload={}, max_retries=3)
    await q.enqueue(job, "generation")
    j = await q.dequeue("generation", worker_id="w1")
    assert j is not None
    await q.fail_job(j, "error")
    # Should be in retry state
    status = await q.get_job_status("retrytest")
    assert status.status in (JobStatus.RETRY, JobStatus.FAILED)
