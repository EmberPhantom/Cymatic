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
