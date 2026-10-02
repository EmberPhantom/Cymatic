import copy

from cymatic_shared.services.spec_validator import validate_spec


def valid_spec():
    return {
        "domain": "real_estate",
        "metadata": {"title": "Test", "description": "Test", "version": "1"},
        "entities": [
            {
                "id": "room-1",
                "type": "room",
                "name": "Living Room",
                "position": [0, 0, 0],
                "properties": {"size": [5, 4, 3]},
            },
            {
                "id": "nav-1",
                "type": "navigation_point",
                "name": "Entry",
                "position": [0, 1.6, 0],
            },
        ],
        "navigation": {
            "points": [{"id": "nav-1", "name": "Entry", "position": [0, 1.6, 0]}],
            "paths": [],
            "default_start_point": "nav-1",
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
        },
        "performance_budget": {
            "target_fps": 60,
            "max_triangles": 100000,
            "max_draw_calls": 50,
            "texture_budget_mb": 100,
        },
    }


def test_valid_real_estate_spec_passes():
    result = validate_spec(valid_spec())
    assert result.valid is True
    assert result.errors == []


def test_missing_required_fields_are_reported_without_schema_crash():
    result = validate_spec({"domain": "real_estate"})
    fields = {error.field for error in result.errors}
    assert result.valid is False
    assert {
        "metadata",
        "entities",
        "navigation",
        "lighting",
        "copilot_policy",
        "performance_budget",
    } <= fields


def test_duplicate_entity_and_invalid_default_navigation_are_rejected():
    spec = valid_spec()
    spec["entities"].append(copy.deepcopy(spec["entities"][0]))
    spec["navigation"]["default_start_point"] = "missing"

    result = validate_spec(spec)
    messages = [error.message for error in result.errors]
    assert any("Duplicate entity ID" in message for message in messages)
    assert any("Default start point" in message for message in messages)


def test_heritage_requires_poi():
    spec = valid_spec()
    spec["domain"] = "heritage"
    result = validate_spec(spec)
    assert result.valid is False
    assert any("POI" in error.message for error in result.errors)


def test_high_performance_budgets_generate_warnings_not_errors():
    spec = valid_spec()
    spec["performance_budget"].update(
        {
            "max_triangles": 90000,
            "max_draw_calls": 45,
            "texture_budget_mb": 90,
            "target_fps": 20,
        }
    )

    result = validate_spec(spec)
    assert result.valid is True
    assert len(result.warnings) >= 4


def test_unknown_path_points_are_errors():
    spec = valid_spec()
    spec["navigation"]["paths"] = [{"from": "nav-1", "to": "ghost", "type": "walk"}]

    result = validate_spec(spec)
    assert result.valid is False
    assert any("ghost" in error.message for error in result.errors)


def test_navigation_cycles_warn():
    spec = valid_spec()
    spec["navigation"]["points"].append(
        {"id": "nav-2", "name": "B", "position": [3, 1.6, 0]}
    )
    spec["navigation"]["paths"] = [
        {"from": "nav-1", "to": "nav-2", "type": "walk"},
        {"from": "nav-2", "to": "nav-1", "type": "walk"},
    ]

    result = validate_spec(spec)
    assert result.valid is True
    assert any("cycle" in w.message.lower() for w in result.warnings)


def test_excess_rooms_warn():
    spec = valid_spec()
    for i in range(100, 121):
        spec["entities"].append(
            {
                "id": f"room-{i}",
                "type": "room",
                "name": f"R{i}",
                "position": [0, 0, 0],
                "properties": {"size": [5, 4, 3]},
            }
        )

    result = validate_spec(spec)
    assert result.valid is True
    assert any("rooms may impact performance" in w.message for w in result.warnings)


def test_malformed_rotation_rejected_at_schema():
    # Schema pins rotation to exactly 3; business rule is defense-in-depth.
    spec = valid_spec()
    spec["entities"].append(
        {
            "id": "room-bad-rot",
            "type": "room",
            "name": "Bad",
            "position": [0, 0, 0],
            "rotation": [0, 0],
            "properties": {"size": [5, 4, 3]},
        }
    )

    result = validate_spec(spec)
    assert result.valid is False
    assert any("rotation" in e.field for e in result.errors)
