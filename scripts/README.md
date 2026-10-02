# `scripts/` — repo tooling (no runtime code)

| Script | Purpose |
|--------|---------|
| `generate_openapi.py` | Emit per-service `openapi.json` (git-ignored artifacts) |
| `generate_ts_schemas.py` | Generate TS schemas from Python (with drift check) |
| `check_schema_sync.py` | CI gate: `schemas/*.py` ↔ `*.ts` (+ shared copies) in sync |
| `benchmark.py` | Health/latency/streaming benchmark → `./reports/` |
| `docker-clean.ps1` | Windows Docker cleanup helper |

Conventions: `#!/usr/bin/env python3`, no hardcoded secrets, outputs to
`./reports/` (git-ignored), backend URLs overridable via env/args.
