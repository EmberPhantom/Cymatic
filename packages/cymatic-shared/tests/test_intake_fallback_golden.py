"""Golden suite for offline intake fallback quality.

Guards the idea-first contract: short, typo'd, landmark-heavy prompts must
still resolve to the right domain with real entities and grounded questions —
never empty entities with generic questions.
"""
import pytest

from cymatic_shared.agents.intake_agent import process_intake_fallback


@pytest.mark.asyncio
async def test_landmark_joined_typo_resolves_heritage():
    r = await process_intake_fallback("A 3D structrue of TajMahal")
    assert r.detected_domain == "heritage"
    assert r.analyser_mode == "fallback"
    assert r.extracted_entities.get("site_type") == "mausoleum"
    assert "Mughal" in str(r.extracted_entities.get("historical_period", ""))
    assert r.extracted_entities.get("key_pois")
    assert "site_type" not in r.missing_fields
    assert r.confidence >= 0.5


@pytest.mark.asyncio
async def test_landmark_typo_resolves_heritage():
    r = await process_intake_fallback("tempel tour of angkor vat at sunset")
    assert r.detected_domain == "heritage"
    assert r.extracted_entities.get("site_type") == "temple"
    assert "Khmer" in str(r.extracted_entities.get("historical_period", ""))


@pytest.mark.asyncio
async def test_compact_real_estate_cues():
    r = await process_intake_fallback("modern 3bhk apartment with balcony")
    assert r.detected_domain == "real_estate"
    assert r.extracted_entities.get("style") == "modern"
    assert r.extracted_entities.get("bedrooms") == "3BHK"
    assert r.extracted_entities.get("outdoor_spaces") == "balcony"
    for f in ("style", "bedrooms", "outdoor_spaces"):
        assert f not in r.missing_fields


@pytest.mark.asyncio
async def test_keyword_typo_still_matches():
    r = await process_intake_fallback("cozy bedrom with garden")
    assert r.detected_domain == "real_estate"
    assert "bedrooms" in r.extracted_entities
    assert "outdoor_spaces" in r.extracted_entities


@pytest.mark.asyncio
async def test_gibberish_is_honest_not_fake():
    r = await process_intake_fallback("zxqw blorp fnord")
    assert r.extracted_entities == {}
    assert r.confidence <= 0.3
    assert r.analyser_mode == "fallback"
    # Leads with open questions, not fake entities
    assert any("describe" in q.lower() or "in mind" in q.lower() for q in r.suggested_questions[:2])
    assert len(r.suggested_questions) > 0


@pytest.mark.asyncio
async def test_questions_grounded_in_idea():
    r = await process_intake_fallback("A 3D structrue of TajMahal")
    assert r.suggested_questions
    assert "You mentioned" in r.suggested_questions[0]


@pytest.mark.asyncio
async def test_heritage_questions_for_heritage_domain():
    r = await process_intake_fallback("palace walkthrough")
    assert r.detected_domain == "heritage"
    joined = " ".join(r.suggested_questions).lower()
    assert "narration" in joined or "period" in joined or "points of interest" in joined


@pytest.mark.asyncio
async def test_missing_fields_are_domain_canonical():
    r = await process_intake_fallback("Taj Mahal")
    heritage_fields = {"site_type", "historical_period", "key_pois", "narration", "languages", "scale", "focus", "indoor_outdoor"}
    assert set(r.missing_fields) <= heritage_fields
    assert "bedrooms" not in r.missing_fields
