#!/usr/bin/env python3
"""Generate TypeScript schemas from Python - delegates to check_schema_sync validator."""
import subprocess
import sys
from pathlib import Path

def main():
    checker = Path(__file__).parent / "check_schema_sync.py"
    result = subprocess.run([sys.executable, str(checker)])
    if result.returncode == 0:
        print("Schemas are in sync - no generation needed (Python is source of truth, TS file already matches)")
    else:
        print("Schema drift detected - update schemas/simulation_spec.ts to match schemas/simulation_spec.py")
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
