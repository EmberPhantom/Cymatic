#!/usr/bin/env python3
"""Generate OpenAPI specs for all services."""
import json
import sys
from pathlib import Path

services = [
    ("services/api", "app.main:app"),
    ("services/worker", "app.main:app"),
    ("services/llm-router", "app.main:app"),
]

for svc_path, app_import in services:
    print(f"Generating OpenAPI for {svc_path}...")
    svc_dir = Path(svc_path)
    if not svc_dir.exists():
        print(f"  Skip {svc_path} - not found")
        continue
    try:
        # Use subprocess to avoid import side effects
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", f"from {app_import.split(':')[0]} import app; import json; print(json.dumps(app.openapi(), indent=2))"],
            cwd=svc_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            output = Path(f"{svc_path}/openapi.json")
            output.write_text(result.stdout)
            print(f"  Generated {output}")
        else:
            print(f"  Failed: {result.stderr[:200]}")
    except Exception as e:
        print(f"  Error: {e}")
