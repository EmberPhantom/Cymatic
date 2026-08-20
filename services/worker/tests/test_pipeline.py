"""Tests for generation pipeline"""
import pytest
import asyncio
from app.agents.intake_agent import process_intake
from app.agents.clarification_agent import process_clarification_answers
from app.agents.research_agent import research_generation
from app.agents.domain_expert_agent import check_domain_compliance
from app.agents.architect_agent import create_simulation_spec
from app.agents.asset_agent import select_assets
from app.agents.composer_agent import compose_scene
from app.agents.validation_agent import validate_simulation_spec
from app.pipelines.real_estate import generate_real_estate_spec
from app.pipelines.heritage import generate_heritage_spec
from cymatic_shared.schemas.simulation_spec import SimulationSpec, Entity, NavigationSpec, NavigationPoint, NavigationPath


class TestIntakeAgent:
    def test_real_estate_intake(self):
        prompt = "Create a modern 3-bedroom apartment walkthrough with warm lighting"
        result = process_intake(prompt)
        
        assert result.detected_domain == "real_estate"
        assert "style" in result.missing_fields
        assert "bedrooms" in result.missing_fields
        assert result.confidence > 0.3
    
    def test_heritage_intake(self):
        prompt = "Generate a heritage temple courtyard walkthrough with narration"
        result = process_intake(prompt)
        
        assert result.detected_domain == "heritage"
        assert "site_type" in result.missing_fields
        assert "narration" in result.missing_fields
    
    def test_merge_answers(self):
        from app.agents.intake_agent import merge_intake_answers
        prompt = "Create a modern apartment"
        result = process_intake(prompt)
        
        merged = merge_intake_answers(result, {"style": "modern", "bedrooms": "3"})
        
        assert merged.extracted_entities.get("style") == "modern"
        assert merged.extracted_entities.get("bedrooms") == "3"
        assert "style" not in merged.missing_fields
        assert "bedrooms" not in merged.missing_fields


class TestClarificationAgent:
    def test_real_estate_clarification(self):
        current = {"style": "modern"}
        new = {"bedrooms": "3", "bathrooms": "2"}
        
        result = process_clarification_answers("real_estate", current, new)
        
        assert result.updated_fields["style"] == "modern"
        assert result.updated_fields["bedrooms"] == 3
        assert result.updated_fields["bathrooms"] == 2
        assert result.completion_percentage > 0
    
    def test_heritage_clarification(self):
        current = {"site_type": "temple"}
        new = {"narration": "yes", "languages": "english,telugu"}
        
        result = process_clarification_answers("heritage", current, new)
        
        assert result.updated_fields["site_type"] == "temple"
        assert result.updated_fields["narration"] is True
        assert result.updated_fields["languages"] == "english,telugu"


class TestResearchAgent:
    def test_real_estate_research(self):
        result = research_generation("real_estate", "modern", {"target_fps": 60})
        
        assert len(result.style_references) > 0
        assert len(result.best_practices) > 0
        assert result.constraints_summary["domain"] == "real_estate"
    
    def test_heritage_research(self):
        result = research_generation("heritage", "temple", {"target_fps": 60})
        
        assert len(result.style_references) > 0
        assert result.constraints_summary["domain"] == "heritage"


class TestDomainExpertAgent:
    def test_real_estate_compliance(self):
        # Create a valid spec
        spec = SimulationSpec(
            domain="real_estate",
            metadata={"title": "Test", "description": "Test", "version": "1.0"},
            entities=[
                Entity(id="room1", type="room", name="Living Room", position=[0,0,0], properties={"size": [15, 20, 10]}),
                Entity(id="room2", type="room", name="Bedroom", position=[20,0,0], properties={"size": [12, 12, 10]}),
            ],
            navigation=NavigationSpec(
                points=[
                    NavigationPoint(id="nav1", name="Living Room", position=[7.5, 1.6, 10], connections=["nav2"]),
                    NavigationPoint(id="nav2", name="Bedroom", position=[26, 1.6, 6], connections=["nav1"]),
                ],
                paths=[NavigationPath(from_point="nav1", to="nav2")],
                default_start_point="nav1"
            ),
            lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
            copilot_policy={"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
            performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
        )
        
        result = check_domain_compliance(spec)
        
        assert result.valid is True
        assert result.compliance_score > 0.5
    
    def test_real_estate_violations(self):
        # Create spec with violations
        spec = SimulationSpec(
            domain="real_estate",
            metadata={"title": "Test", "description": "Test", "version": "1.0"},
            entities=[
                Entity(id="room1", type="room", name="Tiny Bedroom", position=[0,0,0], properties={"size": [5, 5, 7]}),  # Too small
            ],
            navigation=NavigationSpec(
                points=[
                    NavigationPoint(id="nav1", name="Tiny Bedroom", position=[2.5, 1.6, 2.5], connections=[]),
                ],
                paths=[],
                default_start_point="nav1"
            ),
            lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
            copilot_policy={"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
            performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
        )
        
        result = check_domain_compliance(spec)
        
        assert result.valid is False  # Ceiling height violation
        assert len(result.issues) > 0


class TestArchitectAgent:
    def test_create_real_estate_spec(self):
        intake_data = {"style": "modern", "bedrooms": 2, "bathrooms": 1, "furnished": True}
        clarification_data = {"square_footage": 1200, "floors": 1}
        
        result = create_simulation_spec(
            domain="real_estate",
            objective="Create a modern apartment",
            intake_data=intake_data,
            clarification_data=clarification_data
        )
        
        assert result.spec.domain == "real_estate"
        assert len(result.spec.entities) > 0
        assert len(result.spec.navigation.points) > 0
        assert result.spec.performance_budget.target_fps == 60


class TestComposerAgent:
    def test_grid_flow_layout(self):
        entities = [
            Entity(id="room1", type="room", name="Living Room", position=[0,0,0]),
            Entity(id="room2", type="room", name="Kitchen", position=[0,0,0]),
            Entity(id="room3", type="room", name="Bedroom", position=[0,0,0]),
        ]
        
        result = compose_scene(entities, "real_estate", {})
        
        assert len(result.entities) == 3
        assert len(result.navigation.points) == 3
        assert len(result.navigation.paths) == 2  # Linear connections
        
        # Check positions were updated
        for entity in result.entities:
            assert entity.position != [0, 0, 0]
    
    def test_radial_courtyard_layout(self):
        entities = [
            Entity(id="poi1", type="poi", name="Main Hall", position=[0,0,0]),
            Entity(id="poi2", type="poi", name="Sanctuary", position=[0,0,0]),
            Entity(id="poi3", type="poi", name="Courtyard", position=[0,0,0]),
        ]
        
        result = compose_scene(entities, "heritage", {})
        
        assert len(result.entities) == 3
        assert len(result.navigation.points) == 4  # 3 POIs + center
        assert len(result.navigation.paths) > 0


class TestValidationAgent:
    def test_valid_spec(self):
        spec = SimulationSpec(
            domain="real_estate",
            metadata={"title": "Test", "description": "Test", "version": "1.0"},
            entities=[
                Entity(id="room1", type="room", name="Living Room", position=[0,0,0], properties={"size": [15, 20, 10]}),
            ],
            navigation=NavigationSpec(
                points=[
                    NavigationPoint(id="nav1", name="Living Room", position=[7.5, 1.6, 10], connections=["nav2"]),
                    NavigationPoint(id="nav2", name="Kitchen", position=[26, 1.6, 6], connections=["nav1"]),
                ],
                paths=[NavigationPath(from_point="nav1", to="nav2")],
                default_start_point="nav1"
            ),
            lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
            copilot_policy={"enabled": True, "languages": ["en", "te"], "default_language": "en", "personality": "helpful_guide"},
            performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
        )
        
        result = validate_simulation_spec(spec.model_dump())
        
        assert result.valid is True
        assert result.spec_score > 0.5
    
    def test_invalid_spec_missing_navigation(self):
        spec = SimulationSpec(
            domain="real_estate",
            metadata={"title": "Test", "description": "Test", "version": "1.0"},
            entities=[
                Entity(id="room1", type="room", name="Living Room", position=[0,0,0]),
            ],
            navigation=NavigationSpec(points=[], paths=[], default_start_point="start"),
            lighting={"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
            copilot_policy={"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
            performance_budget={"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100}
        )
        
        result = validate_simulation_spec(spec.model_dump())
        
        assert result.valid is False
        assert any("navigation" in e["field"] for e in result.errors)


class TestAssetAgent:
    def test_asset_selection(self):
        entities = [
            Entity(id="room1", type="room", name="Living Room", position=[0,0,0], properties={"style": "modern", "furnished": True}),
        ]
        
        result = select_assets(
            spec_entities=entities,
            domain="real_estate",
            performance_budget={"target_fps": 60, "max_triangles": 100000}
        )
        
        assert len(result.selected_assets) > 0
        assert result.manifest.total_size_mb > 0
        assert result.manifest.estimated_load_time_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])