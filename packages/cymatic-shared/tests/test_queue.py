"""P1 - Queue edge cases with fakeredis"""

import pytest

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


@pytest.mark.asyncio
async def test_fail_job_persists_retry_intent_before_sleep(fake_redis):
    """retry_at must be in the job hash immediately after fail_job."""
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(id="intent", type="generation", payload={}, max_retries=3)
    await q.enqueue(job, "generation")
    j = await q.dequeue("generation", worker_id="w1")
    assert j is not None
    await q.fail_job(j, "boom")
    raw = await fake_redis.hget("job:intent", "retry_at")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    assert raw, "retry_at not persisted in job hash"
    status = await q.get_job_status("intent")
    assert status.status == JobStatus.RETRY
    assert status.retry_at is not None


@pytest.mark.asyncio
async def test_sweep_stale_retries_delayed_path(fake_redis):
    """Stale RETRY with stored queue (fail_job delayed path) is requeued."""
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(id="stale1", type="generation", payload={}, max_retries=3)
    await q.enqueue(job, "generation")
    j = await q.dequeue("generation", worker_id="w1")
    await q.fail_job(j, "boom")
    # Simulate crash: force retry_at into the past (delay is ~10s live).
    past = "2000-01-01T00:00:00+00:00"
    await fake_redis.hset("job:stale1", mapping={"retry_at": past})
    requeued = await q.sweep_stale_retries()
    assert requeued == 1
    resumed = await q.dequeue("generation", worker_id="w2")
    assert resumed is not None
    assert resumed.id == "stale1"


@pytest.mark.asyncio
async def test_sweep_stale_retries_immediate_path_no_stored_queue(fake_redis):
    """Stale RETRY without a stored queue falls back to job.type."""
    from datetime import datetime, timezone

    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(
        id="stale2",
        type="asset",
        payload={},
        status=JobStatus.RETRY,
        retry_count=1,
        max_retries=3,
        retry_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    # Immediate/original path: hash has data+status but no "queue" field.
    await fake_redis.hset(
        "job:stale2",
        mapping={
            "data": job.model_dump_json(),
            "status": JobStatus.RETRY.value,
            "retry_at": "2000-01-01T00:00:00+00:00",
        },
    )
    requeued = await q.sweep_stale_retries()
    assert requeued == 1
    resumed = await q.dequeue("asset", worker_id="w2")
    assert resumed is not None
    assert resumed.id == "stale2"


@pytest.mark.asyncio
async def test_sweep_stale_retries_skips_future_retry_at(fake_redis):
    q = JobQueue(redis_url="redis://localhost:6379/0")
    q._client = fake_redis
    job = Job(id="fresh", type="generation", payload={}, status=JobStatus.RETRY)
    await fake_redis.hset(
        "job:fresh",
        mapping={
            "data": job.model_dump_json(),
            "status": JobStatus.RETRY.value,
            "retry_at": "2999-01-01T00:00:00+00:00",
            "queue": "generation",
        },
    )
    assert await q.sweep_stale_retries() == 0
    assert await q.dequeue("generation", worker_id="w1") is None
