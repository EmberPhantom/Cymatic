#!/usr/bin/env python3
"""Generate OpenAPI specs for all services."""
import sys
import os
import subprocess
from pathlib import Path

# Ensure repo root on PYTHONPATH for shared imports
REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_PATH = REPO_ROOT / "packages" / "cymatic-shared"
for p in [str(REPO_ROOT), str(SHARED_PATH)]:
    if p not in sys.path:
        sys.path.insert(0, p)

services = [
    ("services/api", "app.main:app"),
    ("services/worker", "app.main:app"),
    ("services/llm-router", "app.main:app"),
]

env = os.environ.copy()
# Ensure shared package discoverable
existing_pp = env.get("PYTHONPATH", "")
extra = [str(SHARED_PATH), str(REPO_ROOT / "services" / "api"), str(REPO_ROOT / "services" / "worker"), str(REPO_ROOT / "services" / "llm-router")]
env["PYTHONPATH"] = os.pathsep.join(extra + ([existing_pp] if existing_pp else []))

for svc_path, app_import in services:
    print(f"Generating OpenAPI for {svc_path}...")
    svc_dir = REPO_ROOT / svc_path
    if not svc_dir.exists():
        print(f"  Skip {svc_path} - not found")
        continue
    # app import is e.g., app.main:app -> module app.main
    module = app_import.split(":")[0]
    try:
        # Run from repo root with PYTHONPATH set, import via services.api.app.main etc? But services use `app.main` relative.
        # We need to run with cwd = svc_dir and PYTHONPATH includes shared and svc_dir
        result = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{SHARED_PATH}'); sys.path.insert(0, r'{svc_dir}'); from {module} import app; import json; print(json.dumps(app.openapi(), indent=2))"],
            cwd=str(svc_dir),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            output = svc_dir / "openapi.json"
            output.write_text(result.stdout, encoding="utf-8")
            print(f"  Generated {output}")
        else:
            # Fallback: try importing via services.api.app.main
            alt_module = svc_path.replace("/", ".").replace("-", "_") + "." + module
            # Try repo-root import
            result2 = subprocess.run(
                [sys.executable, "-c", f"from {alt_module} import app; import json; print(json.dumps(app.openapi(), indent=2))"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if result2.returncode == 0 and result2.stdout.strip().startswith("{"):
                output = svc_dir / "openapi.json"
                output.write_text(result2.stdout, encoding="utf-8")
                print(f"  Generated {output} (fallback)")
            else:
                print(f"  Failed: {result.stderr[:500]}")
                if result2.stderr:
                    print(f"  Fallback failed: {result2.stderr[:500]}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
