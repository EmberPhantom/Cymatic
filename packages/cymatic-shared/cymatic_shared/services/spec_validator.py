"""Spec Validator - validates simulation specifications against schema and business rules."""
from typing import List, Dict, Any
from pydantic import ValidationError
from cymatic_shared.schemas.simulation_spec import SimulationSpec
import structlog

logger = structlog.get_logger()


class ValidationErrorDetail:
    def __init__(self, field: str, message: str, code: str = "validation_error"):
        self.field = field
        self.message = message
        self.code = code

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "message": self.message, "code": self.code}


class SpecValidationResult:
    def __init__(self):
        self.errors: List[ValidationErrorDetail] = []
        self.warnings: List[ValidationErrorDetail] = []

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, message: str, code: str = "validation_error"):
        self.errors.append(ValidationErrorDetail(field, message, code))

    def add_warning(self, field: str, message: str, code: str = "warning"):
        self.warnings.append(ValidationErrorDetail(field, message, code))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


class SpecValidator:
    """Validates simulation specifications against schema and business rules."""

    DOMAIN_REQUIREMENTS = {
        "real_estate": {
            "required_entity_types": ["room", "navigation_point"],
            "min_rooms": 1,
            "max_rooms": 20,
            "required_navigation_points": 1,
        },
        "heritage": {
            "required_entity_types": ["poi", "navigation_point"],
            "min_pois": 1,
            "max_pois": 50,
            "required_navigation_points": 1,
        },
    }

    PERFORMANCE_THRESHOLDS = {
        "max_triangles_warning": 80000,
        "max_draw_calls_warning": 40,
        "texture_budget_warning_mb": 80,
    }

    def validate(self, spec_dict: Dict[str, Any]) -> SpecValidationResult:
        result = SpecValidationResult()

        self._validate_schema(spec_dict, result)
        if not result.valid:
            return result

        try:
            spec = SimulationSpec(**spec_dict)
        except ValidationError as e:
            for error in e.errors():
                field = ".".join(str(x) for x in error["loc"])
                result.add_error(field, error["msg"], "schema_error")
            return result

        self._validate_business_rules(spec, result)
        self._validate_performance(spec, result)
        self._validate_navigation(spec, result)
        self._validate_entities(spec, result)

        logger.info("spec_validation_completed", valid=result.valid, errors=len(result.errors), warnings=len(result.warnings))
        return result

    def _validate_schema(self, spec_dict: Dict[str, Any], result: SpecValidationResult):
        required_fields = ["domain", "metadata", "entities", "navigation", "lighting", "copilot_policy", "performance_budget"]
        for field in required_fields:
            if field not in spec_dict:
                result.add_error(field, f"Missing required field: {field}")
        if "domain" in spec_dict and spec_dict["domain"] not in ["real_estate", "heritage"]:
            result.add_error("domain", "Invalid domain. Must be 'real_estate' or 'heritage'")

    def _validate_business_rules(self, spec: SimulationSpec, result: SpecValidationResult):
        req = self.DOMAIN_REQUIREMENTS.get(spec.domain, {})
        entity_types = {}
        for entity in spec.entities:
            entity_types[entity.type] = entity_types.get(entity.type, 0) + 1
        for required_type in req.get("required_entity_types", []):
            if required_type not in entity_types:
                result.add_error("entities", f"Missing required entity type: {required_type}")
        if spec.domain == "real_estate":
            room_count = entity_types.get("room", 0)
            if room_count < req.get("min_rooms", 1):
                result.add_warning("entities", f"Less than {req['min_rooms']} rooms defined")
        elif spec.domain == "heritage":
            poi_count = entity_types.get("poi", 0)
            if poi_count < req.get("min_pois", 1):
                result.add_error("entities", f"Heritage domain requires at least {req['min_pois']} POI")
        nav_points = len(spec.navigation.points)
        if nav_points < req.get("required_navigation_points", 1):
            result.add_error("navigation", f"At least {req['required_navigation_points']} navigation point(s) required")

    def _validate_performance(self, spec: SimulationSpec, result: SpecValidationResult):
        budget = spec.performance_budget
        if budget.max_triangles > self.PERFORMANCE_THRESHOLDS["max_triangles_warning"]:
            result.add_warning("performance_budget.max_triangles", "Triangle budget exceeds recommended threshold")
        if budget.max_draw_calls > self.PERFORMANCE_THRESHOLDS["max_draw_calls_warning"]:
            result.add_warning("performance_budget.max_draw_calls", "Draw call budget exceeds recommended threshold")
        if budget.texture_budget_mb > self.PERFORMANCE_THRESHOLDS["texture_budget_warning_mb"]:
            result.add_warning("performance_budget.texture_budget_mb", "Texture budget exceeds recommended threshold")
        if budget.target_fps < 30:
            result.add_warning("performance_budget.target_fps", "Target FPS below 30 may cause motion sickness")
        elif budget.target_fps > 90:
            result.add_warning("performance_budget.target_fps", "Target FPS above 90 may not be achievable on mobile")

    def _validate_navigation(self, spec: SimulationSpec, result: SpecValidationResult):
        points = {p.id: p for p in spec.navigation.points}
        if not points:
            result.add_error("navigation.points", "No navigation points defined")
            return
        if spec.navigation.default_start_point not in points:
            result.add_error("navigation.default_start_point", f"Default start point '{spec.navigation.default_start_point}' not found in points")
        connected = set()
        for path in spec.navigation.paths:
            if path.from_point in points:
                connected.add(path.from_point)
            if path.to in points:
                connected.add(path.to)
        for point_id in points:
            if point_id not in connected:
                result.add_warning("navigation.points", f"Navigation point '{point_id}' is not connected to any path")

    def _validate_entities(self, spec: SimulationSpec, result: SpecValidationResult):
        entity_ids = set()
        for entity in spec.entities:
            if entity.id in entity_ids:
                result.add_error("entities", f"Duplicate entity ID: {entity.id}")
            entity_ids.add(entity.id)
            if len(entity.position) != 3:
                result.add_error(f"entities.{entity.id}.position", "Position must have 3 coordinates [x, y, z]")


spec_validator = SpecValidator()


def validate_spec(spec_dict: Dict[str, Any]) -> SpecValidationResult:
    """Convenience function to validate a spec."""
    return spec_validator.validate(spec_dict)
