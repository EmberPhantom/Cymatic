"""Shared Simulation Specification Schemas (Python/Pydantic)"""

from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime, timezone


Domain = Literal["real_estate", "heritage"]
EntityType = Literal[
    "room",
    "wall",
    "floor",
    "ceiling",
    "door",
    "window",
    "furniture",
    "decoration",
    "light",
    "navigation_point",
    "poi",
    "audio_zone",
    "trigger_zone",
]
LightingPreset = Literal[
    "warm", "cool", "neutral", "golden_hour", "blue_hour", "custom"
]
CopilotPersonality = Literal[
    "helpful_guide", "expert_narrator", "friendly_assistant", "professional_host"
]
CopilotAction = Literal[
    "highlight_object",
    "show_label",
    "move_to_point",
    "open_menu",
    "change_material",
    "pause_tour",
    "resume_tour",
    "play_audio_hint",
    "answer_question",
]
NavigationPathType = Literal["walk", "teleport"]
CustomLightType = Literal["directional", "point", "spot", "area"]


def _coerce_vec3(v):
    """Accept both [x, y, z] lists and {x, y, z} dicts for vector fields."""
    if isinstance(v, dict):
        return [
            float(v.get("x", 0.0)),
            float(v.get("y", 0.0)),
            float(v.get("z", 0.0)),
        ]
    return v


class SpecMetadata(BaseModel):
    title: str
    description: str
    version: str = "1.0.0"
    author: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = []

    @field_validator("version", mode="before")
    @classmethod
    def _coerce_version(cls, v):
        return str(v)


def _check_finite_vec(v, *, bound: float = 1e6):
    """Reject NaN/Inf and absurd magnitudes that overflow Unity farClip."""
    if v is None:
        return v
    import math

    vals = v if isinstance(v, list) else [v]
    for item in vals:
        seq = item if isinstance(item, list) else [item]
        for x in seq:
            if isinstance(x, (int, float)) and (
                not math.isfinite(float(x)) or abs(float(x)) > bound
            ):
                raise ValueError(f"vector values must be finite within ±{bound:g}")
    return v


class Entity(BaseModel):
    id: str
    type: EntityType
    name: str
    position: List[float] = Field(min_length=3, max_length=3)
    rotation: Optional[List[float]] = Field(default=None, min_length=3, max_length=3)
    scale: Optional[List[float]] = Field(default=None, min_length=3, max_length=3)
    properties: Dict[str, Any] = {}
    children: List["Entity"] = []

    @field_validator("position", "rotation", "scale", mode="before")
    @classmethod
    def _vec_fields(cls, v):
        return _coerce_vec3(v)

    @field_validator("position", "rotation", "scale")
    @classmethod
    def _vec_finite(cls, v):
        return _check_finite_vec(v)


class NavigationPoint(BaseModel):
    id: str
    name: str
    position: List[float] = Field(min_length=3, max_length=3)
    description: Optional[str] = None
    connections: List[str] = []

    @field_validator("position", mode="before")
    @classmethod
    def _vec_field(cls, v):
        return _coerce_vec3(v)


class NavigationPath(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_point: str = Field(alias="from", serialization_alias="from")
    to: str
    type: NavigationPathType = "walk"
    waypoints: Optional[List[List[float]]] = None

    @model_validator(mode="before")
    @classmethod
    def _remap_keys(cls, data):
        if isinstance(data, dict):
            data = dict(data)  # avoid mutating caller via pop
            if "to" not in data and data.get("to_point") is not None:
                data["to"] = data["to_point"]
            if "from" not in data and data.get("from_point") is not None:
                data["from"] = data.pop("from_point")
        return data


class NavigationSpec(BaseModel):
    points: List[NavigationPoint]
    paths: List[NavigationPath]
    default_start_point: str


class CustomLight(BaseModel):
    type: CustomLightType
    position: List[float] = Field(min_length=3, max_length=3)
    color: List[float] = Field(min_length=3, max_length=3)
    intensity: float
    range: Optional[float] = None
    angle: Optional[float] = None

    @field_validator("position", "color", mode="before")
    @classmethod
    def _vec_fields(cls, v):
        return _coerce_vec3(v)


class LightingSpec(BaseModel):
    preset: LightingPreset
    time_of_day: Literal["morning", "noon", "evening", "night"]
    ambient_intensity: float = 1.0
    sun_direction: Optional[List[float]] = Field(
        default=None, min_length=3, max_length=3
    )
    custom_lights: List[CustomLight] = []

    @field_validator("sun_direction", mode="before")
    @classmethod
    def _vec_field(cls, v):
        return _coerce_vec3(v)


class CopilotPolicy(BaseModel):
    enabled: bool = True
    languages: List[str] = ["en"]
    default_language: str = "en"
    personality: CopilotPersonality = "helpful_guide"
    allowed_actions: List[CopilotAction] = [
        "highlight_object",
        "show_label",
        "move_to_point",
        "open_menu",
        "change_material",
        "pause_tour",
        "resume_tour",
        "play_audio_hint",
        "answer_question",
    ]
    knowledge_base: Optional[str] = None

    @model_validator(mode="after")
    def _check_lang(self):
        if not self.allowed_actions:
            raise ValueError("allowed_actions must not be empty")
        if self.default_language not in self.languages:
            raise ValueError("default_language must be in languages")
        return self


class PerformanceBudget(BaseModel):
    target_fps: int = Field(default=60, ge=15, le=120)
    max_triangles: int = Field(default=100000, ge=1000, le=2000000)
    max_draw_calls: int = Field(default=50, ge=1, le=500)
    texture_budget_mb: int = Field(default=100, ge=1, le=2048)
    max_entities: int = Field(default=500, ge=1, le=5000)
    lod_distances: List[float] = Field(
        default=[10.0, 25.0, 50.0], min_length=3, max_length=3
    )

    @field_validator("lod_distances")
    @classmethod
    def _lod_ordered(cls, v: List[float]):
        import math

        for x in v:
            if not math.isfinite(x) or x <= 0 or x > 1e4:
                raise ValueError("lod_distances must be finite positive <= 1e4")
        if not (v[0] < v[1] < v[2]):
            raise ValueError("lod_distances must be strictly increasing")
        return v


class SimulationSpec(BaseModel):
    domain: Domain
    metadata: SpecMetadata
    entities: List[Entity] = []
    navigation: NavigationSpec
    lighting: LightingSpec
    copilot_policy: CopilotPolicy
    performance_budget: PerformanceBudget

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": "real_estate",
                "metadata": {
                    "title": "Modern 3BR Apartment",
                    "description": "Furnished walkthrough with warm lighting",
                    "version": "1.0.0",
                },
                "entities": [
                    {
                        "id": "living_room",
                        "type": "room",
                        "name": "Living Room",
                        "position": [0, 0, 0],
                        "properties": {"size": [5, 4, 2.5]},
                    }
                ],
                "navigation": {
                    "points": [
                        {
                            "id": "start",
                            "name": "Entry",
                            "position": [2.5, 2, 1.6],
                            "connections": ["living"],
                        },
                        {
                            "id": "living",
                            "name": "Living Room",
                            "position": [2.5, 2, 1.6],
                            "connections": ["start"],
                        },
                    ],
                    "paths": [{"from": "start", "to": "living"}],
                    "default_start_point": "start",
                },
                "lighting": {
                    "preset": "warm",
                    "time_of_day": "evening",
                    "ambient_intensity": 0.8,
                },
                "copilot_policy": {
                    "enabled": True,
                    "languages": ["en", "te"],
                    "default_language": "en",
                    "personality": "helpful_guide",
                },
                "performance_budget": {
                    "target_fps": 60,
                    "max_triangles": 100000,
                    "max_draw_calls": 50,
                    "texture_budget_mb": 100,
                },
            }
        }
    )


# Generation Pipeline Types
class GenerationJob(BaseModel):
    id: str
    project_id: int
    spec_id: int
    type: Literal["spec", "scene", "validation"]
    status: Literal["pending", "running", "completed", "failed"]
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssetReference(BaseModel):
    id: str
    type: Literal["model", "texture", "audio", "material"]
    uri: str
    fallback_uri: Optional[str] = None
    lod_levels: Optional[int] = None
    required: bool = True
    estimated_triangles: int = 0
    estimated_size_mb: float = 0.0


class AssetManifest(BaseModel):
    assets: List[AssetReference]
    total_size_mb: float
    estimated_load_time_ms: int
