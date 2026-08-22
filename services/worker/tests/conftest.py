"""Worker test configuration - mock LLM client for test isolation.

Patches call_llm_json at each consumer namespace (not at the definition site)
and returns realistic per-domain data so the LLM code paths are exercised.
"""
import json as _json
import pytest
from unittest.mock import AsyncMock, patch


def _intake_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
    """Return intake-appropriate mock data based on prompt content."""
    content = messages[1]["content"] if len(messages) > 1 else ""
    prompt = content.split("Prompt: ")[1].split("\n")[0] if "Prompt: " in content else content.lower()

    is_heritage = any(kw in prompt.lower() for kw in ("heritage", "temple", "monument", "palace", "museum", "courtyard"))

    if is_heritage:
        return {
            "detected_domain": "heritage",
            "objective": prompt,
            "missing_fields": ["site_type", "narration"],
            "suggested_questions": [
                "What type of heritage site?",
                "Do you need guided narration?",
            ],
            "extracted_entities": {},
            "confidence": 0.85,
        }

    return {
        "detected_domain": "real_estate",
        "objective": prompt,
        "missing_fields": ["style", "bedrooms"],
        "suggested_questions": [
            "What architectural style do you prefer?",
            "How many bedrooms do you need?",
        ],
        "extracted_entities": {},
        "confidence": 0.85,
    }


def _clarification_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
    """Return clarification mock data. The user message contains the merged answers."""
    content = messages[1]["content"] if len(messages) > 1 else "{}"
    try:
        data = _json.loads(content)
    except (_json.JSONDecodeError, IndexError):
        data = {}

    # current_answers already has converted values from convert_value()
    updated_fields = data.get("current_answers", {})

    return {
        "questions": [],
        "updated_fields": updated_fields,
        "ready_for_generation": False,
        "completion_percentage": 0.6,
    }


def _architect_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
    """Return architect mock data - a valid SimulationSpec dict."""
    return {
        "domain": "real_estate",
        "metadata": {"title": "Test Apartment", "description": "Generated spec", "version": "1.0"},
        "entities": [
            {"id": "room1", "type": "room", "name": "Living Room", "position": [0, 0, 0], "properties": {"size": [15, 20, 10]}},
            {"id": "room2", "type": "room", "name": "Bedroom", "position": [20, 0, 0], "properties": {"size": [12, 12, 10]}},
        ],
        "navigation": {
            "points": [
                {"id": "nav1", "name": "Living Room", "position": [7.5, 1.6, 10], "connections": ["nav2"]},
                {"id": "nav2", "name": "Bedroom", "position": [26, 1.6, 6], "connections": ["nav1"]},
            ],
            "paths": [{"from_point": "nav1", "to": "nav2"}],
            "default_start_point": "nav1",
        },
        "lighting": {"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        "copilot_policy": {"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
        "performance_budget": {"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100},
    }


def _dispatch_llm(messages, task_type="copilot_chat", **kwargs):
    """Route to the correct mock based on task_type."""
    if task_type == "intent_extraction":
        return _intake_mock(messages, task_type=task_type, **kwargs)
    elif task_type == "clarification":
        return _clarification_mock(messages, task_type=task_type, **kwargs)
    elif task_type == "spec_generation":
        return _architect_mock(messages, task_type=task_type, **kwargs)
    return {}


@pytest.fixture(autouse=True)
def mock_llm_client():
    """Mock call_llm_json at all three consumer namespaces.

    Patch targets:
      - cymatic_shared.agents.intake_agent.call_llm_json
      - cymatic_shared.agents.clarification_agent.call_llm_json
      - app.agents.architect_agent.call_llm_json
    """
    mock = AsyncMock(side_effect=_dispatch_llm)

    patches = [
        patch("cymatic_shared.agents.intake_agent.call_llm_json", mock),
        patch("cymatic_shared.agents.clarification_agent.call_llm_json", mock),
        patch("app.agents.architect_agent.call_llm_json", mock),
    ]

    for p in patches:
        p.start()

    yield mock

    for p in patches:
        p.stop()
