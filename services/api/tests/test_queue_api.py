"""Job queue cancel semantics against real Redis (container test env)."""
import pytest

from app.core.queue import Job, JobPriority, job_queue


@pytest.mark.asyncio
async def test_cancel_unknown_job_false():
    assert await job_queue.cancel_job("no-such-job-123") is False


@pytest.mark.asyncio
async def test_cancel_queued_job_true_then_gone():
    job = Job(id="cancel-me-1", type="generate_spec", payload={"project_id": 1})
    await job_queue.enqueue(job, "spec")
    assert await job_queue.cancel_job("cancel-me-1") is True
    assert await job_queue.cancel_job("cancel-me-1") is False  # terminal now

    status = await job_queue.get_job_status("cancel-me-1")
    assert status is not None
    assert status.status.value == "cancelled"


@pytest.mark.asyncio
async def test_cancel_respects_priority_param():
    job = Job(id="cancel-me-2", type="x", payload={}, priority=JobPriority.HIGH)
    await job_queue.enqueue(job, "generation")
    assert await job_queue.cancel_job("cancel-me-2") is True
