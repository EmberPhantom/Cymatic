"""Validation Agent - Checks schema correctness, missing objects, broken navigation, performance budget, Unity-specific checks"""
from typing import Dict, Any, List
from pydantic import BaseModel
from app.services.spec_validator import validate_spec, SpecValidationResult
from cymatic_shared.schemas.simulation_spec import SimulationSpec
import structlog

logger = structlog.get_logger()


class ValidationAgentResult(BaseModel):
    valid: bool
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    spec_score: float  # 0-1 quality score
    recommendations: List[str] = []


class ValidationAgent:
    """Comprehensive validation of simulation specifications including Unity-specific checks."""
    
    def validate(self, spec_dict: Dict[str, Any]) -> ValidationAgentResult:
        """Run full validation pipeline."""
        # 1. Schema validation
        schema_result = validate_spec(spec_dict)
        
        # 2. Calculate quality score
        spec_score = self._calculate_quality_score(spec_dict, schema_result)
        
        # 3. Generate recommendations
        recommendations = self._generate_recommendations(spec_dict, schema_result)
        
        result = ValidationAgentResult(
            valid=schema_result.valid,
            errors=[e.to_dict() for e in schema_result.errors],
            warnings=[w.to_dict() for w in schema_result.warnings],
            spec_score=spec_score,
            recommendations=recommendations
        )
        
        logger.info("validation_completed", valid=result.valid, score=spec_score)
        return result
    
    def _calculate_quality_score(self, spec_dict: Dict[str, Any], schema_result: SpecValidationResult) -> float:
        """Calculate overall spec quality score (0-1).

        Previously returned 0.0 immediately on schema invalid, masking warnings vs errors.
        Now computes granular score: errors weigh heavily, warnings lightly, with partial credit.
        """
        score = 1.0

        # Deduct for errors and warnings without masking (HIGH: score masking)
        # Errors are more severe than warnings
        score -= len(schema_result.errors) * 0.2
        score -= len(schema_result.warnings) * 0.05

        # If invalid, cap score at 0.5 to reflect failure while preserving granularity
        if not schema_result.valid:
            score = min(score, 0.5)

        # Bonus for completeness - attempt even if invalid, but guard parsing
        try:
            spec = SimulationSpec(**spec_dict)

            # Entity completeness
            entity_types = set(e.type for e in spec.entities)
            if "room" in entity_types or "poi" in entity_types:
                score += 0.05

            # Navigation completeness
            if len(spec.navigation.points) >= 2:
                score += 0.05
            if spec.navigation.paths and len(spec.navigation.paths) >= max(1, len(spec.navigation.points) - 1):
                score += 0.05

            # Copilot policy
            if spec.copilot_policy.enabled and len(spec.copilot_policy.languages) > 1:
                score += 0.03

            # Performance budget realism
            if 30 <= spec.performance_budget.target_fps <= 90:
                score += 0.02

        except Exception:  # noqa: BLE001 - broad catch preserves scoring when spec parse fails
            # Parsing failed: additional penalty but not full masking
            score -= 0.1

        return max(0.0, min(1.0, score))
    
    def _generate_recommendations(self, spec_dict: Dict[str, Any], schema_result: SpecValidationResult) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # From warnings
        for warning in schema_result.warnings:
            if "navigation" in warning.field:
                recommendations.append(f"Consider adding more navigation paths: {warning.message}")
            elif "performance" in warning.field:
                recommendations.append(f"Optimize performance budget: {warning.message}")
            elif "entities" in warning.field:
                recommendations.append(f"Review entity count: {warning.message}")
        
        # Domain-specific recommendations
        domain = spec_dict.get("domain", "")
        if domain == "real_estate":
            entities = spec_dict.get("entities", [])
            room_count = len([e for e in entities if e.get("type") == "room"])
            if room_count < 3:
                recommendations.append("Consider adding more rooms for a complete walkthrough experience")
            
            # Check for outdoor spaces
            has_outdoor = any(e.get("properties", {}).get("is_outdoor") for e in entities)
            if not has_outdoor:
                recommendations.append("Consider adding outdoor spaces (balcony, garden, patio) for realism")
            
            # Check for doors/windows
            has_doors = any(e.get("properties", {}).get("has_doors") for e in entities if e.get("type") == "room")
            if not has_doors:
                recommendations.append("Add doors to rooms for proper navigation")
            
            has_windows = any(e.get("properties", {}).get("has_windows") for e in entities if e.get("type") == "room")
            if not has_windows:
                recommendations.append("Add windows to rooms for natural lighting")
        
        elif domain == "heritage":
            entities = spec_dict.get("entities", [])
            poi_count = len([e for e in entities if e.get("type") == "poi"])
            if poi_count < 3:
                recommendations.append("Add more points of interest for richer heritage experience")
            
            # Check narration
            copilot = spec_dict.get("copilot_policy", {})
            if not copilot.get("enabled"):
                recommendations.append("Enable copilot for guided heritage narration")
            
            # Check for audio narration
            has_audio = any(e.get("properties", {}).get("has_narration") for e in entities if e.get("type") == "poi")
            if not has_audio:
                recommendations.append("Add audio narration to POIs for accessibility")
        
        # General recommendations
        nav_points = len(spec_dict.get("navigation", {}).get("points", []))
        if nav_points < 3:
            recommendations.append("Add more navigation points for better exploration")
        
        # Check for materials
        entities = spec_dict.get("entities", [])
        has_materials = any(e.get("properties", {}).get("material") for e in entities)
        if not has_materials:
            recommendations.append("Define materials for entities for proper rendering")
        
        # Check for colliders
        has_colliders = any(e.get("properties", {}).get("has_collider") for e in entities)
        if not has_colliders:
            recommendations.append("Add colliders to entities for physics and navigation")
        
        # Check for NavMesh
        nav_points = len(spec_dict.get("navigation", {}).get("points", []))
        if nav_points == 0:
            recommendations.append("Add navigation points for user movement")
        
        nav_paths = len(spec_dict.get("navigation", {}).get("paths", []))
        if nav_paths < len(spec_dict.get("navigation", {}).get("points", [])) - 1:
            recommendations.append("Add navigation paths between points")
        
        return recommendations[:15]  # Limit to top 15


# Global agent instance
validation_agent = ValidationAgent()


def validate_simulation_spec(spec_dict: Dict[str, Any]) -> ValidationAgentResult:
    """Convenience function for validation."""
    return validation_agent.validate(spec_dict)