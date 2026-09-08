"""Simulation Specification Validator"""

from typing import Any
from pydantic import ValidationError
from cymatic_shared.schemas.simulation_spec import SimulationSpec, NavigationPath
import structlog

logger = structlog.get_logger()


class ValidationError_detail:
    def __init__(self, field: str, message: str, code: str = "validation_error"):
        self.field = field
        self.message = message
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message, "code": self.code}


class SpecValidationResult:
    def __init__(self):
        self.errors: list[ValidationError_detail] = []
        self.warnings: list[ValidationError_detail] = []

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, message: str, code: str = "validation_error"):
        self.errors.append(ValidationError_detail(field, message, code))

    def add_warning(self, field: str, message: str, code: str = "warning"):
        self.warnings.append(ValidationError_detail(field, message, code))

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


class SpecValidator:
    """Validates simulation specifications against schema and business rules."""

    # Domain-specific requirements
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

    # Tuned for low-end Android / thermal constraints
    PERFORMANCE_THRESHOLDS = {
        "max_triangles_warning": 50000,
        "max_draw_calls_warning": 30,
        "texture_budget_warning_mb": 50,
    }

    def validate(self, spec_dict: dict[str, Any]) -> SpecValidationResult:
        """Validate a specification dictionary."""
        result = SpecValidationResult()

        # 1. Schema validation
        self._validate_schema(spec_dict, result)
        if not result.valid:
            return result

        # 2. Parse to typed model
        try:
            spec = SimulationSpec(**spec_dict)
        except ValidationError as e:
            for error in e.errors():
                field = ".".join(str(x) for x in error["loc"])
                result.add_error(field, error["msg"], "schema_error")
            return result

        # 3. Business rule validation
        self._validate_business_rules(spec, result)

        # 4. Performance budget validation
        self._validate_performance(spec, result)

        # 5. Navigation validation
        self._validate_navigation(spec, result)

        # 6. Entity validation
        self._validate_entities(spec, result)

        logger.info(
            "spec_validation_completed",
            valid=result.valid,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )
        return result

    def _validate_schema(self, spec_dict: dict[str, Any], result: SpecValidationResult) -> None:
        """Validate required top-level fields exist."""
        required_fields = [
            "domain",
            "metadata",
            "entities",
            "navigation",
            "lighting",
            "copilot_policy",
            "performance_budget",
        ]
        for field in required_fields:
            if field not in spec_dict:
                result.add_error(field, f"Missing required field: {field}")

        if "domain" in spec_dict and spec_dict["domain"] not in [
            "real_estate",
            "heritage",
        ]:
            result.add_error(
                "domain", "Invalid domain. Must be 'real_estate' or 'heritage'"
            )

    def _validate_business_rules(
        self, spec: SimulationSpec, result: SpecValidationResult
    ) -> None:
        """Validate domain-specific business rules."""
        req: dict[str, Any] = self.DOMAIN_REQUIREMENTS.get(spec.domain, {})

        # Count entity types
        entity_types: dict[str, int] = {}
        for entity in spec.entities:
            entity_types[entity.type] = entity_types.get(entity.type, 0) + 1

        # Check required entity types
        required_types: list[str] = req.get("required_entity_types", [])
        for required_type in required_types:
            if required_type not in entity_types:
                result.add_error(
                    "entities", f"Missing required entity type: {required_type}"
                )

        # Domain-specific counts
        if spec.domain == "real_estate":
            room_count = entity_types.get("room", 0)
            if room_count < int(req.get("min_rooms", 1)):
                result.add_warning(
                    "entities", f"Less than {req['min_rooms']} rooms defined"
                )
            if room_count > int(req.get("max_rooms", 20)):
                result.add_warning(
                    "entities",
                    f"More than {req['max_rooms']} rooms may impact performance",
                )

        elif spec.domain == "heritage":
            poi_count = entity_types.get("poi", 0)
            if poi_count < int(req.get("min_pois", 1)):
                result.add_error(
                    "entities",
                    f"Heritage domain requires at least {req['min_pois']} POI",
                )
            if poi_count > int(req.get("max_pois", 50)):
                result.add_warning(
                    "entities",
                    f"More than {req['max_pois']} POIs may impact performance",
                )

        # Check navigation points
        nav_points = len(spec.navigation.points)
        if nav_points < int(req.get("required_navigation_points", 1)):
            result.add_error(
                "navigation",
                f"At least {req['required_navigation_points']} navigation point(s) required",
            )

    def _validate_performance(self, spec: SimulationSpec, result: SpecValidationResult) -> None:
        """Validate performance budget constraints."""
        budget = spec.performance_budget

        if budget.max_triangles > self.PERFORMANCE_THRESHOLDS["max_triangles_warning"]:
            result.add_warning(
                "performance_budget.max_triangles",
                f"Triangle budget exceeds recommended {self.PERFORMANCE_THRESHOLDS['max_triangles_warning']}",
            )

        if (
            budget.max_draw_calls
            > self.PERFORMANCE_THRESHOLDS["max_draw_calls_warning"]
        ):
            result.add_warning(
                "performance_budget.max_draw_calls",
                f"Draw call budget exceeds recommended {self.PERFORMANCE_THRESHOLDS['max_draw_calls_warning']}",
            )

        if (
            budget.texture_budget_mb
            > self.PERFORMANCE_THRESHOLDS["texture_budget_warning_mb"]
        ):
            result.add_warning(
                "performance_budget.texture_budget_mb",
                f"Texture budget exceeds recommended {self.PERFORMANCE_THRESHOLDS['texture_budget_warning_mb']} MB",
            )

        if budget.target_fps < 30:
            result.add_warning(
                "performance_budget.target_fps",
                "Target FPS below 30 may cause motion sickness",
            )
        elif budget.target_fps > 90:
            result.add_warning(
                "performance_budget.target_fps",
                "Target FPS above 90 may not be achievable on mobile",
            )

    def _validate_navigation(self, spec: SimulationSpec, result: SpecValidationResult) -> None:
        """Validate navigation graph connectivity."""
        points = {p.id: p for p in spec.navigation.points}
        paths = spec.navigation.paths

        if not points:
            result.add_error("navigation.points", "No navigation points defined")
            return

        # Check default start point exists
        if spec.navigation.default_start_point not in points:
            result.add_error(
                "navigation.default_start_point",
                f"Default start point '{spec.navigation.default_start_point}' not found in points",
            )

        # Check path connectivity
        connected = set()
        for path in paths:
            if path.from_point not in points:
                result.add_error(
                    "navigation.paths",
                    f"Path references unknown point: {path.from_point}",
                )
            else:
                connected.add(path.from_point)
            if path.to not in points:
                result.add_error(
                    "navigation.paths", f"Path references unknown point: {path.to}"
                )
            else:
                connected.add(path.to)

        # Warn about isolated points
        for point_id in points:
            if point_id not in connected:
                result.add_warning(
                    "navigation.points",
                    f"Navigation point '{point_id}' is not connected to any path",
                )

        # Check for cycles (simple detection)
        self._check_cycles(points, paths, result)

    def _check_cycles(
        self, points: dict[str, Any], paths: list[NavigationPath], result: SpecValidationResult
    ) -> None:
        """Simple cycle detection in navigation graph."""
        # Build adjacency list
        adj: dict[str, list[str]] = {pid: [] for pid in points}
        for path in paths:
            adj[path.from_point].append(path.to)

        # DFS for cycle detection
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for point_id in points:
            if point_id not in visited:
                if dfs(point_id):
                    result.add_warning(
                        "navigation.paths",
                        "Navigation graph contains cycles - may cause navigation issues",
                    )
                    break

    def _validate_entities(self, spec: SimulationSpec, result: SpecValidationResult) -> None:
        """Validate entity properties."""
        entity_ids = set()

        for entity in spec.entities:
            # Check duplicate IDs
            if entity.id in entity_ids:
                result.add_error("entities", f"Duplicate entity ID: {entity.id}")
            entity_ids.add(entity.id)

            # Validate position
            if len(entity.position) != 3:
                result.add_error(
                    f"entities.{entity.id}.position",
                    "Position must have 3 coordinates [x, y, z]",
                )

            # Validate rotation if present
            if entity.rotation and len(entity.rotation) != 3:
                result.add_error(
                    f"entities.{entity.id}.rotation",
                    "Rotation must have 3 values [x, y, z]",
                )

            # Validate scale if present
            if entity.scale and len(entity.scale) != 3:
                result.add_error(
                    f"entities.{entity.id}.scale", "Scale must have 3 values [x, y, z]"
                )

            # Type-specific validation
            if entity.type == "room":
                size = entity.properties.get("size")
                if size and len(size) != 3:
                    result.add_error(
                        f"entities.{entity.id}.properties.size",
                        "Room size must be [width, depth, height]",
                    )

            elif entity.type == "navigation_point":
                # Navigation points should match navigation spec
                pass


# Global validator instance
spec_validator = SpecValidator()


def validate_spec(spec_dict: dict[str, Any]) -> SpecValidationResult:
    """Convenience function to validate a spec."""
    return spec_validator.validate(spec_dict)
