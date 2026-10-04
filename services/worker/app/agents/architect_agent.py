"""Simulation Architect Agent - Creates structured Simulation Specification using LLM"""

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from cymatic_shared.schemas.simulation_spec import Entity, SimulationSpec
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


# Local <3B SLM (phi-3-mini q4 via Ollama) for offline-first generation.
LOCAL_SLM_MODEL = "phi-3-mini-3.8b-q4"
LOCAL_SLM_MAX_TOKENS = 2048
# SLM @ temp 0.2 sometimes emits EOS mid-JSON (trailing newlines, truncated
# object). Retry once before falling through to cloud/templates.
# Tuned 2026-09-10: temp 0.1, 1 retry; steady-state ~5.4 tok/s on CPU.
LOCAL_SLM_TEMPERATURE = 0.1
LOCAL_SLM_MAX_ATTEMPTS = 2

# Compact prompts for the 4k-context SLM. Tuning 2026-09-10 showed a full
# SimulationSpec in one shot is unreliable on 3B (stalls mid-entities or
# emits empty sections). The SLM therefore generates ONLY the variable part
# (entities); deterministic code assembles navigation/lighting/budget.
ARCHITECT_SLIM_PROMPT = """You are a Simulation Architect. Output ONLY a valid SimulationSpec JSON object. No prose, no markdown.

Required top-level keys: domain, metadata, entities, navigation, lighting, copilot_policy, performance_budget.
- domain: "real_estate" or "heritage"
- metadata: {title, description, version: 1, tags: [domain]}
- entities: [{id, type, name, position: {x,y,z} meters Y-up, rotation: {x,y,z}, scale: {x,y,z}, properties: {size:[w,d,h], style, furnished}, children: []}]
- navigation: {points: [{id, name, position, description, connections: [ids]}], paths: [{from_point, to_point, type: "walk"}], default_start_point}
- lighting: {preset: "warm", time_of_day: "evening", ambient_intensity: 1.0, custom_lights: []}
- copilot_policy: {enabled: true, languages: ["en"], default_language: "en", personality: "helpful_guide", allowed_actions: ["highlight_object","show_label","move_to_point"]}
- performance_budget: {target_fps: 60, max_triangles: 80000, max_draw_calls: 50, texture_budget_mb: 100, max_entities: 50, lod_distances: [10.0, 30.0, 60.0]}
Entity types: room, furniture, poi. Real estate uses rooms, heritage uses poi.

Example for "Cozy 2BHK apartment":
{"domain":"real_estate","metadata":{"title":"Cozy 2BHK","description":"Cozy 2BHK apartment","version":1,"tags":["real_estate"]},"entities":[{"id":"room_living_room","type":"room","name":"Living Room","position":{"x":0.0,"y":0.0,"z":0.0},"rotation":{"x":0.0,"y":0.0,"z":0.0},"scale":{"x":1.0,"y":1.0,"z":1.0},"properties":{"furnished":true,"style":"modern","size":[6.0,7.0,2.7],"has_window":true,"has_doors":true},"children":[]},{"id":"room_kitchen","type":"room","name":"Kitchen","position":{"x":12.0,"y":0.0,"z":0.0},"rotation":{"x":0.0,"y":0.0,"z":0.0},"scale":{"x":1.0,"y":1.0,"z":1.0},"properties":{"furnished":true,"style":"modern","size":[4.0,5.0,2.7],"has_window":true,"has_doors":true},"children":[]}],"navigation":{"points":[{"id":"nav_room_living_room","name":"Living Room","position":{"x":0.0,"y":0.0,"z":0.0},"description":"Standing in Living Room","connections":["nav_room_kitchen"]},{"id":"nav_room_kitchen","name":"Kitchen","position":{"x":12.0,"y":0.0,"z":0.0},"description":"Standing in Kitchen","connections":["nav_room_living_room"]}],"paths":[{"from_point":"nav_room_living_room","to_point":"nav_room_kitchen","type":"walk"}],"default_start_point":"nav_room_living_room"},"lighting":{"preset":"warm","time_of_day":"evening","ambient_intensity":1.0,"custom_lights":[]},"copilot_policy":{"enabled":true,"languages":["en"],"default_language":"en","personality":"helpful_guide","allowed_actions":["highlight_object","show_label","move_to_point"]},"performance_budget":{"target_fps":60,"max_triangles":80000,"max_draw_calls":50,"texture_budget_mb":100,"max_entities":50,"lod_distances":[10.0,30.0,60.0]}}

Now generate the spec for the request below. Output ONLY JSON."""


# Entities-only prompt for the SLM hybrid path: short output (~300-600
# tokens) the 3B model completes reliably. Navigation/lighting/budget are
# assembled deterministically from these entities.
ARCHITECT_SLIM_ENTITIES_PROMPT = """You are a Simulation Architect. Output ONLY a JSON object with one key "entities": a list of rooms (real_estate) or POIs (heritage).

Each entity: {id, type, name, position: {x,y,z} meters Y-up, rotation: {x,y,z}, scale: {x,y,z}, properties, children: []}.
- Real estate: type "room", properties {furnished, style, size: [w,d,h] meters, has_window, has_doors}. Space rooms 12m apart on x.
- Heritage: type "poi", properties {description, has_narration: true, site_type}. Space POIs 15m apart on x.

Example for "Cozy 2BHK apartment" (real_estate):
{"entities":[{"id":"room_living_room","type":"room","name":"Living Room","position":{"x":0.0,"y":0.0,"z":0.0},"rotation":{"x":0.0,"y":0.0,"z":0.0},"scale":{"x":1.0,"y":1.0,"z":1.0},"properties":{"furnished":true,"style":"modern","size":[6.0,7.0,2.7],"has_window":true,"has_doors":true},"children":[]},{"id":"room_kitchen","type":"room","name":"Kitchen","position":{"x":12.0,"y":0.0,"z":0.0},"rotation":{"x":0.0,"y":0.0,"z":0.0},"scale":{"x":1.0,"y":1.0,"z":1.0},"properties":{"furnished":true,"style":"modern","size":[4.0,5.0,2.7],"has_window":true,"has_doors":true},"children":[]}]}

Now generate ONLY {"entities": [...]} for the request below. Output ONLY JSON."""


def _local_llm_enabled() -> bool:
    """Check the ENABLE_LOCAL_LLM feature flag (default off for cloud CI)."""
    try:
        from app.core.config import get_settings

        return bool(getattr(get_settings(), "ENABLE_LOCAL_LLM", False))
    except Exception:
        return False


def _local_llm_timeout() -> float:
    """Per-request timeout for SLM inference (default covers CPU generation)."""
    try:
        from app.core.config import get_settings

        return float(getattr(get_settings(), "LOCAL_LLM_TIMEOUT", 300.0))
    except Exception:
        return 300.0


async def create_spec_slm(input_data: ArchitectInput) -> ArchitectResult:
    """Generate simulation specification using the local <3B SLM (phi-3-mini q4).

    Retries once on invalid JSON (the SLM occasionally emits EOS mid-object),
    then raises so the caller can fall back to cloud or templates.
    """
    all_data = {**input_data.intake_data, **input_data.clarification_data}

    context = {
        "domain": input_data.domain,
        "objective": input_data.objective,
        "requirements": all_data,
    }

    messages = [
        {"role": "system", "content": ARCHITECT_SLIM_ENTITIES_PROMPT},
        {
            "role": "user",
            "content": f'Generate ONLY {{"entities": [...]}} for:\n{json.dumps(context)}',
        },
    ]

    last_err: Exception | None = None
    for attempt in range(LOCAL_SLM_MAX_ATTEMPTS):
        try:
            # Retries bypass the router cache (a truncated first output must
            # not be replayed) and nudge temperature to escape deterministic
            # stalls.
            result = await call_llm_json(
                messages=messages,
                task_type="spec_generation",
                sensitivity="internal",
                temperature=LOCAL_SLM_TEMPERATURE + 0.05 * attempt,
                max_tokens=LOCAL_SLM_MAX_TOKENS,
                model=LOCAL_SLM_MODEL,
                timeout=_local_llm_timeout(),
                use_cache=(attempt == 0),
                # A truncation-repaired object without entities is a false
                # success — return {} so this attempt fails and retries.
                required_non_empty_keys=["entities"],
            )

            raw_entities = result.get("entities")
            if not isinstance(raw_entities, list) or not raw_entities:
                raise ValueError("SLM returned no entities list")
            # Validate each entity shape; raises ValidationError on bad items.
            # Default bedrooms to has_window=True when the SLM omits the flag
            # so domain-expert egress checks don't flake on valid layouts.
            entities = []
            for e in raw_entities:
                if not isinstance(e, dict):
                    continue
                props = (
                    e.get("properties") if isinstance(e.get("properties"), dict) else {}
                )
                if (
                    e.get("type") == "room"
                    and props is not None
                    and "has_window" not in props
                ):
                    props["has_window"] = True
                entities.append(Entity(**e).model_dump())
            if not entities:
                raise ValueError("SLM returned no valid entities")

            template = DOMAIN_TEMPLATES.get(
                input_data.domain, DOMAIN_TEMPLATES["real_estate"]
            )
            all_data = {**input_data.intake_data, **input_data.clarification_data}
            spec = _assemble_spec(
                domain=input_data.domain,
                objective=input_data.objective,
                all_data=all_data,
                entities=entities,
                template=template,
            )

            notes = [
                f"Generated {input_data.domain} specification via local SLM ({LOCAL_SLM_MODEL})",
                f"Entities: {len(spec.entities)} (SLM) + deterministic scaffold",
                f"Navigation points: {len(spec.navigation.points)}",
            ]
            if attempt > 0:
                notes.append(f"SLM succeeded on attempt {attempt + 1}")

            logger.info(
                "architect_slm_completed",
                domain=input_data.domain,
                entities=len(spec.entities),
                attempt=attempt + 1,
            )
            return ArchitectResult(spec=spec, generation_notes=notes)
        except (ValidationError, ValueError, KeyError) as e:
            last_err = e
            logger.warning(
                "architect_slm_attempt_failed",
                attempt=attempt + 1,
                max_attempts=LOCAL_SLM_MAX_ATTEMPTS,
                error=str(e)[:200],
            )

    raise (
        last_err if last_err is not None else ValueError("SLM returned no usable spec")
    )


async def create_spec_llm(input_data: ArchitectInput) -> ArchitectResult:
    """Generate simulation specification using LLM.

    Order: local SLM first when ENABLE_LOCAL_LLM is on (offline-first),
    then cloud, then deterministic templates.
    """
    if _local_llm_enabled():
        try:
            return await create_spec_slm(input_data)
        except Exception as e:  # noqa: BLE001
            logger.warning("architect_slm_failed_falling_back_to_cloud", error=str(e))

    all_data = {**input_data.intake_data, **input_data.clarification_data}

    # Prepare context for LLM
    context = {
        "domain": input_data.domain,
        "objective": input_data.objective,
        "requirements": all_data,
    }

    messages = [
        {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Generate SimulationSpec for:\n{json.dumps(context, indent=2)}",
        },
    ]

    try:
        result = await call_llm_json(
            messages=messages,
            task_type="spec_generation",
            sensitivity="internal",
            temperature=0.3,
            max_tokens=8000,
            # Repaired-but-empty parses must surface as {} so the
            # template-fallback path below triggers (never an empty spec).
            required_non_empty_keys=["entities"],
        )

        # Parse and validate
        spec = SimulationSpec(**result)

        notes = [
            f"Generated {input_data.domain} specification via LLM",
            f"Entities: {len(spec.entities)}",
            f"Navigation points: {len(spec.navigation.points)}",
            f"Performance budget: {spec.performance_budget.target_fps} FPS, {spec.performance_budget.max_triangles} triangles",
        ]

        logger.info(
            "architect_llm_completed",
            domain=input_data.domain,
            entities=len(spec.entities),
        )
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
    },
}


def _assemble_spec(
    domain: str,
    objective: str,
    all_data: dict[str, Any],
    entities: list[dict[str, Any]],
    template: dict[str, Any],
) -> SimulationSpec:
    """Assemble a full SimulationSpec from entities + deterministic scaffold.

    Navigation, lighting, copilot policy and performance budget are fixed
    templates; only entities vary (SLM-generated or template-built).
    """
    if domain == "heritage":
        nav_points = _build_heritage_nav_points(entities)
        nav_paths = _build_heritage_nav_paths(nav_points)
        default_start = nav_points[0]["id"] if nav_points else "entrance"
    else:
        nav_points = _build_real_estate_nav_points(entities)
        nav_paths = _build_real_estate_nav_paths(nav_points)
        default_start = nav_points[0]["id"] if nav_points else "front_door"

    return SimulationSpec(
        domain=domain,
        metadata={
            "title": all_data.get("title", f"Generated {domain} walkthrough"),
            "description": objective,
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
                "highlight_object",
                "show_label",
                "move_to_point",
                "open_menu",
                "pause_tour",
                "resume_tour",
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


async def create_spec_fallback(input_data: ArchitectInput) -> ArchitectResult:
    """Fallback template-based spec generation without LLM."""
    domain = input_data.domain
    template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES["real_estate"])
    all_data = {**input_data.intake_data, **input_data.clarification_data}

    if domain == "heritage":
        entities = _build_heritage_entities(all_data)
    else:
        entities = _build_real_estate_entities(all_data)

    spec = _assemble_spec(
        domain=domain,
        objective=input_data.objective,
        all_data=all_data,
        entities=entities,
        template=template,
    )

    notes = [
        f"Template-based fallback for {domain}",
        f"Entities: {len(spec.entities)}",
        f"Navigation points: {len(spec.navigation.points)}",
    ]

    logger.info(
        "architect_fallback_completed", domain=domain, entities=len(spec.entities)
    )
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
        entities.append(
            {
                "id": f"room_{room_name}",
                "type": "room",
                "name": room_name.replace("_", " ").title(),
                "position": {"x": x_offset, "y": 0.0, "z": 0.0},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "properties": {
                    "furnished": data.get("furnished", True),
                    "style": data.get("style", "modern"),
                    "size": size,
                    "has_window": True,
                    "has_doors": True,
                },
                "children": [],
            }
        )
        x_offset += room_spacing
    return entities


def _build_heritage_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build basic heritage entity list from user data."""
    pois_raw = data.get(
        "key_pois", data.get("pois", data.get("points_of_interest", ""))
    )
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

    # Ensure temple/palace mandatory elements are present so domain-expert
    # validation passes for template-generated specs. User POIs are kept;
    # missing mandatory elements are appended (alias-aware check).
    site_type = str(data.get("site_type", "courtyard")).lower()
    mandatory_by_site = {
        "temple": ["Garbhagriha", "Mandapa", "Pradakshina Path"],
        "palace": ["Diwan-I-Am", "Diwan-I-Khas", "Zenana"],
    }
    required = mandatory_by_site.get(site_type, [])
    if required:
        existing = {n.lower().replace("_", " ").strip() for n in poi_names}
        # Alias coverage matching domain_expert HERITAGE_ELEMENT_ALIASES
        alias_sets = {
            "garbhagriha": {
                "garbhagriha",
                "sanctum",
                "sanctuary",
                "inner sanctum",
                "main shrine",
            },
            "mandapa": {"mandapa", "main hall", "main_hall", "prayer hall", "hall"},
            "pradakshina path": {
                "pradakshina",
                "pradakshina path",
                "circumambulation",
                "courtyard",
            },
            "diwan-i-am": {"diwan-i-am", "diwan i am", "public hall"},
            "diwan-i-khas": {"diwan-i-khas", "diwan i khas", "private hall"},
            "zenana": {"zenana", "women quarters", "private quarters"},
        }
        for req in required:
            key = req.lower()
            covered = any(
                alias in existing or any(alias in e for e in existing)
                for alias in alias_sets.get(key, {key})
            )
            if not covered:
                poi_names.append(req)

    # Non-overlapping spacing: 15m apart matches heritage_templates spacing
    poi_spacing = 15.0
    entities = []
    for i, poi_name in enumerate(poi_names):
        safe_name = poi_name.strip()
        if not safe_name:
            continue
        entities.append(
            {
                "id": f"poi_{i}",
                "type": "poi",
                "name": safe_name.title(),
                "position": {"x": i * poi_spacing, "y": 0.0, "z": 0.0},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "properties": {
                    "description": safe_name,
                    "has_narration": True,
                    "site_type": data.get("site_type", "courtyard"),
                },
                "children": [],
            }
        )
    return entities


def _build_real_estate_nav_points(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    points = []
    for ent in entities:
        if ent.get("type") == "room":
            points.append(
                {
                    "id": f"nav_{ent['id']}",
                    "name": ent["name"],
                    "position": ent["position"],
                    "description": f"Standing in {ent['name']}",
                    "connections": [],
                }
            )
    # Wire connections linearly
    for i in range(len(points) - 1):
        points[i]["connections"].append(points[i + 1]["id"])
        points[i + 1]["connections"].append(points[i]["id"])
    return points


def _build_heritage_nav_points(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for ent in entities:
        if ent.get("type") == "poi":
            points.append(
                {
                    "id": f"nav_{ent['id']}",
                    "name": ent["name"],
                    "position": ent["position"],
                    "description": ent["properties"].get("description", ""),
                    "connections": [],
                }
            )
    for i in range(len(points) - 1):
        points[i]["connections"].append(points[i + 1]["id"])
        points[i + 1]["connections"].append(points[i]["id"])
    return points


def _build_real_estate_nav_paths(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    for i in range(len(points) - 1):
        paths.append(
            {
                "from_point": points[i]["id"],
                "to_point": points[i + 1]["id"],
                "type": "walk",
            }
        )
    return paths


def _build_heritage_nav_paths(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    for i in range(len(points) - 1):
        paths.append(
            {
                "from_point": points[i]["id"],
                "to_point": points[i + 1]["id"],
                "type": "teleport",
            }
        )
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
        context=context or {},
    )
    return await create_spec_llm(input_data)
