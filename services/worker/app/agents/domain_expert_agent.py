"""Domain Expert Agent - Applies real estate/heritage rules, checks spatial plausibility"""
from typing import Any

from pydantic import BaseModel

from cymatic_shared.schemas.simulation_spec import Entity, SimulationSpec
import structlog

logger = structlog.get_logger()


class DomainCheckResult(BaseModel):
    valid: bool
    issues: list[dict[str, Any]] = []
    suggestions: list[str] = []
    compliance_score: float = 1.0


class DomainExpertAgent:
    """Applies domain-specific rules and checks plausibility."""

    # Real Estate Rules (dimensions in METERS - matches SimulationSpec units)
    REAL_ESTATE_RULES: dict[str, Any] = {
        "min_room_dimensions": {
            "bedroom": {"width": 2.1, "depth": 2.7, "height": 2.4},
            "bathroom": {"width": 1.5, "depth": 2.1, "height": 2.4},
            "kitchen": {"width": 2.4, "depth": 3.0, "height": 2.4},
            "living_room": {"width": 3.6, "depth": 4.5, "height": 2.7},
            "dining_room": {"width": 3.0, "depth": 3.6, "height": 2.7},
        },
        "door_widths": {
            "standard": 0.81,  # meters
            "accessible": 0.91,
            "exterior": 0.91,
        },
        "corridor_width": 0.91,  # meters minimum
        "ceiling_height_min": 2.4,  # meters
        "window_rules": {
            "bedroom_min": 1,  # per bedroom
            "living_min": 1,
            "egress_required": ["bedroom", "basement"],
        },
        "clearances": {
            "toilet_front": 21,  # inches
            "toilet_side": 15,
            "sink_front": 20,
            "shower_min": 30,
            "tub_front": 24,
            "kitchen_aisle": 42,
            "kitchen_work_triangle_max": 26,  # feet total
        },
        "plumbing_groups": {
            "bathroom": ["toilet", "sink", "shower/tub"],
            "kitchen": ["sink", "dishwasher"],
            "laundry": ["washer", "dryer"],
        }
    }
    
    # Heritage Rules
    HERITAGE_RULES: dict[str, Any] = {
        "temple": {
            "orientation": "east_facing_preferred",
            "mandatory_elements": ["garbhagriha", "mandapa", "pradakshina"],
            "proportions": {
                "shikhara_height_to_base": 2.5,
                "mandapa_width_to_depth": 1.5,
            },
            "decorum": {
                "no_shoes_area": True,
                "circumambulation_direction": "clockwise",
            }
        },
        "palace": {
            "hierarchy": ["public", "semi-private", "private"],
            "courtyard_sequence": ["outer", "middle", "inner"],
            "mandatory_elements": ["diwan_i_am", "diwan_i_khas", "zenana"],
            "proportions": {
                "courtyard_aspect_ratio": 1.0,
                "hall_height_to_width": 0.5,
            }
        },
        "courtyard": {
            "enclosure": "four_sided_preferred",
            "center_feature": ["fountain", "tree", "platform"],
            "aspect_ratio_range": [0.8, 1.5],
            "arcade_depth": 8,  # feet
        }
    }
    
    def check_spec(self, spec: SimulationSpec) -> DomainCheckResult:
        """Run domain-specific checks on specification."""
        if spec.domain == "real_estate":
            return self._check_real_estate(spec)
        elif spec.domain == "heritage":
            return self._check_heritage(spec)
        
        return DomainCheckResult(valid=True)
    
    def _check_real_estate(self, spec: SimulationSpec) -> DomainCheckResult:
        """Check real estate specification for compliance."""
        issues = []
        suggestions = []
        score = 1.0
        
        rooms = [e for e in spec.entities if e.type == "room"]
        
        # Check room dimensions
        for room in rooms:
            room_type = self._identify_room_type(room)
            min_dims = self.REAL_ESTATE_RULES["min_room_dimensions"].get(room_type)

            if min_dims:
                size = room.properties.get("size")
                if (
                    not isinstance(size, (list, tuple))
                    or len(size) < 3
                    or not all(isinstance(v, (int, float)) for v in size[:3])
                ):
                    # Missing/unparseable dimensions: flag as warning, not fatal
                    issues.append({
                        "entity": room.id,
                        "field": "properties.size",
                        "message": f"Room '{room.name}' has no measurable size (expected [width, depth, height])",
                        "severity": "warning"
                    })
                    score -= 0.02
                    continue

                width, depth, height = float(size[0]), float(size[1]), float(size[2])
                
                if width < min_dims["width"]:
                    issues.append({
                        "entity": room.id,
                        "field": "size.width",
                        "message": f"{room_type} width {width}m below minimum {min_dims['width']}m",
                        "severity": "warning"
                    })
                    score -= 0.05

                if depth < min_dims["depth"]:
                    issues.append({
                        "entity": room.id,
                        "field": "size.depth",
                        "message": f"{room_type} depth {depth}m below minimum {min_dims['depth']}m",
                        "severity": "warning"
                    })
                    score -= 0.05

                if height < self.REAL_ESTATE_RULES["ceiling_height_min"]:
                    issues.append({
                        "entity": room.id,
                        "field": "size.height",
                        "message": f"Ceiling height {height}m below minimum {self.REAL_ESTATE_RULES['ceiling_height_min']}m",
                        "severity": "error"
                    })
                    score -= 0.1
        
        # Check bathroom clearances
        bathrooms = [r for r in rooms if self._identify_room_type(r) == "bathroom"]
        for bath in bathrooms:
            suggestions.append(f"Verify bathroom '{bath.name}' meets clearance requirements")
        
        # Check kitchen work triangle
        kitchen = next((r for r in rooms if self._identify_room_type(r) == "kitchen"), None)
        if kitchen:
            suggestions.append("Verify kitchen work triangle (sink-stove-fridge) under 26ft total")
        
        # Check window requirements
        bedrooms = [r for r in rooms if self._identify_room_type(r) == "bedroom"]
        for bed in bedrooms:
            if not bed.properties.get("has_window", True):
                issues.append({
                    "entity": bed.id,
                    "field": "properties.has_window",
                    "message": "Bedroom requires at least one window for egress",
                    "severity": "error"
                })
                score -= 0.1
        
        # Check navigation flow
        nav_points = spec.navigation.points
        room_nav_points = [p for p in nav_points if any(r.name in p.name for r in rooms)]
        if len(room_nav_points) < len(rooms):
            suggestions.append("Consider adding navigation points for all major rooms")
        
        return DomainCheckResult(
            valid=len([i for i in issues if i["severity"] == "error"]) == 0,
            issues=issues,
            suggestions=suggestions,
            compliance_score=max(0.0, score)
        )
    
    def _check_heritage(self, spec: SimulationSpec) -> DomainCheckResult:
        """Check heritage specification for compliance."""
        issues = []
        suggestions = []
        score = 1.0
        
        # Identify site type from entities
        site_type = self._identify_heritage_type(spec)
        rules = self.HERITAGE_RULES.get(site_type, {})
        
        if not rules:
            suggestions.append(f"Unknown heritage site type: {site_type}")
            return DomainCheckResult(valid=True, suggestions=suggestions)
        
        # Check mandatory elements
        mandatory = rules.get("mandatory_elements", [])
        entity_names = [e.name.lower() for e in spec.entities]
        
        for element in mandatory:
            found = any(element.lower() in name for name in entity_names)
            if not found:
                issues.append({
                    "entity": "spec",
                    "field": "entities",
                    "message": f"Missing mandatory element for {site_type}: {element}",
                    "severity": "error"
                })
                score -= 0.15
        
        # Check proportions
        proportions = rules.get("proportions", {})
        for prop_name, expected_ratio in proportions.items():
            # This would need actual measurements from entities
            suggestions.append(f"Verify {prop_name} ratio matches {expected_ratio} for {site_type}")
        
        # Check decorum rules
        decorum = rules.get("decorum", {})
        if decorum.get("no_shoes_area"):
            suggestions.append("Mark shoe removal areas at entrances")
        
        if decorum.get("circumambulation_direction"):
            suggestions.append(f"Ensure pradakshina path flows {decorum['circumambulation_direction']}")
        
        # Check POI navigation
        pois = [e for e in spec.entities if e.type == "poi"]
        nav_points = spec.navigation.points
        poi_nav = [p for p in nav_points if any(poi.name in p.name for poi in pois)]
        
        if len(poi_nav) < len(pois):
            suggestions.append("Add navigation points for all points of interest")
        
        return DomainCheckResult(
            valid=len([i for i in issues if i["severity"] == "error"]) == 0,
            issues=issues,
            suggestions=suggestions,
            compliance_score=max(0.0, score)
        )
    
    def _identify_room_type(self, room: Entity) -> str:
        """Identify room type from name and properties."""
        name = room.name.lower()
        props = room.properties
        
        if "master" in name or props.get("is_master"):
            return "bedroom"
        if "bed" in name:
            return "bedroom"
        if "bath" in name:
            return "bathroom"
        if "kitchen" in name:
            return "kitchen"
        if "living" in name or "lounge" in name:
            return "living_room"
        if "dining" in name:
            return "dining_room"
        if "office" in name or "study" in name:
            return "bedroom"  # Similar requirements
        return "bedroom"  # Default
    
    def _identify_heritage_type(self, spec: SimulationSpec) -> str:
        """Identify heritage site type from entities."""
        names = " ".join(e.name.lower() for e in spec.entities)
        
        if "temple" in names:
            return "temple"
        if "palace" in names or "fort" in names:
            return "palace"
        if "courtyard" in names or "haveli" in names:
            return "courtyard"
        if "monument" in names:
            return "palace"  # Similar rules
        
        return "courtyard"  # Default


# Global agent instance
domain_expert_agent = DomainExpertAgent()


def check_domain_compliance(spec: SimulationSpec) -> DomainCheckResult:
    """Convenience function for domain checking."""
    return domain_expert_agent.check_spec(spec)