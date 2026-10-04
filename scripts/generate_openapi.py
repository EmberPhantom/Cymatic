#!/usr/bin/env python3
"""Generate OpenAPI specs for all services.

Import strategy (hyphen-safe): service dirs like ``services/llm-router`` are
NOT valid Python package paths (``services.llm_router`` does not exist), so
each app is loaded path-first — the subprocess puts that service's own dir at
sys.path[0] and imports plain ``app.main``. No ``services.<name>`` dotted
import is attempted.

Output goes to ./reports/ (like benchmarks) by default — never into the
service source tree — unless --out-dir points elsewhere.
"""
import argparse
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

SERVICE_NAMES = [s.split("/")[-1] for s, _ in services]


def generate_one(svc_path: str, app_import: str, env: dict, out_dir: Path) -> bool:
    print(f"Generating OpenAPI for {svc_path}...")
    svc_dir = REPO_ROOT / svc_path
    if not svc_dir.exists():
        print(f"  Skip {svc_path} - not found")
        return False
    # app import is e.g., app.main:app -> module app.main
    module = app_import.split(":")[0]
    # Path-based import: svc_dir first on sys.path, then shared. The service
    # dir MUST precede every other service dir so `app.main` resolves to THIS
    # service (never via a dotted `services.<hyphen-name>` path, which is
    # unimportable).
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{SHARED_PATH}'); sys.path.insert(0, r'{svc_dir}'); from {module} import app; import json; print(json.dumps(app.openapi(), indent=2))"],
        cwd=str(svc_dir),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if result.returncode == 0 and result.stdout.strip().startswith("{"):
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / f"openapi-{svc_path.split('/')[-1]}.json"
        output.write_text(result.stdout, encoding="utf-8")
        print(f"  Generated {output}")
        return True
    print(f"  Failed: {result.stderr[:500]}")
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate OpenAPI specs into ./reports/.")
    parser.add_argument(
        "--services", nargs="*", default=SERVICE_NAMES,
        help=f"Subset of services to generate (default: all). Choices: {SERVICE_NAMES}",
    )
    parser.add_argument(
        "--out-dir", default=str(REPO_ROOT / "reports"),
        help="Output directory (default: ./reports). Nothing is written into service source trees.",
    )
    args = parser.parse_args(argv)

    unknown = [s for s in args.services if s not in SERVICE_NAMES]
    if unknown:
        parser.error(f"unknown services: {unknown} (choices: {SERVICE_NAMES})")
    out_dir = Path(args.out_dir)

    env = os.environ.copy()
    # Ensure shared package discoverable
    existing_pp = env.get("PYTHONPATH", "")
    extra = [str(SHARED_PATH)]
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing_pp] if existing_pp else []))

    ok = True
    for svc_path, app_import in services:
        if svc_path.split("/")[-1] not in args.services:
            continue
        if not generate_one(svc_path, app_import, env, out_dir):
            ok = False
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
