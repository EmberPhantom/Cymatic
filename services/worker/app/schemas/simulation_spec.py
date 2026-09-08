"""Worker schema shim - re-exports canonical shared schemas to avoid fork drift.

Canonical source: packages/cymatic-shared/cymatic_shared/schemas/simulation_spec.py
and schemas/simulation_spec.py at repo root. This file exists for backward compat
with older import paths and now delegates to the shared package to keep a single
source of truth (HIGH: stale fork). Any changes should be made in the shared
package, not here.
"""
# Re-export everything from the canonical shared package
from cymatic_shared.schemas.simulation_spec import (  # noqa: F401, F403
    AssetManifest,
    AssetReference,
    CopilotAction,
    CopilotPersonality,
    CopilotPolicy,
    CustomLight,
    CustomLightType,
    Domain,
    Entity,
    EntityType,
    GenerationJob,
    LightingPreset,
    LightingSpec,
    NavigationPath,
    NavigationPathType,
    NavigationPoint,
    NavigationSpec,
    PerformanceBudget,
    SimulationSpec,
    SpecMetadata,
)

__all__ = [
    "AssetManifest",
    "AssetReference",
    "CopilotAction",
    "CopilotPersonality",
    "CopilotPolicy",
    "CustomLight",
    "CustomLightType",
    "Domain",
    "Entity",
    "EntityType",
    "GenerationJob",
    "LightingPreset",
    "LightingSpec",
    "NavigationPath",
    "NavigationPathType",
    "NavigationPoint",
    "NavigationSpec",
    "PerformanceBudget",
    "SimulationSpec",
    "SpecMetadata",
]
