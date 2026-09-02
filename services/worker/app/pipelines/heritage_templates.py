"""Heritage Templates - Pre-built heritage walkthrough configurations"""
from typing import Dict, Any, List
from cymatic_shared.schemas.simulation_spec import (
    SimulationSpec, SpecMetadata, Entity, NavigationSpec, NavigationPoint,
    NavigationPath, LightingSpec, CopilotPolicy, PerformanceBudget
)
from datetime import datetime
import uuid


class HeritageTemplateLibrary:
    """Library of pre-built heritage templates"""
    
    TEMPLATES = {
        "temple_south_indian": {
            "name": "South Indian Temple",
            "description": "Traditional Dravidian temple with gopuram, mandapa, and garbhagriha",
            "site_type": "temple",
            "historical_period": "Chola Dynasty (9th-13th century)",
            "culture": "Tamil",
            "default_pois": [
                "rajagopuram_entrance",
                "mandapa_hall",
                "garbhagriha_sanctum",
                "pradakshina_path",
                "temple_tank",
                "nandi_mandapa"
            ],
            "layout": "axial",
            "narration_style": "spiritual",
            "recommended_languages": ["en", "ta", "te", "hi"],
        },
        "temple_north_indian": {
            "name": "North Indian Temple",
            "description": "Nagara style temple with shikhara and mandapa",
            "site_type": "temple",
            "historical_period": "Gupta Period (4th-6th century)",
            "culture": "Hindi/Sanskrit",
            "default_pois": [
                "main_entrance",
                "mandapa",
                "garbhagriha",
                "shikhara_view",
                "circumambulation_path"
            ],
            "layout": "axial",
            "narration_style": "spiritual",
            "recommended_languages": ["en", "hi", "sa"],
        },
        "mughal_palace": {
            "name": "Mughal Palace",
            "description": "Grand Mughal palace with diwan-i-am, diwan-i-khas, and zenana",
            "site_type": "palace",
            "historical_period": "Mughal Empire (16th-18th century)",
            "culture": "Persian/Urdu",
            "default_pois": [
                "main_gate",
                "diwan_i_am",
                "diwan_i_khas",
                "zenana_quarters",
                "royal_gardens",
                "armory",
                "hammam"
            ],
            "layout": "courtyard_sequence",
            "narration_style": "historical",
            "recommended_languages": ["en", "ur", "hi", "fa"],
        },
        "rajput_palace": {
            "name": "Rajput Palace",
            "description": "Rajput hill palace with jharokha, chhatri, and courtyards",
            "site_type": "palace",
            "historical_period": "Rajput Period (7th-18th century)",
            "culture": "Rajasthani",
            "default_pois": [
                "main_gate",
                "outer_courtyard",
                "diwan_i_khas",
                "zenana",
                "chhatri_towers",
                "stepwell",
                "temple_complex"
            ],
            "layout": "courtyard_sequence",
            "narration_style": "cultural",
            "recommended_languages": ["en", "hi", "raj"],
        },
        "haveli_courtyard": {
            "name": "Haveli Courtyard",
            "description": "Traditional haveli with chowk, jali, and otla",
            "site_type": "courtyard",
            "historical_period": "18th-19th century",
            "culture": "Gujarati/Rajasthani",
            "default_pois": [
                "entrance_gate",
                "outer_chowk",
                "central_fountain",
                "baradari",
                "side_pavilions",
                "otla_seating",
                "service_areas"
            ],
            "layout": "enclosed_courtyard",
            "narration_style": "cultural",
            "recommended_languages": ["en", "gu", "hi"],
        },
        "islamic_monument": {
            "name": "Islamic Monument",
            "description": "Mausoleum or mosque with dome, minarets, and gardens",
            "site_type": "monument",
            "historical_period": "Various Islamic periods",
            "culture": "Islamic",
            "default_pois": [
                "main_gateway",
                "courtyard",
                "prayer_hall",
                "mihrab",
                "minarets",
                "dome_interior",
                "charbagh_gardens"
            ],
            "layout": "radial",
            "narration_style": "spiritual",
            "recommended_languages": ["en", "ar", "ur", "fa", "tr"],
        },
        "buddhist_stupa": {
            "name": "Buddhist Stupa",
            "description": "Stupa complex with vihara, chaitya, and pradakshina path",
            "site_type": "temple",
            "historical_period": "Mauryan to Gupta (3rd BCE - 6th CE)",
            "culture": "Buddhist",
            "default_pois": [
                "stupa_base",
                "harmika",
                "yasti",
                "chatra",
                "pradakshina_path",
                "vihara_monastery",
                "chaitya_hall"
            ],
            "layout": "radial",
            "narration_style": "spiritual",
            "recommended_languages": ["en", "hi", "pi", "sa"],
        },
    }
    
    @classmethod
    def get_template(cls, template_id: str) -> Dict[str, Any]:
        """Get template by ID"""
        return cls.TEMPLATES.get(template_id, cls.TEMPLATES["haveli_courtyard"])
    
    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        """List all available templates"""
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "site_type": t["site_type"],
                "historical_period": t["historical_period"],
                "culture": t["culture"],
            }
            for tid, t in cls.TEMPLATES.items()
        ]


def create_heritage_spec_from_template(
    template_id: str,
    project_name: str,
    customizations: Dict[str, Any] = None
) -> "SimulationSpec":
    """Create a SimulationSpec from a heritage template"""
    template = HeritageTemplateLibrary.get_template(template_id)
    custom = customizations or {}
    
    # Merge template defaults with customizations
    site_type = custom.get("site_type", template["site_type"])
    pois = custom.get("key_pois", template["default_pois"])
    layout = template["layout"]
    narration = template["narration_style"]
    languages = custom.get("languages", template["recommended_languages"])
    
    # Generate entities
    entities = []
    entity_id = 0
    
    def next_id(prefix: str) -> str:
        nonlocal entity_id
        entity_id += 1
        return f"{prefix}_{entity_id}"
    
    spacing = 15
    x_pos = 0
    z_pos = 0
    
    for i, poi_name in enumerate(pois):
        poi_name = poi_name.strip()
        if not poi_name:
            continue
        
        if layout == "axial":
            # Linear arrangement
            entities.append(Entity(
                id=next_id("poi"),
                type="poi",
                name=poi_name.replace("_", " ").title(),
                position=[x_pos, 0, z_pos],
                properties={
                    "description": f"Key point of interest: {poi_name}",
                    "site_type": site_type,
                    "historical_significance": "high",
                    "has_narration": True,
                    "indoor": True,
                }
            ))
            x_pos += spacing
            
        elif layout == "courtyard_sequence":
            # Courtyard arrangement
            entities.append(Entity(
                id=next_id("poi"),
                type="poi",
                name=poi_name.replace("_", " ").title(),
                position=[x_pos, 0, z_pos],
                properties={
                    "description": f"Key area: {poi_name}",
                    "site_type": site_type,
                    "has_narration": True,
                    "indoor": True,
                }
            ))
            x_pos += spacing
            if x_pos > spacing * 2:
                x_pos = 0
                z_pos += spacing
                
        elif layout == "radial":
            # Circular arrangement
            import math
            angle = (2 * math.pi * i) / max(len(pois), 1)
            radius = spacing + 10
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            
            entities.append(Entity(
                id=next_id("poi"),
                type="poi",
                name=poi_name.replace("_", " ").title(),
                position=[x, 0, z],
                properties={
                    "description": f"Key point: {poi_name}",
                    "site_type": site_type,
                    "has_narration": True,
                    "indoor": True,
                }
            ))
            
        elif layout == "enclosed_courtyard":
            # Courtyard with central feature
            if i == 0:
                # Central feature
                entities.append(Entity(
                    id=next_id("poi"),
                    type="poi",
                    name="Central Courtyard",
                    position=[0, 0, 0],
                    properties={
                        "description": "Central courtyard with fountain",
                        "is_courtyard_center": True,
                        "has_narration": True,
                    }
                ))
            else:
                # Surrounding POIs
                entities.append(Entity(
                    id=next_id("poi"),
                    type="poi",
                    name=poi_name.replace("_", " ").title(),
                    position=[x_pos, 0, z_pos],
                    properties={
                        "description": f"Pavilion: {poi_name}",
                        "has_narration": True,
                    }
                ))
                x_pos += spacing
                if x_pos > spacing * 2:
                    x_pos = 0
                    z_pos += spacing
    
    # Add entrance
    entities.append(Entity(
        id=next_id("poi"),
        type="poi",
        name="Main Entrance",
        position=[0, 0, -spacing] if layout != "enclosed_courtyard" else [-spacing, 0, 0],
        properties={
            "description": "Primary entrance to the heritage site",
            "is_entrance": True,
            "has_narration": True,
        }
    ))
    
    # Add ambient light
    entities.append(Entity(
        id=next_id("light"),
        type="light",
        name="Ambient Light",
        position=[0, 20, 0],
        properties={
            "light_type": "directional",
            "intensity": 1.0,
            "color": [1.0, 0.95, 0.85]
        }
    ))
    
    # Create navigation
    nav_points = []
    nav_paths = []
    
    for i, entity in enumerate(entities):
        if entity.type == "poi":
            nav_points.append(NavigationPoint(
                id=f"nav_{entity.id}",
                name=entity.name,
                position=entity.position,
                description=f"Visit {entity.name}",
                connections=[]
            ))
    
    # Create paths based on layout
    if layout == "axial" or layout == "courtyard_sequence":
        for i in range(len(nav_points) - 1):
            nav_paths.append(NavigationPath(
                from_point=nav_points[i].id,
                to=nav_points[i + 1].id,
                type="walk"
            ))
        # Return path
        if len(nav_points) > 2:
            nav_paths.append(NavigationPath(
                from_point=nav_points[-1].id,
                to=nav_points[0].id,
                type="walk"
            ))
    elif layout == "radial" or layout == "enclosed_courtyard":
        # Center to each POI
        center_point = nav_points[0] if nav_points else None
        if center_point:
            for point in nav_points[1:]:
                nav_paths.append(NavigationPath(
                    from_point=center_point.id,
                    to=point.id,
                    type="walk"
                ))
            # Connect adjacent
            for i in range(1, len(nav_points)):
                next_i = (i % (len(nav_points) - 1)) + 1
                nav_paths.append(NavigationPath(
                    from_point=nav_points[i].id,
                    to=nav_points[next_i].id,
                    type="walk"
                ))
    
    # Update connections
    for path in nav_paths:
        for point in nav_points:
            if point.id == path.from_point:
                if path.to not in point.connections:
                    point.connections.append(path.to)
            if point.id == path.to:
                if path.from_point not in point.connections:
                    point.connections.append(path.from_point)
    
    default_start = nav_points[0].id if nav_points else "start"
    
    # Create spec
    spec = SimulationSpec(
        domain="heritage",
        metadata=SpecMetadata(
            title=custom.get("title", f"{template['name']} Walkthrough"),
            description=custom.get("description", template["description"]),
            version="1.0.0",
            tags=["heritage", template["site_type"], template["culture"]]
        ),
        entities=entities,
        navigation=NavigationSpec(
            points=nav_points,
            paths=nav_paths,
            default_start_point=default_start
        ),
        lighting=LightingSpec(
            preset="golden_hour",
            time_of_day="morning",
            ambient_intensity=0.8
        ),
        copilot_policy=CopilotPolicy(
            enabled=True,
            languages=languages,
            default_language=languages[0] if languages else "en",
            personality="expert_narrator",
        ),
        performance_budget=PerformanceBudget(
            target_fps=60,
            max_triangles=100000,
            max_draw_calls=50,
            texture_budget_mb=100,
            max_entities=500,
            lod_distances=[10.0, 25.0, 50.0]
        )
    )
    
    return spec


def get_heritage_asset_catalog(site_type: str) -> Dict[str, List[str]]:
    """Get asset catalog for heritage site type"""
    catalogs = {
        "temple": {
            "architecture": [
                "models/temple/gopuram.glb",
                "models/temple/mandapa.glb",
                "models/temple/garbhagriha.glb",
                "models/temple/pillar.glb",
                "models/temple/vimana.glb",
            ],
            "decor": [
                "models/temple/nandi.glb",
                "models/temple/deepam.glb",
                "models/temple/bell.glb",
            ],
            "nature": [
                "models/nature/banyan_tree.glb",
                "models/nature/temple_tank.glb",
            ]
        },
        "palace": {
            "architecture": [
                "models/palace/gate.glb",
                "models/palace/diwan_hall.glb",
                "models/palace/jharokha.glb",
                "models/palace/chhatri.glb",
                "models/palace/arch.glb",
            ],
            "decor": [
                "models/palace/fountain.glb",
                "models/palace/rug.glb",
                "models/palace/chandelier.glb",
            ],
            "nature": [
                "models/nature/garden.glb",
                "models/nature/charbagh.glb",
            ]
        },
        "courtyard": {
            "architecture": [
                "models/haveli/gate.glb",
                "models/haveli/chowk.glb",
                "models/haveli/baradari.glb",
                "models/haveli/jali.glb",
            ],
            "decor": [
                "models/haveli/fountain.glb",
                "models/haveli/otla.glb",
                "models/haveli/swing.glb",
            ],
            "nature": [
                "models/nature/tulsi_plant.glb",
                "models/nature/courtyard_tree.glb",
            ]
        },
        "monument": {
            "architecture": [
                "models/monument/base.glb",
                "models/monument/dome.glb",
                "models/monument/minaret.glb",
                "models/monument/arch.glb",
            ],
            "decor": [
                "models/monument/inscription.glb",
                "models/monument/geometric_pattern.glb",
            ],
            "nature": [
                "models/nature/charbagh.glb",
                "models/nature/reflecting_pool.glb",
            ]
        }
    }
    return catalogs.get(site_type, catalogs["courtyard"])