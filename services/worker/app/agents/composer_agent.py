"""Scene Composer Agent - Proposes spatial layout, navigation points, lighting presets"""
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel
from cymatic_shared.schemas.simulation_spec import (
    Entity, NavigationSpec, NavigationPoint, NavigationPath, LightingSpec
)
import math
import structlog

logger = structlog.get_logger()


class ComposerInput(BaseModel):
    entities: List[Entity]
    domain: str
    user_preferences: Dict[str, Any] = {}
    constraints: Dict[str, Any] = {}


class ComposerResult(BaseModel):
    entities: List[Entity]  # Updated with positions
    navigation: NavigationSpec
    lighting: LightingSpec
    layout_notes: List[str] = []


class SceneComposerAgent:
    """Composes spatial layout from entities."""
    
    # Layout algorithms per domain
    LAYOUT_STRATEGIES = {
        "real_estate": "grid_flow",
        "heritage": "radial_courtyard",
    }
    
    def compose(self, input_data: ComposerInput) -> ComposerResult:
        """Compose scene layout."""
        strategy = self.LAYOUT_STRATEGIES.get(input_data.domain, "grid_flow")
        
        if strategy == "grid_flow":
            entities, nav_points, paths = self._grid_flow_layout(input_data)
        elif strategy == "radial_courtyard":
            entities, nav_points, paths = self._radial_courtyard_layout(input_data)
        else:
            entities, nav_points, paths = self._grid_flow_layout(input_data)
        
        # Create navigation spec
        navigation = NavigationSpec(
            points=nav_points,
            paths=paths,
            default_start_point=nav_points[0].id if nav_points else "start"
        )
        
        # Create lighting
        lighting = self._create_lighting(input_data.domain, input_data.user_preferences)
        
        notes = [
            f"Applied {strategy} layout strategy",
            f"Positioned {len(entities)} entities",
            f"Created {len(nav_points)} navigation points",
            f"Generated {len(paths)} navigation paths"
        ]
        
        logger.info("scene_composed", strategy=strategy, entities=len(entities))
        
        return ComposerResult(
            entities=entities,
            navigation=navigation,
            lighting=lighting,
            layout_notes=notes
        )
    
    def _grid_flow_layout(self, input_data: ComposerInput) -> Tuple[List[Entity], List[NavigationPoint], List[NavigationPath]]:
        """Grid-based layout for real estate (rooms in flow)."""
        entities = input_data.entities
        rooms = [e for e in entities if e.type == "room"]
        others = [e for e in entities if e.type != "room"]
        
        # Layout parameters
        room_width = 12
        room_depth = 10
        corridor_width = 3
        max_per_row = 3
        
        positioned_entities = []
        nav_points = []
        paths = []
        
        # Position rooms in grid
        for i, room in enumerate(rooms):
            row = i // max_per_row
            col = i % max_per_row
            
            x = col * (room_width + corridor_width)
            z = row * (room_depth + corridor_width)
            
            # Update entity position
            room.position = [x + room_width/2, 0, z + room_depth/2]
            positioned_entities.append(room)
            
            # Create navigation point at room center
            nav_point = NavigationPoint(
                id=f"nav_{room.id}",
                name=room.name,
                position=[x + room_width/2, 1.6, z + room_depth/2],
                description=f"Enter {room.name}",
                connections=[]
            )
            nav_points.append(nav_point)
        
        # Position other entities (lights, decorations) relative to rooms
        for entity in others:
            if entity.type == "light":
                # Place lights above room centers
                if nav_points:
                    center = nav_points[len(nav_points)//2]
                    entity.position = [center.position[0], 5, center.position[2]]
            positioned_entities.append(entity)
        
        # Create navigation paths (linear flow through rooms)
        for i in range(len(nav_points) - 1):
            paths.append(NavigationPath(
                from_point=nav_points[i].id,
                to=nav_points[i+1].id,
                type="walk"
            ))
        
        # Add connections to nav points
        for path in paths:
            for np in nav_points:
                if np.id == path.from_point:
                    np.connections.append(path.to)
                if np.id == path.to:
                    np.connections.append(path.from_point)
        
        return positioned_entities, nav_points, paths
    
    def _radial_courtyard_layout(self, input_data: ComposerInput) -> Tuple[List[Entity], List[NavigationPoint], List[NavigationPath]]:
        """Radial layout for heritage (courtyard with surrounding POIs)."""
        entities = input_data.entities
        pois = [e for e in entities if e.type == "poi"]
        others = [e for e in entities if e.type != "poi"]
        
        positioned_entities = []
        nav_points = []
        paths = []
        
        # Central courtyard
        center_x, center_z = 0, 0
        courtyard_radius = 15
        
        # Position POIs in circle around center
        for i, poi in enumerate(pois):
            angle = (2 * math.pi * i) / max(len(pois), 1)
            radius = courtyard_radius + 5
            
            x = center_x + radius * math.cos(angle)
            z = center_z + radius * math.sin(angle)
            
            poi.position = [x, 0, z]
            positioned_entities.append(poi)
            
            # Navigation point at POI
            nav_point = NavigationPoint(
                id=f"nav_{poi.id}",
                name=poi.name,
                position=[x, 1.6, z],
                description=f"Visit {poi.name}",
                connections=[]
            )
            nav_points.append(nav_point)
        
        # Add center courtyard point
        center_nav = NavigationPoint(
            id="nav_courtyard_center",
            name="Central Courtyard",
            position=[center_x, 1.6, center_z],
            description="Central gathering area",
            connections=[]
        )
        nav_points.insert(0, center_nav)
        
        # Position other entities
        for entity in others:
            if entity.type == "light":
                entity.position = [center_x, 10, center_z]
            positioned_entities.append(entity)
        
        # Create radial paths (center to each POI)
        for nav_point in nav_points[1:]:  # Skip center
            paths.append(NavigationPath(
                from_point=center_nav.id,
                to=nav_point.id,
                type="walk"
            ))
        
        # Connect adjacent POIs in circle
        for i in range(1, len(nav_points)):
            next_i = (i % (len(nav_points) - 1)) + 1
            paths.append(NavigationPath(
                from_point=nav_points[i].id,
                to=nav_points[next_i].id,
                type="walk"
            ))
        
        # Add connections
        for path in paths:
            for np in nav_points:
                if np.id == path.from_point:
                    np.connections.append(path.to)
                if np.id == path.to:
                    np.connections.append(path.from_point)
        
        return positioned_entities, nav_points, paths
    
    def _create_lighting(self, domain: str, preferences: Dict[str, Any]) -> LightingSpec:
        """Create lighting specification."""
        lighting_pref = preferences.get("lighting_preference", "warm")
        
        preset_map = {
            "warm": "warm",
            "bright/natural": "neutral",
            "cool/modern": "cool",
            "golden hour": "golden_hour",
            "evening/ambient": "golden_hour",
        }
        
        preset = preset_map.get(lighting_pref.lower(), "warm")
        
        return LightingSpec(
            preset=preset,
            time_of_day=preferences.get("time_of_day", "evening"),
            ambient_intensity=0.8,
            sun_direction=[0.5, -1, 0.3] if preset == "golden_hour" else [0, -1, 0]
        )


# Global agent instance
composer_agent = SceneComposerAgent()


def compose_scene(
    entities: List[Entity],
    domain: str,
    user_preferences: Dict[str, Any] = None,
    constraints: Dict[str, Any] = None
) -> ComposerResult:
    """Convenience function for scene composition."""
    input_data = ComposerInput(
        entities=entities,
        domain=domain,
        user_preferences=user_preferences or {},
        constraints=constraints or {}
    )
    return composer_agent.compose(input_data)