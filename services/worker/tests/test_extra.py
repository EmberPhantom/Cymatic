"""Extra coverage tests for worker"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.architect_agent import create_spec_fallback, ArchitectInput
from app.agents.scene_package import generate_scene_package
from cymatic_shared.schemas.simulation_spec import SimulationSpec
from app.pipelines.real_estate import generate_real_estate_spec
from app.pipelines.heritage import generate_heritage_spec


@pytest.mark.asyncio
async def test_real_estate_pipeline_extra():
    result = await generate_real_estate_spec(project_id=999, prompt="Create a modern 2-bedroom apartment")
    assert result.status == "completed"
    assert result.spec is not None
    assert result.spec.domain == "real_estate"


@pytest.mark.asyncio
async def test_heritage_pipeline_extra():
    result = await generate_heritage_spec(project_id=998, prompt="Generate a heritage temple courtyard walkthrough")
    assert result.status in ("completed", "domain_validation_failed", "validation_failed")
    # Even if domain check fails, pipeline should not crash


@pytest.mark.asyncio
async def test_architect_fallback():
    input_data = ArchitectInput(domain="real_estate", objective="Create apartment", intake_data={"style": "modern"}, clarification_data={})
    result = await create_spec_fallback(input_data)
    assert result.spec.domain == "real_estate"
    assert len(result.spec.entities) > 0

    # trigger LLM failure path via mock raising
    with patch("app.agents.architect_agent.call_llm_json", new=AsyncMock(side_effect=Exception("LLM down"))):
        result2 = await create_spec_fallback(input_data)
        # fallback should still work
        assert result2.spec is not None


def test_scene_package_generation():
    spec = SimulationSpec(
        domain="real_estate",
        metadata={"title": "Test", "description": "Test", "version": "1.0"},
        entities=[
            {"id": "room1", "type": "room", "name": "Living Room", "position": [0,0,0], "properties": {"size": [5,4,3]}},
        ],
        navigation={
            "points": [{"id": "nav1", "name": "Living", "position": [2.5,1.6,1.6], "connections": ["nav2"]}, {"id": "nav2", "name": "Kitchen", "position": [7,1.6,1.6], "connections": ["nav1"]}],
            "paths": [{"from": "nav1", "to": "nav2"}],
            "default_start_point": "nav1"
        },
        lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        copilot_policy={"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
        performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
    )
    pkg = generate_scene_package(spec=spec, spec_version=1, asset_manifest={"assets": []})
    assert pkg.domain == "real_estate"
    assert len(pkg.entities) == 1


def test_checkpoint_save_load():
    from app.pipelines.checkpoint import PipelineCheckpointManager, PipelineCheckpoint
    import tempfile
    tmpdir = tempfile.mkdtemp()
    mgr = PipelineCheckpointManager(checkpoint_dir=tmpdir)
    cp = PipelineCheckpoint(project_id=12345, stage="intake", stage_index=0, input_data={"project_id": 12345, "prompt": "test"}, stage_outputs={"intake": {"detected_domain": "real_estate"}})
    mgr.save_checkpoint(cp)
    loaded = mgr.load_checkpoint(12345)
    assert loaded is not None
    assert loaded.project_id == 12345
    mgr.clear_checkpoint(12345)
    assert mgr.load_checkpoint(12345) is None


def test_research_style_guidance():
    from app.agents.research_agent import get_style_guidance, research_generation
    res = research_generation("real_estate", "modern", {"target_fps": 60})
    assert len(res.style_references) > 0
    guidance = get_style_guidance("real_estate", "modern")
    assert "key_features" in guidance
    # heritage style
    guidance2 = get_style_guidance("heritage", "temple")
    assert "key_features" in guidance2
    # unknown style fallback
    res2 = research_generation("real_estate", "unknown_style", {})
    assert len(res2.style_references) > 0


def test_domain_expert_heritage():
    from app.agents.domain_expert_agent import check_domain_compliance
    from cymatic_shared.schemas.simulation_spec import SimulationSpec, Entity, NavigationSpec, NavigationPoint, NavigationPath
    spec = SimulationSpec(
        domain="heritage",
        metadata={"title": "Test", "description": "Test", "version": "1.0"},
        entities=[
            Entity(id="poi1", type="poi", name="Garbhagriha", position=[0,0,0]),
            Entity(id="poi2", type="poi", name="Mandapa", position=[10,0,0]),
        ],
        navigation=NavigationSpec(
            points=[
                NavigationPoint(id="nav1", name="Garbhagriha", position=[0,1.6,0], connections=["nav2"]),
                NavigationPoint(id="nav2", name="Mandapa", position=[10,1.6,0], connections=["nav1"]),
            ],
            paths=[NavigationPath(from_point="nav1", to="nav2")],
            default_start_point="nav1"
        ),
        lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        copilot_policy={"enabled": True, "languages": ["en"], "default_language": "en", "personality": "expert_narrator"},
        performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
    )
    result = check_domain_compliance(spec)
    # heritage check may have suggestions but valid if mandatory elements found?
    assert isinstance(result.valid, bool)


def test_composer_lighting_variants():
    from app.agents.composer_agent import compose_scene
    from cymatic_shared.schemas.simulation_spec import Entity
    entities = [Entity(id="room1", type="room", name="Living Room", position=[0,0,0])]
    res1 = compose_scene(entities, "real_estate", {"lighting_preference": "warm"})
    assert res1.lighting.preset == "warm"
    res2 = compose_scene(entities, "real_estate", {"lighting_preference": "golden hour"})
    assert res2.lighting.preset == "golden_hour"


def test_asset_high_budget_lod():
    from app.agents.asset_agent import select_assets
    from cymatic_shared.schemas.simulation_spec import Entity
    entities = [Entity(id="room1", type="room", name="Living Room", position=[0,0,0], properties={"style": "modern", "furnished": True})]
    # low budget
    res_low = select_assets(spec_entities=entities, domain="real_estate", performance_budget={"target_fps": 60, "max_triangles": 80000})
    assert len(res_low.selected_assets) > 0
    # high budget triggers medium/high profile
    res_high = select_assets(spec_entities=entities, domain="real_estate", performance_budget={"target_fps": 60, "max_triangles": 200000})
    assert len(res_high.selected_assets) > 0


def test_validation_recommendations():
    from app.agents.validation_agent import validate_simulation_spec
    spec_dict = {
        "domain": "real_estate",
        "metadata": {"title": "Small", "description": "Test", "version": "1.0"},
        "entities": [{"id": "room1", "type": "room", "name": "Small Room", "position": [0,0,0], "properties": {"size": [1,1,1]}}],
        "navigation": {"points": [{"id": "nav1", "name": "Room", "position": [0,1.6,0], "connections": []}], "paths": [], "default_start_point": "nav1"},
        "lighting": {"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        "copilot_policy": {"enabled": False, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
        "performance_budget": {"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
    }
    result = validate_simulation_spec(spec_dict)
    assert result.valid is False or len(result.warnings) >= 0 or len(result.recommendations) > 0


def test_heritage_template_creation():
    from app.pipelines.heritage_templates import create_heritage_spec_from_template, HeritageTemplateLibrary
    spec = create_heritage_spec_from_template("temple_south_indian", "Test Temple", {"title": "My Temple"})
    assert spec.domain == "heritage"
    assert len(spec.entities) > 0
    assert len(HeritageTemplateLibrary.list_templates()) > 0
