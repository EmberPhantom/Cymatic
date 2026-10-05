"""Regression tests for truncated-SLM JSON salvage.

A 3B SLM occasionally emits EOS mid-object; the router caches the truncated
output, so without repair + cache-bypassed retries the architect fails twice
on the same garbage (seen live: Taj Mahal run, cut mid `key_pois`).
"""

import json

from cymatic_shared.agents.llm_client import _repair_truncated_json


def test_repair_mid_string_truncation_salvages_entity():
    truncated = """{"entities": [{"id": "poi_entrance_gate", "type": "poi",
"properties": {"description": "grand gate", "has_narration": true,
"key_pois": " main gate"""
    repaired = _repair_truncated_json(truncated)
    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["entities"][0]["id"] == "poi_entrance_gate"
    assert parsed["entities"][0]["properties"]["has_narration"] is True


def test_repair_early_cut_without_balanced_close():
    truncated = """{"entities": [{"id": "a", "type": "poi",
"properties": {"x": 1"""
    repaired = _repair_truncated_json(truncated)
    assert repaired is not None
    assert json.loads(repaired)["entities"][0]["id"] == "a"


def test_repair_unrecoverable_returns_none():
    assert _repair_truncated_json("") is None
    assert _repair_truncated_json("not json at all") is None
    assert _repair_truncated_json('{"a": ') is None


def test_meets_completeness_bar():
    from cymatic_shared.agents.llm_client import _meets_completeness_bar

    assert _meets_completeness_bar({"entities": [{"id": "a"}]}, ["entities"]) is True
    assert _meets_completeness_bar({"entities": []}, ["entities"]) is False
    assert _meets_completeness_bar({"other": 1}, ["entities"]) is False
    assert _meets_completeness_bar({"entities": None}, ["entities"]) is False
    assert _meets_completeness_bar({"a": 1}, []) is True


async def _run_call_llm_json(content, **kwargs):
    from unittest.mock import AsyncMock, patch

    from cymatic_shared.agents import llm_client as mod

    fake = AsyncMock(return_value={"choices": [{"message": {"content": content}}]})
    with patch.object(mod.llm_router_client, "chat_completion", fake):
        return await mod.call_llm_json(
            messages=[{"role": "user", "content": "x"}], **kwargs
        )


async def test_repair_without_entities_fails_completeness_bar():
    """A truncated spec that repairs to an entity-less object must return
    the documented {} failure signal (not a false success) so template
    fallback triggers."""
    truncated = '{"metadata": {"title": "Tower", "version": "1.0"}, "entit'
    assert (
        await _run_call_llm_json(truncated, required_non_empty_keys=["entities"]) == {}
    )


async def test_repair_with_entities_passes_completeness_bar():
    truncated = (
        '{"entities": [{"id": "room_a", "type": "room"}], '
        '"navigation": {"points": [1, 2'
    )
    parsed = await _run_call_llm_json(truncated, required_non_empty_keys=["entities"])
    assert parsed["entities"][0]["id"] == "room_a"
