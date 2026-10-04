"""Phase C-Worker tests: concurrency honesty, LLM timeout wiring, checkpoint
TTL/size/per-run files, and the worker LLM-call budget guard.

Items:
  1. WORKER_CONCURRENCY dead flag -> single-owner loop, Dockerfile pinned.
  2. LLM_TIMEOUT wired as the shared client default.
  3. Checkpoint TTL + size guard + per-run files with legacy fallback.
  4. Worker-side LLM backoff/budget + consecutive-failure breaker.
"""

import inspect
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings, get_settings

# NOTE: bound at COLLECTION time on purpose. The autouse mock_llm_client
# fixture patches these same attribute names at test-setup time, so importing
# them inside test bodies would bind the mock instead of the real wrapper.
from app.core.llm_client import (
    _budget_settings as _real_budget_settings,
    call_llm_json_with_budget as _real_call_llm_json_with_budget,
    get_worker_llm_breaker as _real_get_worker_llm_breaker,
    reset_worker_llm_breaker as _real_reset_worker_llm_breaker,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
WORKER_DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


# ---------------------------------------------------------------------------
# Item 1: WORKER_CONCURRENCY honesty
# ---------------------------------------------------------------------------


def test_dockerfile_pins_single_uvicorn_worker():
    text = WORKER_DOCKERFILE.read_text()
    assert (
        "${WORKER_CONCURRENCY" not in text
    ), "Dockerfile must not fan out uvicorn workers from WORKER_CONCURRENCY"
    assert '"--workers", "1"' in text or '"--workers","1"' in text.replace(
        " ", ""
    ), "uvicorn must run with exactly one worker (single worker_loop owner)"


def test_worker_concurrency_kept_only_for_compat():
    assert Settings.model_fields["WORKER_CONCURRENCY"].default == 4
    from app.main import worker_loop

    doc = worker_loop.__doc__ or ""
    assert "SERIAL" in doc, "worker_loop must document its serial contract"


# ---------------------------------------------------------------------------
# Item 2: LLM_TIMEOUT wiring
# ---------------------------------------------------------------------------


def test_llm_timeout_declared_default_is_60():
    assert Settings.model_fields["LLM_TIMEOUT"].default == 60.0


async def test_shared_client_default_matches_worker_settings():
    from cymatic_shared.agents import llm_client as shared_lc

    shared_lc._reset_settings()
    try:
        settings = get_settings()
        client = shared_lc.LLMRouterClient(base_url="http://localhost:9", api_key="")
        try:
            assert float(client.client.timeout.connect) == float(settings.LLM_TIMEOUT)
        finally:
            await client.close()
    finally:
        shared_lc._reset_settings()


def test_budget_and_checkpoint_settings_have_sane_defaults():
    fields = Settings.model_fields
    assert fields["CHECKPOINT_TTL_HOURS"].default == 24.0
    assert fields["CHECKPOINT_MAX_STAGE_BYTES"].default == 1_000_000
    assert fields["LLM_BUDGET_MAX_RETRIES"].default == 3
    assert fields["LLM_BUDGET_BACKOFF_BASE_S"].default == 1.0
    assert fields["LLM_BUDGET_MAX_CONSECUTIVE_FAILURES"].default == 5
    assert fields["LLM_BUDGET_COOLDOWN_S"].default == 30.0


# ---------------------------------------------------------------------------
# Item 3: checkpoints
# ---------------------------------------------------------------------------


def _manager(tmp_path, **kwargs):
    from app.pipelines.checkpoint import PipelineCheckpointManager

    return PipelineCheckpointManager(checkpoint_dir=str(tmp_path), **kwargs)


def _checkpoint(**kwargs):
    from app.pipelines.checkpoint import PipelineCheckpoint

    base = dict(
        project_id=77001,
        stage="intake",
        stage_index=0,
        input_data={"project_id": 77001, "prompt": "test"},
        stage_outputs={"intake": {"detected_domain": "real_estate"}},
    )
    base.update(kwargs)
    return PipelineCheckpoint(**base)


def test_checkpoint_fresh_roundtrip(tmp_path):
    mgr = _manager(tmp_path)
    mgr.save_checkpoint(_checkpoint())
    loaded = mgr.load_checkpoint(77001)
    assert loaded is not None
    assert loaded.project_id == 77001
    assert loaded.stage_outputs["intake"]["detected_domain"] == "real_estate"


def test_checkpoint_stale_is_ignored_and_pruned(tmp_path):
    mgr = _manager(tmp_path, ttl_hours=24.0)
    mgr.save_checkpoint(_checkpoint())
    path = tmp_path / "checkpoint_77001.json"
    assert path.exists()
    # Backdate the payload beyond the TTL (both payload clock and mtime).
    data = json.loads(path.read_text())
    data["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    path.write_text(json.dumps(data))
    old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(path, (old_mtime, old_mtime))

    assert mgr.load_checkpoint(77001) is None
    assert not path.exists(), "stale checkpoint must be pruned on load"


def test_checkpoint_size_guard_stores_pointer(tmp_path):
    mgr = _manager(tmp_path, max_stage_bytes=100)
    big = "x" * 5000
    cp = _checkpoint(stage_outputs={"big": big, "small": {"a": 1}})
    mgr.save_checkpoint(cp)
    # Caller's in-memory data is untouched.
    assert cp.stage_outputs["big"] == big

    loaded = mgr.load_checkpoint(77001)
    assert loaded is not None
    pointer = loaded.stage_outputs["big"]
    assert pointer["_truncated"] is True
    assert pointer["bytes"] >= 5000
    assert "summary" in pointer and "preview" in pointer
    assert loaded.stage_outputs["small"] == {"a": 1}


def test_checkpoint_per_run_files_isolate_reruns(tmp_path):
    mgr = _manager(tmp_path)
    mgr.save_checkpoint(_checkpoint(run_id="run-a"))
    assert (tmp_path / "checkpoint_77001_run-a.json").exists()
    assert not (tmp_path / "checkpoint_77001.json").exists()

    loaded = mgr.load_checkpoint(77001, run_id="run-a")
    assert loaded is not None
    assert loaded.run_id == "run-a"
    # A different run sees nothing; the legacy read sees nothing either.
    assert mgr.load_checkpoint(77001, run_id="run-b") is None
    assert mgr.load_checkpoint(77001) is None


def test_checkpoint_legacy_fallback_for_run_reads(tmp_path):
    mgr = _manager(tmp_path)
    mgr.save_checkpoint(_checkpoint())  # legacy name, no run_id
    loaded = mgr.load_checkpoint(77001, run_id="run-new")
    assert loaded is not None
    assert loaded.stage == "intake"


def test_checkpoint_clear_is_run_scoped(tmp_path):
    mgr = _manager(tmp_path)
    mgr.save_checkpoint(_checkpoint(run_id="run-a"))
    mgr.save_checkpoint(_checkpoint())
    mgr.clear_checkpoint(77001, run_id="run-a")
    assert not (tmp_path / "checkpoint_77001_run-a.json").exists()
    assert (
        tmp_path / "checkpoint_77001.json"
    ).exists(), "clearing one run must not wipe the legacy checkpoint"
    mgr.clear_checkpoint(77001)
    assert not (tmp_path / "checkpoint_77001.json").exists()


def test_checkpoint_prune_stale_sweep(tmp_path):
    mgr = _manager(tmp_path, ttl_hours=24.0)
    mgr.save_checkpoint(_checkpoint(project_id=1))
    stale = _checkpoint(project_id=2)
    mgr.save_checkpoint(stale)
    stale_path = tmp_path / "checkpoint_2.json"
    data = json.loads(stale_path.read_text())
    data["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    stale_path.write_text(json.dumps(data))
    old = (datetime.now(timezone.utc) - timedelta(hours=72)).timestamp()
    os.utime(stale_path, (old, old))

    assert mgr.prune_stale() == 1
    assert (tmp_path / "checkpoint_1.json").exists()
    assert not stale_path.exists()


def test_checkpoint_env_overrides(monkeypatch, tmp_path):
    from app.pipelines.checkpoint import PipelineCheckpointManager

    monkeypatch.setenv("CHECKPOINT_TTL_HOURS", "48")
    monkeypatch.setenv("CHECKPOINT_MAX_STAGE_BYTES", "10")
    mgr = PipelineCheckpointManager(checkpoint_dir=str(tmp_path))
    assert mgr.ttl_hours == 48.0
    assert mgr.max_stage_bytes == 10

    monkeypatch.setenv("CHECKPOINT_TTL_HOURS", "junk")
    monkeypatch.setenv("CHECKPOINT_MAX_STAGE_BYTES", "junk")
    mgr2 = PipelineCheckpointManager(checkpoint_dir=str(tmp_path))
    assert mgr2.ttl_hours == 24.0
    assert mgr2.max_stage_bytes == 1_000_000


def test_pipeline_entry_points_accept_run_id():
    from app.pipelines.real_estate import generate_real_estate_spec
    from app.pipelines.heritage import generate_heritage_spec

    assert "run_id" in inspect.signature(generate_real_estate_spec).parameters
    assert "run_id" in inspect.signature(generate_heritage_spec).parameters


@pytest.mark.parametrize(
    "pipeline_mod_name",
    ["app.pipelines.real_estate", "app.pipelines.heritage"],
)
async def test_pipeline_checkpoints_land_in_per_run_file(
    tmp_path, monkeypatch, pipeline_mod_name
):
    import importlib

    mod = importlib.import_module(pipeline_mod_name)
    from app.agents.intake_agent import IntakeResult
    from app.pipelines.checkpoint import PipelineCheckpointManager

    pipeline_cls, input_cls, result_cls = (
        mod.RealEstatePipeline
        if hasattr(mod, "RealEstatePipeline")
        else mod.HeritagePipeline,
        mod.PipelineInput,
        mod.PipelineResult,
    )
    assert "run_id" in input_cls.model_fields
    pipeline = pipeline_cls()
    pipeline.checkpoint_manager = PipelineCheckpointManager(
        checkpoint_dir=str(tmp_path)
    )
    intake = IntakeResult(
        detected_domain="real_estate",
        objective="x",
        missing_fields=[],
        suggested_questions=[],
        extracted_entities={},
        confidence=0.9,
    )
    calls = {"n": 0}

    async def fake_run_stage(stage, stage_index, input_data, stage_outputs, job=None):
        calls["n"] += 1
        assert input_data.run_id == "run-9", "run_id must thread into stages"
        if calls["n"] == 1:
            return result_cls(status="completed", intake=intake)
        return result_cls(status="validation_failed", error="Final validation failed")

    monkeypatch.setattr(pipeline, "_run_stage", fake_run_stage)
    result = await pipeline.run(
        input_cls(project_id=778001, prompt="test", run_id="run-9")
    )
    assert result.status == "validation_failed"
    assert (tmp_path / "checkpoint_778001_run-9.json").exists()
    assert not (
        tmp_path / "checkpoint_778001.json"
    ).exists(), "per-run checkpoint must not clobber the legacy file"


# ---------------------------------------------------------------------------
# Item 4: worker LLM budget guard
# ---------------------------------------------------------------------------


@pytest.fixture
def _fresh_breaker():
    _real_reset_worker_llm_breaker()
    yield
    _real_reset_worker_llm_breaker()


async def test_wrapper_retries_then_succeeds(_fresh_breaker):
    max_retries, base_delay, _, _ = _real_budget_settings()
    inner = AsyncMock(
        side_effect=[RuntimeError("boom"), RuntimeError("boom"), {"entities": []}]
    )
    with (
        patch("cymatic_shared.agents.llm_client.call_llm_json", new=inner),
        patch("asyncio.sleep", new=AsyncMock()) as asleep,
    ):
        result = await _real_call_llm_json_with_budget(
            messages=[{"role": "user", "content": "hi"}],
            task_type="spec_generation",
        )
    assert result == {"entities": []}
    assert inner.await_count == 3
    assert [c.args[0] for c in asleep.await_args_list] == [
        base_delay,
        base_delay * 2,
    ]
    assert _real_get_worker_llm_breaker().consecutive_failures == 0
    assert max_retries >= 2


async def test_wrapper_gives_up_and_records_breaker_failure(_fresh_breaker):
    max_retries, _, _, _ = _real_budget_settings()
    inner = AsyncMock(side_effect=RuntimeError("router down"))
    with (
        patch("cymatic_shared.agents.llm_client.call_llm_json", new=inner),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(RuntimeError):
            await _real_call_llm_json_with_budget(
                messages=[{"role": "user", "content": "hi"}],
            )
    assert inner.await_count == 1 + max_retries
    assert _real_get_worker_llm_breaker().consecutive_failures == 1


async def test_wrapper_pauses_when_breaker_open(_fresh_breaker):
    _, _, max_failures, cooldown = _real_budget_settings()
    breaker = _real_get_worker_llm_breaker()
    for _ in range(max_failures):
        breaker.record_failure()
    assert breaker.is_open

    inner = AsyncMock(return_value={"ok": True})
    with (
        patch("cymatic_shared.agents.llm_client.call_llm_json", new=inner),
        patch("asyncio.sleep", new=AsyncMock()) as asleep,
    ):
        assert await _real_call_llm_json_with_budget(
            messages=[{"role": "user", "content": "hi"}],
        ) == {"ok": True}
    asleep.assert_awaited_once_with(cooldown)
    assert breaker.consecutive_failures == 0


async def test_architect_cloud_path_uses_budgeted_call(mock_llm_client):
    from app.agents.architect_agent import ArchitectInput, create_spec_llm

    budgeted = AsyncMock(return_value={})
    with patch("app.agents.architect_agent.call_llm_json_with_budget", new=budgeted):
        result = await create_spec_llm(
            ArchitectInput(
                domain="real_estate",
                objective="2BHK walkthrough",
                intake_data={},
                clarification_data={},
            )
        )
    budgeted.assert_awaited_once()
    # The unguarded entry point must not fire on this path anymore.
    mock_llm_client.assert_not_awaited()
    assert result.spec.domain == "real_estate"
