"""Simulation Architect Agent - Creates structured Simulation Specification using LLM"""
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from cymatic_shared.schemas.simulation_spec import SimulationSpec
import structlog
from app.core.llm_client import call_llm_json

logger = structlog.get_logger()


class ArchitectInput(BaseModel):
    domain: str
    objective: str
    intake_data: dict[str, Any]
    clarification_data: dict[str, Any]
    context: dict[str, Any] = {}


class ArchitectResult(BaseModel):
    spec: SimulationSpec
    generation_notes: list[str] = []


ARCHITECT_SYSTEM_PROMPT = """You are a Simulation Architect. Generate a complete, valid Simulation Specification JSON.

Input: domain, objective, intake data, clarification data
Output: Full SimulationSpec matching the schema exactly.

Schema requirements:
- domain: "real_estate" or "heritage"
- metadata: {title, description, version, tags}
- entities: array of {id, type, name, position[x,y,z], rotation?, scale?, properties, children?}
- navigation: {points[{id,name,position,description,connections}], paths[{from,to,type}], default_start_point}
- lighting: {preset, time_of_day, ambient_intensity, sun_direction?, custom_lights?}
- copilot_policy: {enabled, languages, default_language, personality, allowed_actions, knowledge_base?}
- performance_budget: {target_fps, max_triangles, max_draw_calls, texture_budget_mb, max_entities, lod_distances}

Entity types: room, wall, floor, ceiling, door, window, furniture, decoration, light, navigation_point, poi, audio_zone, trigger_zone
Navigation path types: walk, teleport
Lighting presets: warm, cool, neutral, golden_hour, blue_hour, custom
Copilot personalities: helpful_guide, expert_narrator, friendly_assistant, professional_host
Copilot actions: highlight_object, show_label, move_to_point, open_menu, change_material, pause_tour, resume_tour, play_audio_hint, answer_question

Guidelines:
- Positions in meters, Y-up coordinate system
- Real estate: rooms as entities, linear navigation
- Heritage: POIs as entities, radial/courtyard navigation
- Include proper navigation connections
- Performance budget appropriate for mobile VR (target 60 FPS, <100k triangles)
- Copilot enabled with multi-language support (en, te minimum)"""


async def create_spec_llm(input_data: ArchitectInput) -> ArchitectResult:
    """Generate simulation specification using LLM."""
    all_data = {**input_data.intake_data, **input_data.clarification_data}
    
    # Prepare context for LLM
    context = {
        "domain": input_data.domain,
        "objective": input_data.objective,
        "requirements": all_data,
    }
    
    messages = [
        {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Generate SimulationSpec for:\n{json.dumps(context, indent=2)}"}
    ]
    
    try:
        result = await call_llm_json(
            messages=messages,
            task_type="spec_generation",
            sensitivity="internal",
            temperature=0.3,
            max_tokens=8000,
        )

        # Parse and validate
        spec = SimulationSpec(**result)

        notes = [
            f"Generated {input_data.domain} specification via LLM",
            f"Entities: {len(spec.entities)}",
            f"Navigation points: {len(spec.navigation.points)}",
            f"Performance budget: {spec.performance_budget.target_fps} FPS, {spec.performance_budget.max_triangles} triangles"
        ]

        logger.info("architect_llm_completed", domain=input_data.domain, entities=len(spec.entities))
        return ArchitectResult(spec=spec, generation_notes=notes)

    except (ValidationError, ValueError, KeyError, OSError) as e:
        logger.error("architect_llm_failed", error=str(e))
        # Fallback to template-based
        try:
            return await create_spec_fallback(input_data)
        except Exception as fallback_err:  # noqa: BLE001
            logger.error("architect_fallback_failed", error=str(fallback_err))
            raise
    except Exception as e:  # noqa: BLE001
        logger.error("architect_llm_failed_unexpected", error=str(e))
        # Fallback to template-based for any unexpected error
        try:
            return await create_spec_fallback(input_data)
        except Exception as fallback_err:  # noqa: BLE001
            logger.error("architect_fallback_failed", error=str(fallback_err))
            raise


# Fallback implementation (template-based)
DOMAIN_TEMPLATES = {
    "real_estate": {
        "lighting_preset": "warm",
        "time_of_day": "evening",
        "copilot_personality": "helpful_guide",
        "default_rooms": ["living_room", "kitchen", "master_bedroom", "bathroom"],
        "navigation_style": "walk",
    },
    "heritage": {
        "lighting_preset": "golden_hour",
        "time_of_day": "morning",
        "copilot_personality": "expert_narrator",
        "default_pois": ["entrance", "main_hall", "sanctuary", "courtyard"],
        "navigation_style": "teleport",
    }
}


async def create_spec_fallback(input_data: ArchitectInput) -> ArchitectResult:
    """Fallback template-based spec generation without LLM."""
    domain = input_data.domain
    template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES["real_estate"])
    all_data = {**input_data.intake_data, **input_data.clarification_data}

    if domain == "heritage":
        entities = _build_heritage_entities(all_data)
        nav_points = _build_heritage_nav_points(entities)
        nav_paths = _build_heritage_nav_paths(nav_points)
        default_start = nav_points[0]["id"] if nav_points else "entrance"
    else:
        entities = _build_real_estate_entities(all_data)
        nav_points = _build_real_estate_nav_points(entities)
        nav_paths = _build_real_estate_nav_paths(nav_points)
        default_start = nav_points[0]["id"] if nav_points else "front_door"

    spec = SimulationSpec(
        domain=domain,
        metadata={
            "title": all_data.get("title", f"Generated {domain} walkthrough"),
            "description": input_data.objective,
            "version": 1,
            "tags": [domain],
        },
        entities=entities,
        navigation={
            "points": nav_points,
            "paths": nav_paths,
            "default_start_point": default_start,
        },
        lighting={
            "preset": template.get("lighting_preset", "warm"),
            "time_of_day": template.get("time_of_day", "evening"),
            "ambient_intensity": 1.0,
            "custom_lights": [],
        },
        copilot_policy={
            "enabled": True,
            "languages": ["en"],
            "default_language": "en",
            "personality": template.get("copilot_personality", "helpful_guide"),
            "allowed_actions": [
                "highlight_object", "show_label", "move_to_point",
                "open_menu", "pause_tour", "resume_tour",
            ],
        },
        performance_budget={
            "target_fps": 60,
            "max_triangles": 80000,
            "max_draw_calls": 50,
            "texture_budget_mb": 100,
            "max_entities": 50,
            "lod_distances": [10.0, 30.0, 60.0],
        },
    )

    notes = [
        f"Template-based fallback for {domain}",
        f"Entities: {len(spec.entities)}",
        f"Navigation points: {len(spec.navigation.points)}",
    ]

    logger.info("architect_fallback_completed", domain=domain, entities=len(spec.entities))
    return ArchitectResult(spec=spec, generation_notes=notes)


def _build_real_estate_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build basic real estate entity list from user data."""
    rooms = data.get("rooms", [])
    if not rooms:
        rooms = ["living_room", "kitchen", "master_bedroom", "bathroom"]

    # Non-overlapping spacing: room width ~6m + corridor ~3m + buffer -> 12m
    # Ensures no AABB overlap for even large rooms
    room_spacing = 12.0
    # Also add realistic size property for domain checks
    default_sizes: dict[str, list[float]] = {
        "living_room": [6.0, 7.0, 2.7],
        "kitchen": [4.0, 5.0, 2.7],
        "master_bedroom": [5.0, 5.5, 2.7],
        "bedroom": [4.0, 4.5, 2.4],
        "bathroom": [2.5, 3.0, 2.4],
    }
    entities = []
    x_offset = 0.0
    for room_name in rooms:
        # sanitize room_name (strip, lower, remove empties)
        room_name = str(room_name).strip().lower().replace(" ", "_")
        if not room_name:
            continue
        size = default_sizes.get(room_name, [4.5, 5.0, 2.7])
        entities.append({
            "id": f"room_{room_name}",
            "type": "room",
            "name": room_name.replace("_", " ").title(),
            "position": {"x": x_offset, "y": 0.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            "properties": {"furnished": data.get("furnished", True), "style": data.get("style", "modern"), "size": size, "has_window": True, "has_doors": True},
            "children": [],
        })
        x_offset += room_spacing
    return entities


def _build_heritage_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build basic heritage entity list from user data."""
    pois_raw = data.get("key_pois", data.get("pois", data.get("points_of_interest", "")))
    poi_names: list[str] = []
    if isinstance(pois_raw, list):
        poi_names = [str(p).strip() for p in pois_raw if str(p).strip()]
    elif isinstance(pois_raw, str) and pois_raw.strip():
        # Support comma or newline separated
        import re
        parts = re.split(r"[,\n;]+", pois_raw)
        poi_names = [p.strip() for p in parts if p.strip()]
    if not poi_names:
        poi_names = ["entrance", "main_hall", "sanctuary", "courtyard"]

    # Deduplicate case-insensitive while preserving order
    seen_lower: set[str] = set()
    deduped: list[str] = []
    for n in poi_names:
        low = n.lower()
        if low not in seen_lower:
            seen_lower.add(low)
            deduped.append(n)
    poi_names = deduped

    # Non-overlapping spacing: 15m apart matches heritage_templates spacing
    poi_spacing = 15.0
    entities = []
    for i, poi_name in enumerate(poi_names):
        safe_name = poi_name.strip()
        if not safe_name:
            continue
        entities.append({
            "id": f"poi_{i}",
            "type": "poi",
            "name": safe_name.title(),
            "position": {"x": i * poi_spacing, "y": 0.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            "properties": {"description": safe_name, "has_narration": True, "site_type": data.get("site_type", "courtyard")},
            "children": [],
        })
    return entities


def _build_real_estate_nav_points(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for ent in entities:
        if ent.get("type") == "room":
            points.append({
                "id": f"nav_{ent['id']}",
                "name": ent["name"],
                "position": ent["position"],
                "description": f"Standing in {ent['name']}",
                "connections": [],
            })
    # Wire connections linearly
    for i in range(len(points) - 1):
        points[i]["connections"].append(points[i + 1]["id"])
        points[i + 1]["connections"].append(points[i]["id"])
    return points


def _build_heritage_nav_points(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for ent in entities:
        if ent.get("type") == "poi":
            points.append({
                "id": f"nav_{ent['id']}",
                "name": ent["name"],
                "position": ent["position"],
                "description": ent["properties"].get("description", ""),
                "connections": [],
            })
    for i in range(len(points) - 1):
        points[i]["connections"].append(points[i + 1]["id"])
        points[i + 1]["connections"].append(points[i]["id"])
    return points


def _build_real_estate_nav_paths(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    for i in range(len(points) - 1):
        paths.append({
            "from_point": points[i]["id"],
            "to_point": points[i + 1]["id"],
            "type": "walk",
        })
    return paths


def _build_heritage_nav_paths(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    for i in range(len(points) - 1):
        paths.append({
            "from_point": points[i]["id"],
            "to_point": points[i + 1]["id"],
            "type": "teleport",
        })
    return paths


# Main entry point
async def create_simulation_spec(
    domain: str,
    objective: str,
    intake_data: dict[str, Any],
    clarification_data: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> ArchitectResult:
    """Main architect function - uses LLM with fallback."""
    input_data = ArchitectInput(
        domain=domain,
        objective=objective,
        intake_data=intake_data,
        clarification_data=clarification_data,
        context=context or {}
    )
    return await create_spec_llm(input_data)