"""Phase B1 (worker pipeline correctness P0s) regression tests.

Covers: spec_id flush, failure-checkpoint persistence, corrupt-stage drop,
async MinIO variants, RunStage mapping, advisory-lock keys, template errors,
has_window unification, time_of_day normalization, research flags.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cymatic_shared.model_enums import RunStage
from cymatic_shared.schemas.simulation_spec import Entity


VALID_INTAKE = {
    "detected_domain": "real_estate",
    "objective": "test",
    "missing_fields": [],
    "suggested_questions": [],
    "extracted_entities": {"site_type": "courtyard"},
    "confidence": 0.9,
}


def _base_spec_dict(room_props):
    return {
        "domain": "real_estate",
        "metadata": {"title": "Test", "description": "Test", "version": "1.0"},
        "entities": [
            {
                "id": "room1",
                "type": "room",
                "name": "Living Room",
                "position": [0, 0, 0],
                "properties": room_props,
            },
        ],
        "navigation": {
            "points": [
                {
                    "id": "nav1",
                    "name": "Living",
                    "position": [7.5, 1.6, 10],
                    "connections": ["nav2"],
                },
                {
                    "id": "nav2",
                    "name": "Bedroom",
                    "position": [26, 1.6, 6],
                    "connections": ["nav1"],
                },
            ],
            "paths": [{"from": "nav1", "to": "nav2"}],
            "default_start_point": "nav1",
        },
        "lighting": {
            "preset": "warm",
            "time_of_day": "evening",
            "ambient_intensity": 0.8,
        },
        "copilot_policy": {
            "enabled": True,
            "languages": ["en"],
            "default_language": "en",
            "personality": "helpful_guide",
        },
        "performance_budget": {
            "target_fps": 60,
            "max_triangles": 100000,
            "max_draw_calls": 50,
            "texture_budget_mb": 100,
        },
    }


def _mock_cm(mock_session):
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


# ---------------------------------------------------------------------------
# Item 1: spec_id flush before result_json
# ---------------------------------------------------------------------------


async def test_generate_spec_result_json_has_real_spec_id():
    from app.tasks.generation import generate_spec_task
    from app.pipelines.real_estate import PipelineResult
    from app.agents.validation_agent import ValidationAgentResult
    from cymatic_shared.schemas.simulation_spec import SimulationSpec

    project = MagicMock()
    project.id = 1
    project.domain = "real_estate"
    run = MagicMock()
    run.id = 7

    spec = SimulationSpec(**_base_spec_dict({"size": [15, 20, 10]}))
    pipeline_result = PipelineResult(status="completed", spec=spec)
    validation = ValidationAgentResult(
        valid=True, errors=[], warnings=[], spec_score=0.9
    )

    mock_session = AsyncMock()
    calls = {"n": 0}

    async def fake_execute(stmt, *args, **kwargs):
        mock_result = MagicMock()
        idx = calls["n"]
        calls["n"] += 1
        if idx in (0, 1):
            mock_result.scalar_one_or_none.return_value = project
        else:
            # version query: SELECT max+1
            mock_result.scalar_one.return_value = 1
        return mock_result

    async def fake_scalar(stmt):
        return run

    captured = {}

    def _add(obj):
        captured["db_spec"] = obj

    async def _flush():
        # Simulate Postgres assigning the PK on flush.
        captured["db_spec"].id = 42

    mock_session.execute = fake_execute
    mock_session.scalar = fake_scalar
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock(side_effect=_flush)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with (
        patch(
            "app.tasks.generation.AsyncSessionLocal",
            return_value=_mock_cm(mock_session),
        ),
        patch(
            "app.pipelines.real_estate.generate_real_estate_spec",
            AsyncMock(return_value=pipeline_result),
        ),
        patch(
            "app.agents.validation_agent.validate_simulation_spec",
            return_value=validation,
        ),
    ):
        result = await generate_spec_task(
            {"project_id": 1, "prompt": "modern apartment", "run_id": 7}
        )

    assert mock_session.flush.await_count == 1
    assert result["spec_id"] == 42
    assert run.result_json["spec_id"] == 42
    assert run.result_json["spec_id"] is not None


# ---------------------------------------------------------------------------
# Item 10: pipeline statuses map to valid RunStage values
# ---------------------------------------------------------------------------


def test_pipeline_status_to_run_stage_mapping():
    from app.tasks.generation.spec_tasks import _PIPELINE_STATUS_TO_RUN_STAGE

    assert (
        _PIPELINE_STATUS_TO_RUN_STAGE["awaiting_clarification"]
        is RunStage.CLARIFICATION
    )
    assert _PIPELINE_STATUS_TO_RUN_STAGE["validation_failed"] is RunStage.VALIDATION
    assert (
        _PIPELINE_STATUS_TO_RUN_STAGE["domain_validation_failed"] is RunStage.VALIDATION
    )
    assert (
        _PIPELINE_STATUS_TO_RUN_STAGE.get("some_future_status", RunStage.SPEC)
        is RunStage.SPEC
    )
    assert set(_PIPELINE_STATUS_TO_RUN_STAGE.values()) <= set(RunStage)


# ---------------------------------------------------------------------------
# Item 11: collision-free advisory lock keys
# ---------------------------------------------------------------------------


def test_advisory_lock_keys_namespaced_and_distinct():
    from cymatic_shared.db import advisory_lock_key

    assert advisory_lock_key("scene", 10, 1) == advisory_lock_key("scene", 10, 1)
    assert advisory_lock_key("scene", 10, 1) != advisory_lock_key("scene", 1, 10)
    assert advisory_lock_key("scene", 1) != advisory_lock_key("spec", 1)
    assert 0 <= advisory_lock_key("scene", 10, 1) < 2**63


# ---------------------------------------------------------------------------
# Item 2: checkpoint persisted before early returns (both pipelines)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pipeline_mod_name",
    ["app.pipelines.real_estate", "app.pipelines.heritage"],
)
async def test_failure_checkpoint_persisted(tmp_path, monkeypatch, pipeline_mod_name):
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
        if calls["n"] == 1:
            return result_cls(status="completed", intake=intake)
        return result_cls(status="validation_failed", error="Final validation failed")

    monkeypatch.setattr(pipeline, "_run_stage", fake_run_stage)
    result = await pipeline.run(input_cls(project_id=777001, prompt="test"))
    assert result.status == "validation_failed"
    ckpt_file = tmp_path / "checkpoint_777001.json"
    assert ckpt_file.exists(), "checkpoint missing after early return"
    data = json.loads(ckpt_file.read_text())
    assert data["status"] == "validation_failed"
    assert data["error"] == "Final validation failed"
    assert "intake" in data["stage_outputs"]


# ---------------------------------------------------------------------------
# Item 3: corrupt stage entries dropped (only the corrupt one)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pipeline_mod_name",
    ["app.pipelines.real_estate", "app.pipelines.heritage"],
)
def test_corrupt_stage_entry_dropped_only_corrupt(pipeline_mod_name):
    import importlib

    mod = importlib.import_module(pipeline_mod_name)
    pipeline_cls = (
        mod.RealEstatePipeline
        if hasattr(mod, "RealEstatePipeline")
        else mod.HeritagePipeline
    )
    pipeline = pipeline_cls()
    outputs = {
        "intake": dict(VALID_INTAKE),
        "research": {"style_references": 12345},
    }
    result = mod.PipelineResult()
    dropped = pipeline._load_stage_outputs(outputs, result)
    assert result.intake is not None
    assert result.research is None
    assert dropped == ["research"]
    assert "intake" in outputs
    assert "research" not in outputs


# ---------------------------------------------------------------------------
# Item 4: async MinIO variants + lock key capture
# ---------------------------------------------------------------------------


class _FakeMinIO:
    def __init__(self):
        self.uploaded: dict = {}
        self.sync_upload_calls = 0
        self.sync_info_calls = 0

    async def upload_data_async(
        self, object_name, data, content_type=None, metadata=None
    ):
        self.uploaded[object_name] = data
        return object_name

    async def get_object_info_async(self, object_name):
        data = self.uploaded.get(object_name)
        if data is None:
            return None
        return {"size": len(data), "etag": "x", "content_type": "application/json"}

    def upload_data(self, *args, **kwargs):
        self.sync_upload_calls += 1
        raise AssertionError("sync upload_data must not be called in async handler")

    def get_object_info(self, *args, **kwargs):
        self.sync_info_calls += 1
        raise AssertionError("sync get_object_info must not be called in async handler")


async def test_generate_scene_uses_async_minio():
    from app.tasks.generation import generate_scene_task
    from cymatic_shared.db import advisory_lock_key
    from cymatic_shared.models import SpecStatus

    project = MagicMock()
    project.id = 1
    project.organization_id = 9
    project.domain = "real_estate"
    spec = MagicMock()
    spec.id = 10
    spec.project_id = 1
    spec.version = 1
    spec.payload_json = _base_spec_dict({"size": [15, 20, 10]})
    spec.status = SpecStatus.VALID

    lock_params: dict = {}
    mock_session = AsyncMock()
    calls = {"n": 0}

    async def fake_execute(stmt, *args, **kwargs):
        mock_result = MagicMock()
        idx = calls["n"]
        calls["n"] += 1
        if idx == 0:
            mock_result.scalar_one_or_none.return_value = project
        elif idx == 1:
            mock_result.scalar_one_or_none.return_value = spec
        else:
            # advisory lock execute(stmt, params)
            if args and isinstance(args[0], dict):
                lock_params.update(args[0])
        return mock_result

    mock_session.execute = fake_execute
    mock_session.scalar = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.refresh = AsyncMock()

    fake_minio = _FakeMinIO()
    with (
        patch(
            "app.tasks.generation.AsyncSessionLocal",
            return_value=_mock_cm(mock_session),
        ),
        patch(
            "app.tasks.generation.scene_tasks.get_minio_client",
            return_value=fake_minio,
        ),
    ):
        result = await generate_scene_task({"project_id": 1, "spec_id": 10})

    assert result["storage_key"].startswith("orgs/9/projects/1/scenes/")
    assert fake_minio.uploaded, "async upload was never called"
    assert fake_minio.sync_upload_calls == 0
    assert fake_minio.sync_info_calls == 0
    # Item 11: scene lock key is the namespaced derivation.
    assert lock_params.get("key") == advisory_lock_key("scene", 10, 1)


# ---------------------------------------------------------------------------
# Item 7: unknown heritage template is an error, not a silent default
# ---------------------------------------------------------------------------


def test_unknown_heritage_template_errors():
    from app.pipelines.heritage_templates import (
        HeritageTemplateLibrary,
        create_heritage_spec_from_template,
    )

    assert HeritageTemplateLibrary.get_template("no_such_template") is None
    assert (
        HeritageTemplateLibrary.get_template("temple_south_indian")["site_type"]
        == "temple"
    )
    with pytest.raises(ValueError, match="Unknown heritage template"):
        create_heritage_spec_from_template("no_such_template", "P", {})


async def test_heritage_pipeline_surfaces_unknown_template():
    from app.pipelines.heritage import HeritagePipeline, PipelineInput

    pipeline = HeritagePipeline()
    inp = PipelineInput(
        project_id=5,
        prompt="x",
        context={"template_id": "no_such_template"},
        expected_domain="heritage",
    )
    with pytest.raises(ValueError, match="Unknown heritage template"):
        await pipeline._run_stage("architect", 3, inp, {"intake": dict(VALID_INTAKE)})


# ---------------------------------------------------------------------------
# Item 8: has_window canonical key
# ---------------------------------------------------------------------------


def test_validation_accepts_canonical_has_window():
    from app.agents.validation_agent import validate_simulation_spec

    recs = " ".join(
        validate_simulation_spec(
            _base_spec_dict({"size": [15, 20, 10], "has_window": True})
        ).recommendations
    ).lower()
    assert "window" not in recs


def test_validation_flags_missing_window():
    from app.agents.validation_agent import validate_simulation_spec

    recs = " ".join(
        validate_simulation_spec(
            _base_spec_dict({"size": [15, 20, 10]})
        ).recommendations
    ).lower()
    assert "window" in recs


def test_validation_accepts_legacy_has_windows_alias():
    from app.agents.validation_agent import validate_simulation_spec

    recs = " ".join(
        validate_simulation_spec(
            _base_spec_dict({"size": [15, 20, 10], "has_windows": True})
        ).recommendations
    ).lower()
    assert "window" not in recs


# ---------------------------------------------------------------------------
# Item 9: time_of_day normalization
# ---------------------------------------------------------------------------


def test_normalize_time_of_day():
    from app.agents.composer_agent import normalize_time_of_day

    assert normalize_time_of_day("golden hour") == "evening"
    assert normalize_time_of_day("Golden Hour glow") == "evening"
    assert normalize_time_of_day("sunset") == "evening"
    assert normalize_time_of_day("dawn") == "morning"
    assert normalize_time_of_day("sunrise") == "morning"
    assert normalize_time_of_day("morning") == "morning"
    assert normalize_time_of_day("noon") == "noon"
    assert normalize_time_of_day("night") == "night"
    assert normalize_time_of_day("evening") == "evening"
    assert normalize_time_of_day(None) == "evening"
    assert normalize_time_of_day("something weird") == "evening"


def test_compose_scene_golden_hour_does_not_crash():
    from app.agents.composer_agent import compose_scene

    entities = [
        Entity(id="room1", type="room", name="Living Room", position=[0, 0, 0]),
    ]
    result = compose_scene(entities, "real_estate", {"time_of_day": "golden hour"})
    assert result.lighting.time_of_day == "evening"


# ---------------------------------------------------------------------------
# Item 12: research explicit default flag + Filament renderer directive
# ---------------------------------------------------------------------------


def test_research_unknown_style_flagged_not_silent():
    from app.agents.research_agent import research_generation

    result = research_generation(
        "real_estate", "definitely_not_a_style_xyz", {"target_fps": 60}
    )
    assert result.style_defaulted is True
    assert result.requested_style == "definitely_not_a_style_xyz"
    assert len(result.style_references) > 0


def test_research_known_style_not_flagged():
    from app.agents.research_agent import research_generation

    result = research_generation("real_estate", "modern", {"target_fps": 60})
    assert result.style_defaulted is False
    assert result.requested_style == "modern"


def test_research_rendering_targets_filament_sbs():
    from app.agents.research_agent import research_generation

    result = research_generation("heritage", "temple", {})
    assert result.constraints_summary["rendering"] == "filament_sbs"
