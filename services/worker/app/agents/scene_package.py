"""Scene Package Generator - Creates Unity-compatible scene packages from SimulationSpec"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from cymatic_shared.schemas.simulation_spec import SimulationSpec, Entity, NavigationSpec
import structlog
import json
import uuid
from datetime import datetime, timezone

logger = structlog.get_logger()


class ScenePackageMetadata(BaseModel):
    format: str = "cymatic_v1"
    spec_version: int
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "cymatic-worker"
    unity_version: str = "2022.3"
    target_platform: str = "android"
    streaming_protocol: str = "webrtc"


class SceneEntity(BaseModel):
    """Unity-ready entity representation."""
    id: str
    name: str
    type: str
    position: List[float]
    rotation: List[float] = [0, 0, 0]
    scale: List[float] = [1, 1, 1]
    prefab_path: Optional[str] = None
    properties: Dict[str, Any] = {}
    components: List[Dict[str, Any]] = Field(default_factory=list)
    children: List["SceneEntity"] = Field(default_factory=list)


class NavigationPointData(BaseModel):
    id: str
    name: str
    position: List[float]
    description: str = ""
    connections: List[str] = []


class NavigationPathData(BaseModel):
    from_point: str
    to_point: str
    type: str  # walk, teleport
    waypoints: List[List[float]] = Field(default_factory=list)


class LightingData(BaseModel):
    preset: str
    time_of_day: str
    ambient_intensity: float
    sun_direction: List[float] = [0.5, -1, 0.3]
    custom_lights: List[Dict[str, Any]] = Field(default_factory=list)


class CopilotPolicyData(BaseModel):
    enabled: bool = True
    languages: List[str] = ["en", "te"]
    default_language: str = "en"
    personality: str = "helpful_guide"
    allowed_actions: List[str] = [
        "highlight_object", "show_label", "move_to_point", "open_menu",
        "change_material", "pause_tour", "resume_tour", "play_audio_hint", "answer_question"
    ]
    knowledge_base: Optional[str] = None


class PerformanceBudgetData(BaseModel):
    target_fps: int = 60
    max_triangles: int = 100000
    max_draw_calls: int = 50
    texture_budget_mb: int = 100
    max_entities: int = 500
    lod_distances: List[float] = [10.0, 25.0, 50.0]


class ScenePackage(BaseModel):
    """Complete scene package for Unity runtime."""
    metadata: ScenePackageMetadata
    domain: str
    entities: List[SceneEntity]
    navigation: NavigationSpec
    lighting: LightingData
    copilot_policy: CopilotPolicyData
    performance_budget: PerformanceBudgetData
    asset_manifest: Dict[str, Any] = Field(default_factory=dict)


class ScenePackageGenerator:
    """Generates Unity-compatible scene packages from SimulationSpec."""
    
    # Prefab mappings by entity type and style
    PREFAB_MAPPINGS = {
        "real_estate": {
            "room": {
                "modern": "Prefabs/Rooms/ModernRoom",
                "traditional": "Prefabs/Rooms/TraditionalRoom",
                "luxury": "Prefabs/Rooms/LuxuryRoom",
            },
            "furniture": {
                "modern": "Prefabs/Furniture/Modern",
                "traditional": "Prefabs/Furniture/Traditional",
            },
            "light": "Prefabs/Lighting/DirectionalLight",
            "door": "Prefabs/Architecture/Door",
            "window": "Prefabs/Architecture/Window",
        },
        "heritage": {
            "poi": {
                "temple": "Prefabs/Heritage/TemplePOI",
                "palace": "Prefabs/Heritage/PalacePOI",
                "courtyard": "Prefabs/Heritage/CourtyardPOI",
                "monument": "Prefabs/Heritage/MonumentPOI",
            },
            "light": "Prefabs/Lighting/HeritageLight",
        }
    }
    
    # Component templates
    COMPONENT_TEMPLATES = {
        "room": [
            {"type": "MeshFilter", "mesh": "room_mesh"},
            {"type": "MeshRenderer", "materials": ["wall_material", "floor_material"]},
            {"type": "BoxCollider", "isTrigger": False},
            {"type": "NavigationArea", "areaType": "Walkable"},
        ],
        "poi": [
            {"type": "MeshFilter", "mesh": "poi_mesh"},
            {"type": "MeshRenderer", "materials": ["poi_material"]},
            {"type": "SphereCollider", "isTrigger": True, "radius": 2.0},
            {"type": "POIComponent", "description": "", "hasNarration": True},
            {"type": "NavigationArea", "areaType": "Walkable"},
        ],
        "light": [
            {"type": "Light", "lightType": "Directional", "intensity": 1.0, "color": [1.0, 0.95, 0.9]},
        ],
        "navigation_point": [
            {"type": "SphereCollider", "isTrigger": True, "radius": 1.5},
            {"type": "NavigationPoint", "pointId": "", "connections": []},
        ],
    }
    
    def generate(self, spec: SimulationSpec, spec_version: int, asset_manifest: Dict[str, Any] = None) -> ScenePackage:
        """Generate complete scene package from SimulationSpec."""
        
        # Convert entities
        entities = [self._convert_entity(e, spec.domain) for e in spec.entities]
        
        # Convert navigation
        nav_points = [
            NavigationPointData(
                id=p.id,
                name=p.name,
                position=p.position,
                description=p.description or "",
                connections=p.connections
            )
            for p in spec.navigation.points
        ]
        
        nav_paths = [
            NavigationPathData(
                from_point=p.from_point,
                to_point=p.to,
                type=p.type,
                waypoints=p.waypoints or []
            )
            for p in spec.navigation.paths
        ]
        
        navigation = NavigationSpec(
            points=nav_points,
            paths=nav_paths,
            default_start_point=spec.navigation.default_start_point
        )
        
        # Convert lighting
        lighting = LightingData(
            preset=spec.lighting.preset,
            time_of_day=spec.lighting.time_of_day,
            ambient_intensity=spec.lighting.ambient_intensity,
            sun_direction=spec.lighting.sun_direction or [0.5, -1, 0.3],
            custom_lights=spec.lighting.custom_lights or []
        )
        
        # Copilot policy
        copilot = CopilotPolicyData(
            enabled=spec.copilot_policy.enabled,
            languages=spec.copilot_policy.languages,
            default_language=spec.copilot_policy.default_language,
            personality=spec.copilot_policy.personality,
            allowed_actions=spec.copilot_policy.allowed_actions,
            knowledge_base=spec.copilot_policy.knowledge_base,
        )
        
        # Performance budget
        perf = PerformanceBudgetData(
            target_fps=spec.performance_budget.target_fps,
            max_triangles=spec.performance_budget.max_triangles,
            max_draw_calls=spec.performance_budget.max_draw_calls,
            texture_budget_mb=spec.performance_budget.texture_budget_mb,
            max_entities=spec.performance_budget.max_entities,
            lod_distances=spec.performance_budget.lod_distances,
        )
        
        # Metadata
        metadata = ScenePackageMetadata(
            spec_version=spec_version,
            asset_manifest=asset_manifest or {}
        )
        
        package = ScenePackage(
            metadata=metadata,
            domain=spec.domain,
            entities=entities,
            navigation=navigation,
            lighting=lighting,
            copilot_policy=copilot,
            performance_budget=perf,
            asset_manifest=asset_manifest or {}
        )
        
        logger.info("scene_package_generated", domain=spec.domain, entities=len(entities))
        return package
    
    def _convert_entity(self, entity: Entity, domain: str) -> SceneEntity:
        """Convert SimulationSpec Entity to SceneEntity."""
        
        # Determine prefab path
        prefab_path = self._get_prefab_path(entity, domain)
        
        # Get components
        components = self.COMPONENT_TEMPLATES.get(entity.type, []).copy()
        
        # Customize components based on entity properties
        if entity.type == "navigation_point":
            for comp in components:
                if comp.get("type") == "NavigationPoint":
                    comp["pointId"] = entity.id
                    comp["connections"] = entity.properties.get("connections", [])
        
        if entity.type == "poi":
            for comp in components:
                if comp.get("type") == "POIComponent":
                    comp["description"] = entity.properties.get("description", "")
                    comp["hasNarration"] = entity.properties.get("has_narration", True)
        
        # Convert children recursively
        children = []
        for child in entity.children or []:
            children.append(self._convert_entity(child, domain))
        
        return SceneEntity(
            id=entity.id,
            name=entity.name,
            type=entity.type,
            position=entity.position,
            rotation=entity.rotation or [0, 0, 0],
            scale=entity.scale or [1, 1, 1],
            prefab_path=prefab_path,
            properties=entity.properties,
            components=components,
            children=children
        )
    
    def _get_prefab_path(self, entity: Entity, domain: str) -> Optional[str]:
        """Get Unity prefab path for entity."""
        mappings = self.PREFAB_MAPPINGS.get(domain, {})
        
        if entity.type in mappings:
            type_mappings = mappings[entity.type]
            if isinstance(type_mappings, dict):
                # Style-specific
                style = entity.properties.get("style", "modern")
                return type_mappings.get(style, list(type_mappings.values())[0])
            else:
                return type_mappings
        
        return None
    
    def to_json(self, package: ScenePackage) -> str:
        """Serialize scene package to JSON."""
        return package.model_dump_json(indent=2)
    
    def save_to_file(self, package: ScenePackage, filepath: str):
        """Save scene package to file."""
        with open(filepath, 'w') as f:
            f.write(self.to_json(package))
        logger.info("scene_package_saved", path=filepath)


# Global generator instance
scene_package_generator = ScenePackageGenerator()


def generate_scene_package(
    spec: SimulationSpec,
    spec_version: int,
    asset_manifest: Dict[str, Any] = None
) -> ScenePackage:
    """Convenience function to generate scene package."""
    return scene_package_generator.generate(spec, spec_version, asset_manifest)


def scene_package_to_json(package: ScenePackage) -> str:
    return scene_package_generator.to_json(package)