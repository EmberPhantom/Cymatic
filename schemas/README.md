# `schemas/` — canonical Simulation Specification

Single source of truth for the spec-first pipeline. Every simulation is
generated from, validated against, and stored as these schemas.

- `simulation_spec.py` / `simulation_spec.ts` — entities, navigation,
  lighting, copilot policy, performance budget, asset manifest
- `planning_sheet.py` / `planning_sheet.ts` — planning agent output
- `package.json` — TS build/type-check

Keep `.py` and `.ts` in sync (CI drift gate: `scripts/check_schema_sync.py`).
Service-local copies are re-exports, never forks.
