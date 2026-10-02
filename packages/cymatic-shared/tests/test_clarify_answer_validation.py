"""Regression tests for fallback clarification answer validation.

Free-text answers ("when it was built for the first time.") must never
overwrite clean entities as canonical field values (live Taj run: site_type
became "palace." and poisoned the architect + domain check). Raw text is
kept in answer_notes; only validated values become entities.
"""

from cymatic_shared.agents.clarification_agent import (
    _clean_fallback_answer,
    process_clarification_fallback,
)


def test_choice_matches_option_canonically():
    clean, raw = _clean_fallback_answer("site_type", "palace.", "heritage")
    assert clean == "Palace"
    assert raw == "palace."


def test_sentence_is_note_not_entity():
    clean, raw = _clean_fallback_answer(
        "historical_period", "when it was built for the first time.", "heritage"
    )
    assert clean is None
    assert raw is not None and "when it was built" in raw


def test_fragment_with_vocabulary_passes():
    clean, _ = _clean_fallback_answer("historical_period", "Mughal era", "heritage")
    assert clean == "Mughal era"


def test_boolean_contains_match():
    clean, _ = _clean_fallback_answer(
        "narration", "yes, english and hindi.", "heritage"
    )
    assert clean is True


def test_number_extraction():
    clean, _ = _clean_fallback_answer("bedrooms", "3 bedrooms", "real_estate")
    assert clean == 3


def test_good_entity_survives_garbage_answer():
    current = {"site_type": "mausoleum", "historical_period": "Mughal"}
    new = {
        "site_type": "palace.",
        "historical_period": "when it was built for the first time.",
        "narration": "yes",
    }
    r = process_clarification_fallback("heritage", current, new)
    assert r.updated_fields["site_type"] == "Palace"
    assert r.updated_fields["historical_period"] == "Mughal"
    assert "when it was built" in r.answer_notes["historical_period"]
    assert r.updated_fields["narration"] is True


def test_choice_without_separator_matching_no_option_does_not_crash():
    # Live regression: a short choice answer with no comma/slash that matches
    # no option (e.g. scale="entire complex") raised UnboundLocalError on
    # `parts` and failed the whole worker clarification stage.
    clean, raw = _clean_fallback_answer("scale", "entire complex", "heritage")
    assert clean == "entire complex"
    assert raw == "entire complex"
