"""Mocked tests for generation tasks to boost coverage"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cymatic_shared.models import SpecStatus


VALID_SPEC_DICT = {
    "domain": "real_estate",
    "metadata": {"title": "Test", "description": "Test", "version": "1.0"},
    "entities": [
        {"id": "room1", "type": "room", "name": "Living Room", "position": [0,0,0], "properties": {"size": [15, 20, 10]}},
    ],
    "navigation": {
        "points": [
            {"id": "nav1", "name": "Living", "position": [7.5,1.6,10], "connections": ["nav2"]},
            {"id": "nav2", "name": "Bedroom", "position": [26,1.6,6], "connections": ["nav1"]},
        ],
        "paths": [{"from": "nav1", "to": "nav2"}],
        "default_start_point": "nav1"
    },
    "lighting": {"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
    "copilot_policy": {"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
    "performance_budget": {"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
}


def _make_mock_session(scalar_returns=None, execute_returns=None):
    mock_session = AsyncMock()
    # execute mock
    async def fake_execute(*args, **kwargs):
        mock_result = MagicMock()
        # scalar_one_or_none should return first scalar_returns item
        if scalar_returns is not None:
            # pop
            val = scalar_returns.pop(0) if scalar_returns else None
            mock_result.scalar_one_or_none.return_value = val
            mock_result.scalar_one.return_value = val
            # for scalars().all()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = val if isinstance(val, list) else []
            mock_result.scalars.return_value = mock_scalars
        else:
            mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        return mock_result
    mock_session.execute = fake_execute
    # scalar helper (for db.scalar)
    async def fake_scalar(stmt):
        if scalar_returns is not None and scalar_returns:
            return scalar_returns.pop(0)
        return None
    mock_session.scalar = fake_scalar
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.refresh = AsyncMock()
    # async context manager
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm, mock_session


@pytest.mark.asyncio
async def test_validate_spec_task_success():
    from app.tasks.generation import validate_spec_task
    mock_spec = MagicMock()
    mock_spec.id = 1
    mock_spec.payload_json = VALID_SPEC_DICT
    mock_spec.status = SpecStatus.DRAFT

    # execute will be called once for select spec, scalar_one_or_none returns mock_spec
    # we need to handle both execute calls: first for spec fetch, then later not needed
    mock_cm, mock_session = _make_mock_session(scalar_returns=[mock_spec])

    # Need to handle execute returning mock_spec for first call, second call after validation also needs mock_spec?
    # Patch AsyncSessionLocal to return mock_cm
    with patch("app.tasks.generation.AsyncSessionLocal", return_value=mock_cm):
        result = await validate_spec_task({"spec_id": 1})
        assert "valid" in result
        assert result["valid"] is True


@pytest.mark.asyncio
async def test_validate_spec_task_not_found():
    from app.tasks.generation import validate_spec_task
    mock_cm, _ = _make_mock_session(scalar_returns=[None])
    with patch("app.tasks.generation.AsyncSessionLocal", return_value=mock_cm):
        try:
            await validate_spec_task({"spec_id": 999})
            assert False, "should have raised"
        except ValueError as e:
            assert "not found" in str(e).lower()


@pytest.mark.asyncio
async def test_analytics_aggregation_empty():
    from app.tasks.generation import analytics_aggregation_task
    # sessions empty, events empty
    mock_cm, mock_session = _make_mock_session(scalar_returns=[[]])  # sessions_result.scalars().all() returns []
    # But analytics does two queries: first for sessions, second for events if session_ids
    # Our fake_execute currently handles one call; need to handle two calls
    # Simplify: mock execute to return empty for both
    mock_session = AsyncMock()
    async def fake_execute(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result
    mock_session.execute = fake_execute
    mock_session.scalar = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.tasks.generation.AsyncSessionLocal", return_value=mock_cm):
        result = await analytics_aggregation_task({"project_id": 1})
        assert result["total_sessions"] == 0
        assert result["total_events"] == 0


@pytest.mark.asyncio
async def test_process_asset_task_not_found():
    from app.tasks.generation import process_asset_task
    mock_cm, _ = _make_mock_session(scalar_returns=[None])
    with patch("app.tasks.generation.AsyncSessionLocal", return_value=mock_cm):
        try:
            await process_asset_task({"asset_id": 999})
            assert False
        except ValueError:
            assert True


@pytest.mark.asyncio
async def test_publish_scene_task_missing_ids():
    from app.tasks.generation import publish_scene_task
    try:
        await publish_scene_task({"project_id": None, "scene_package_id": None})
        assert False
    except ValueError as e:
        assert "required" in str(e).lower()


@pytest.mark.asyncio
async def test_generate_scene_task_invalid_spec_status():
    from app.tasks.generation import generate_scene_task
    from cymatic_shared.models import ProjectStatus
    mock_project = MagicMock()
    mock_project.id = 1
    mock_project.domain = "real_estate"
    mock_project.organization_id = 1
    mock_project.status = ProjectStatus.DRAFT
    mock_spec = MagicMock()
    mock_spec.id = 10
    mock_spec.project_id = 1
    mock_spec.version = 1
    mock_spec.payload_json = VALID_SPEC_DICT
    mock_spec.status = SpecStatus.DRAFT  # not VALID, should fail

    # Need to mock db.execute for project and spec
    mock_session = AsyncMock()
    call_count = {"n": 0}
    async def fake_execute(stmt, *args, **kwargs):
        mock_result = MagicMock()
        if call_count["n"] == 0:
            mock_result.scalar_one_or_none.return_value = mock_project
        elif call_count["n"] == 1:
            mock_result.scalar_one_or_none.return_value = mock_spec
        else:
            mock_result.scalar_one_or_none.return_value = None
        call_count["n"] += 1
        return mock_result
    mock_session.execute = fake_execute
    mock_session.scalar = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.tasks.generation.AsyncSessionLocal", return_value=mock_cm):
        try:
            await generate_scene_task({"project_id": 1, "spec_id": 10})
            assert False
        except ValueError as e:
            assert "valid specification" in str(e).lower()
