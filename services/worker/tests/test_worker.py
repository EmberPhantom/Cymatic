"""Tests for Worker service"""
import pytest
from app.agents.intake_agent import process_intake
from app.agents.clarification_agent import process_clarification_answers
from app.agents.validation_agent import validate_simulation_spec


@pytest.mark.asyncio
async def test_intake_agent():
    result = await process_intake("Create a modern 3-bedroom apartment")
    assert result.detected_domain == "real_estate"
    assert "style" in result.missing_fields
    assert len(result.suggested_questions) > 0


@pytest.mark.asyncio
async def test_clarification_agent():
    current = {"style": "modern"}
    new = {"bedrooms": "3", "bathrooms": "2"}
    result = await process_clarification_answers("real_estate", current, new)
    assert result.updated_fields["bedrooms"] == 3
    assert result.updated_fields["bathrooms"] == 2


@pytest.mark.asyncio
async def test_validation_agent():
    from cymatic_shared.schemas.simulation_spec import (
        SimulationSpec, Entity, NavigationSpec, NavigationPoint, NavigationPath,
    )

    spec = SimulationSpec(
        domain="real_estate",
        metadata={"title": "Test", "description": "Test", "version": "1.0"},
        entities=[
            Entity(id="room1", type="room", name="Living Room", position=[0, 0, 0], properties={"size": [5, 4, 3]}),
            Entity(id="navpoint1", type="navigation_point", name="Nav Point 1", position=[2.5, 1.6, 1.6]),
        ],
        navigation=NavigationSpec(
            points=[
                NavigationPoint(id="nav1", name="Living Room", position=[2.5, 1.6, 1.6], connections=["nav2"]),
                NavigationPoint(id="nav2", name="Kitchen", position=[7, 1.6, 1.6], connections=["nav1"]),
            ],
            paths=[NavigationPath(from_point="nav1", to="nav2")],
            default_start_point="nav1",
        ),
        lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        copilot_policy={"enabled": True, "languages": ["en", "te"], "default_language": "en", "personality": "helpful_guide"},
        performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100},
    )

    result = validate_simulation_spec(spec.model_dump())
    assert result.valid is True
