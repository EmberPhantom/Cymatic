"""Asset Agent - Selects assets, validates mobile performance, prepares manifest"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from cymatic_shared.schemas.simulation_spec import AssetReference, AssetManifest, Entity
import structlog

logger = structlog.get_logger()


class AssetAgentInput(BaseModel):
    spec_entities: List[Entity]
    domain: str
    performance_budget: Dict[str, Any]
    available_assets: List[Dict[str, Any]] = []


class AssetAgentResult(BaseModel):
    manifest: AssetManifest
    selected_assets: List[AssetReference]
    substitutions: List[Dict[str, Any]] = []  # Original -> substituted
    warnings: List[str] = []


class AssetAgent:
    """Selects and prepares assets for scene generation."""
    
    # Asset mappings by entity type and style
    ASSET_CATALOG = {
        "real_estate": {
            "room": {
                "modern": {
                    "living_room": ["models/living_modern.glb", "models/sofa_modern.glb", "models/tv_stand.glb"],
                    "kitchen": ["models/kitchen_modern.glb", "models/fridge.glb", "models/oven.glb"],
                    "bedroom": ["models/bed_modern.glb", "models/wardrobe.glb", "models/nightstand.glb"],
                    "bathroom": ["models/bathroom_modern.glb", "models/toilet.glb", "models/sink.glb"],
                },
                "traditional": {
                    "living_room": ["models/living_traditional.glb", "models/sofa_traditional.glb"],
                    "kitchen": ["models/kitchen_traditional.glb"],
                    "bedroom": ["models/bed_traditional.glb"],
                    "bathroom": ["models/bathroom_traditional.glb"],
                }
            },
            "furniture": {
                "modern": ["models/chair_modern.glb", "models/table_modern.glb", "models/lamp_modern.glb"],
                "traditional": ["models/chair_traditional.glb", "models/table_traditional.glb"],
            },
            "decoration": {
                "plants": ["models/plant_large.glb", "models/plant_small.glb"],
                "art": ["models/painting_abstract.glb", "models/painting_landscape.glb"],
                "rugs": ["models/rug_modern.glb", "models/rug_traditional.glb"],
            }
        },
        "heritage": {
            "poi": {
                "temple": ["models/temple_entrance.glb", "models/temple_sanctum.glb", "models/temple_pillar.glb"],
                "palace": ["models/palace_gate.glb", "models/palace_hall.glb", "models/palace_balcony.glb"],
                "courtyard": ["models/courtyard_fountain.glb", "models/courtyard_pavilion.glb"],
                "monument": ["models/monument_base.glb", "models/monument_inscription.glb"],
            },
            "decoration": {
                "statues": ["models/statue_deity.glb", "models/statue_historical.glb"],
                "lanterns": ["models/lantern_traditional.glb", "models/lantern_oil.glb"],
                "textiles": ["models/tapestry.glb", "models/carpet_traditional.glb"],
            }
        }
    }
    
    # Performance profiles
    PERFORMANCE_PROFILES = {
        "low": {
            "max_triangles_per_asset": 5000,
            "texture_size": 512,
            "lod_levels": 2,
        },
        "medium": {
            "max_triangles_per_asset": 15000,
            "texture_size": 1024,
            "lod_levels": 3,
        },
        "high": {
            "max_triangles_per_asset": 50000,
            "texture_size": 2048,
            "lod_levels": 4,
        }
    }
    
    def select_assets(self, input_data: AssetAgentInput) -> AssetAgentResult:
        """Select assets for all entities in the spec."""
        domain = input_data.domain
        budget = input_data.performance_budget
        
        # Determine performance profile
        profile = self._get_performance_profile(budget)
        
        selected = []
        substitutions = []
        warnings = []
        total_size = 0
        total_triangles = 0
        
        # Process each entity
        for entity in input_data.spec_entities:
            entity_assets = self._select_entity_assets(
                entity, domain, profile, input_data.available_assets
            )
            
            for asset in entity_assets:
                # Check budget
                if total_triangles + asset.estimated_triangles > budget.get("max_triangles", 100000):
                    # Find lower LOD alternative
                    lod_asset = self._find_lod_alternative(asset, profile)
                    if lod_asset:
                        substitutions.append({
                            "original": asset.uri,
                            "substituted": lod_asset.uri,
                            "reason": "Triangle budget exceeded"
                        })
                        asset = lod_asset
                    else:
                        warnings.append(f"Skipping {asset.uri}: exceeds triangle budget")
                        continue
                
                selected.append(asset)
                total_triangles += asset.estimated_triangles
                total_size += asset.estimated_size_mb
        
        # Add essential assets (lighting, skybox, etc.)
        essential = self._get_essential_assets(domain, profile)
        for asset in essential:
            selected.append(asset)
            total_size += asset.estimated_size_mb
        
        # Create manifest
        manifest = AssetManifest(
            assets=selected,
            total_size_mb=round(total_size, 2),
            estimated_load_time_ms=self._estimate_load_time(total_size)
        )
        
        logger.info("asset_selection_completed", 
                   domain=domain, 
                   assets=len(selected), 
                   size_mb=total_size,
                   triangles=total_triangles)
        
        return AssetAgentResult(
            manifest=manifest,
            selected_assets=selected,
            substitutions=substitutions,
            warnings=warnings
        )
    
    def _get_performance_profile(self, budget: Dict[str, Any]) -> str:
        """Determine performance profile from budget."""
        target_fps = budget.get("target_fps", 60)
        max_triangles = budget.get("max_triangles", 100000)
        
        if target_fps >= 60 and max_triangles <= 80000:
            return "low"
        elif target_fps >= 30 and max_triangles <= 150000:
            return "medium"
        return "high"
    
    def _select_entity_assets(
        self,
        entity: Entity,
        domain: str,
        profile: str,
        available: List[Dict[str, Any]]
    ) -> List[AssetReference]:
        """Select assets for a single entity."""
        assets = []
        catalog = self.ASSET_CATALOG.get(domain, {})
        
        # Get entity-specific assets
        entity_type = entity.type
        style = entity.properties.get("style", "modern")
        
        if entity_type in catalog:
            type_catalog = catalog[entity_type]
            if style in type_catalog:
                style_catalog = type_catalog[style]

                # Match by entity name
                entity_name_lower = entity.name.lower().replace(" ", "_")
                if isinstance(style_catalog, dict):
                    for key, asset_uris in style_catalog.items():
                        if key in entity_name_lower or entity_name_lower in key:
                            for uri in asset_uris:
                                assets.append(self._create_asset_reference(uri, profile, required=True))
                            break
                    else:
                        # Default to first available
                        for asset_uris in style_catalog.values():
                            for uri in asset_uris[:2]:  # Limit to 2 per category
                                assets.append(self._create_asset_reference(uri, profile, required=True))
                            break
                elif isinstance(style_catalog, list):
                    for uri in style_catalog[:2]:  # Limit to 2 per category
                        assets.append(self._create_asset_reference(uri, profile, required=True))
        
        # Add decoration assets for rooms
        if entity_type == "room" and entity.properties.get("furnished", True):
            decor = catalog.get("decoration", {})
            for decor_type, uris in decor.items():
                for uri in uris[:1]:  # One per decoration type
                    assets.append(self._create_asset_reference(uri, profile, required=False))
        
        return assets
    
    def _create_asset_reference(self, uri: str, profile: str, required: bool) -> AssetReference:
        """Create asset reference with profile-appropriate settings."""
        profile_config = self.PERFORMANCE_PROFILES[profile]
        
        # Estimate size and triangles based on profile
        if profile == "low":
            estimated_triangles = 3000
            estimated_size = 2
            lod_levels = 2
        elif profile == "medium":
            estimated_triangles = 10000
            estimated_size = 8
            lod_levels = 3
        else:
            estimated_triangles = 30000
            estimated_size = 25
            lod_levels = 4
        
        return AssetReference(
            id=uri.split("/")[-1].replace(".glb", ""),
            type="model",
            uri=f"assets/{uri}",
            fallback_uri=f"assets/{uri.replace('.glb', '_low.glb')}" if profile != "low" else None,
            lod_levels=lod_levels,
            required=required,
            estimated_triangles=estimated_triangles,
            estimated_size_mb=float(estimated_size),
        )
    
    def _find_lod_alternative(self, asset: AssetReference, profile: str) -> Optional[AssetReference]:
        """Find lower LOD version of asset."""
        if asset.fallback_uri:
            return AssetReference(
                id=asset.id + "_low",
                type=asset.type,
                uri=asset.fallback_uri,
                lod_levels=max(1, (asset.lod_levels or 2) - 1),
                required=asset.required
            )
        return None
    
    def _get_essential_assets(self, domain: str, profile: str) -> List[AssetReference]:
        """Get essential assets for any scene."""
        essential = [
            self._create_asset_reference("environments/skybox.glb", profile, True),
            self._create_asset_reference("materials/standard_materials.glb", profile, True),
        ]
        
        if domain == "heritage":
            essential.append(self._create_asset_reference("audio/ambient_heritage.mp3", profile, False))
        else:
            essential.append(self._create_asset_reference("audio/ambient_home.mp3", profile, False))
        
        return essential
    
    def _estimate_load_time(self, total_size_mb: float) -> int:
        """Estimate load time in milliseconds."""
        # Assume 50 Mbps effective bandwidth on mobile
        bandwidth_mbps = 50 / 8  # MB/s
        base_time = (total_size_mb / bandwidth_mbps) * 1000
        # Add overhead for parsing, GPU upload
        return int(base_time * 1.5)


# Global agent instance
asset_agent = AssetAgent()


def select_assets(
    spec_entities: List[Entity],
    domain: str,
    performance_budget: Dict[str, Any],
    available_assets: List[Dict[str, Any]] = None
) -> AssetAgentResult:
    """Convenience function for asset selection."""
    input_data = AssetAgentInput(
        spec_entities=spec_entities,
        domain=domain,
        performance_budget=performance_budget,
        available_assets=available_assets or []
    )
    return asset_agent.select_assets(input_data)