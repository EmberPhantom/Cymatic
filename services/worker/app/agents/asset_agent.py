"""Asset Agent - Selects assets, validates mobile performance, prepares manifest"""
from typing import Any

from pydantic import BaseModel

from cymatic_shared.schemas.simulation_spec import AssetManifest, AssetReference, Entity
import structlog

logger = structlog.get_logger()


class AssetAgentInput(BaseModel):
    spec_entities: list[Entity]
    domain: str
    performance_budget: dict[str, Any]
    available_assets: list[dict[str, Any]] = []


class AssetAgentResult(BaseModel):
    manifest: AssetManifest
    selected_assets: list[AssetReference]
    substitutions: list[dict[str, Any]] = []  # Original -> substituted
    warnings: list[str] = []


class AssetAgent:
    """Selects and prepares assets for scene generation."""

    # Asset mappings by entity type and style
    ASSET_CATALOG: dict[str, Any] = {
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
    PERFORMANCE_PROFILES: dict[str, dict[str, Any]] = {
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

        selected: list[AssetReference] = []
        substitutions: list[dict[str, Any]] = []
        warnings: list[str] = []
        total_size = 0.0
        total_triangles = 0
        seen_uris: set[str] = set()

        # Enforce max_entities cap early
        max_entities_cap = int(budget.get("max_entities", 500))
        # If spec already exceeds cap, warn
        if len(input_data.spec_entities) > max_entities_cap:
            warnings.append(f"Spec entity count {len(input_data.spec_entities)} exceeds budget max_entities {max_entities_cap}")

        # Process each entity
        for entity in input_data.spec_entities:
            entity_assets = self._select_entity_assets(
                entity, domain, profile, input_data.available_assets
            )

            for asset in entity_assets:
                # Deduplicate same URI across entities (HIGH: same uri duplication)
                if asset.uri in seen_uris:
                    continue

                # Enforce max_entities cap on assets as well
                if max_entities_cap and len(selected) >= max_entities_cap:
                    warnings.append(f"Skipping {asset.uri}: max_entities budget {max_entities_cap} reached")
                    continue

                # Check triangle budget - retry with LOD if needed, re-validate
                if total_triangles + asset.estimated_triangles > budget.get("max_triangles", 100000):
                    lod_asset = self._find_lod_alternative(asset, profile)
                    if lod_asset and lod_asset.uri not in seen_uris:
                        # Re-check triangle budget even after LOD; skip if still exceeds and no further LOD
                        if total_triangles + lod_asset.estimated_triangles > budget.get("max_triangles", 100000):
                            # If LOD still exceeds and it's not reducible further, skip
                            warnings.append(f"Skipping {asset.uri} (and LOD {lod_asset.uri}): exceeds triangle budget even at LOD")
                            continue
                        substitutions.append({
                            "original": asset.uri,
                            "substituted": lod_asset.uri,
                            "reason": "Triangle budget exceeded"
                        })
                        asset = lod_asset
                    else:
                        warnings.append(f"Skipping {asset.uri}: exceeds triangle budget")
                        continue

                # Final dedup check for LOD uri
                if asset.uri in seen_uris:
                    continue
                seen_uris.add(asset.uri)
                selected.append(asset)
                total_triangles += asset.estimated_triangles
                total_size += asset.estimated_size_mb

        # Add essential assets (lighting, skybox, etc.) with dedup and size accounting
        essential = self._get_essential_assets(domain, profile)
        for asset in essential:
            if asset.uri in seen_uris:
                continue
            if max_entities_cap and len(selected) >= max_entities_cap:
                warnings.append(f"Skipping essential {asset.uri}: max_entities budget reached")
                continue
            # Essential assets bypass triangle budget but still count toward size and dedup
            seen_uris.add(asset.uri)
            selected.append(asset)
            total_size += asset.estimated_size_mb
            total_triangles += asset.estimated_triangles
        
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
    
    def _get_performance_profile(self, budget: dict[str, Any]) -> str:
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
        available: list[dict[str, Any]],
    ) -> list[AssetReference]:
        """Select assets for a single entity."""
        assets: list[AssetReference] = []
        catalog: dict[str, Any] = self.ASSET_CATALOG.get(domain, {})
        
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
            decor: dict[str, Any] = catalog.get("decoration", {})
            for decor_type, uris in decor.items():
                for uri in uris[:1]:  # One per decoration type
                    assets.append(self._create_asset_reference(uri, profile, required=False))
        
        return assets
    
    def _create_asset_reference(self, uri: str, profile: str, required: bool) -> AssetReference:
        """Create asset reference with profile-appropriate settings."""
        cfg = self.PERFORMANCE_PROFILES.get(profile, self.PERFORMANCE_PROFILES["medium"])

        # Derive estimates from PERFORMANCE_PROFILES to stay consistent (HIGH: hardcode vs profile)
        max_per_asset = int(cfg.get("max_triangles_per_asset", 15000))
        estimated_triangles = max(500, int(max_per_asset * 0.6))
        if profile == "low":
            estimated_size = 2.0
        elif profile == "medium":
            estimated_size = 8.0
        else:
            estimated_size = 25.0
        lod_levels = int(cfg.get("lod_levels", 2))
        
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
    
    def _find_lod_alternative(self, asset: AssetReference, profile: str) -> AssetReference | None:
        """Find lower LOD version of asset. Preserves budget accounting (HIGH: LOD zero bypass)."""
        if asset.fallback_uri:
            lod_levels = max(1, (asset.lod_levels or 2) - 1)
            # Preserve estimates with reduction to avoid zero-bypass cheating budget.
            # Use ~50% triangles and size reduction, clamped to minimum.
            est_tris = max(500, int((asset.estimated_triangles or 3000) * 0.5))
            est_size = max(0.5, float(asset.estimated_size_mb or 2.0) * 0.5)
            return AssetReference(
                id=asset.id + "_low",
                type=asset.type,
                uri=asset.fallback_uri,
                fallback_uri=None,
                lod_levels=lod_levels,
                required=asset.required,
                estimated_triangles=est_tris,
                estimated_size_mb=est_size,
            )
        return None
    
    def _get_essential_assets(self, domain: str, profile: str) -> list[AssetReference]:
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
    spec_entities: list[Entity],
    domain: str,
    performance_budget: dict[str, Any],
    available_assets: list[dict[str, Any]] | None = None,
) -> AssetAgentResult:
    """Convenience function for asset selection."""
    input_data = AssetAgentInput(
        spec_entities=spec_entities,
        domain=domain,
        performance_budget=performance_budget,
        available_assets=available_assets or []
    )
    return asset_agent.select_assets(input_data)