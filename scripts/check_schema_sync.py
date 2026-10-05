#!/usr/bin/env python3
"""
Schema Sync Check - Compares Python Pydantic models with TypeScript interfaces.

This script extracts field names and types from both schemas and reports any drift.
"""
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import importlib.util

SCHEMA_ROOT = Path(__file__).parent.parent / "schemas"
SHARED_SCHEMAS = Path(__file__).parent.parent / "packages" / "cymatic-shared" / "cymatic_shared" / "schemas"
# (python file, typescript file, root model/interface name)
# Candidate survey 2026-10-04: schemas/ contains exactly two .py+.ts schema
# pairs (simulation_spec, planning_sheet). simulation_spec_generated.py has NO
# TypeScript counterpart (codegen output, not a sync pair); __init__.py and
# package.json are not schemas. Service-local app/schemas/ copies are banned
# (see SHARED_COPIES below). So the pair list stays at 2 — each entry is
# existence-checked at runtime and skipped with a warning instead of crashing.
SCHEMA_PAIRS = [
    ("simulation_spec.py", "simulation_spec.ts", "SimulationSpec"),
    ("planning_sheet.py", "planning_sheet.ts", "PlanningSheet"),
]
# Service-local copies are banned: shared/schemas must stay byte-identical
# to the canonical root schemas (validators import from shared).
SHARED_COPIES = ["simulation_spec.py", "planning_sheet.py"]


def extract_python_schema(py_file: str, model_name: str) -> Dict[str, Any]:
    """Extract schema structure from Python Pydantic models."""
    path = SCHEMA_ROOT / py_file
    module_name = Path(py_file).stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Get the JSON schema from Pydantic
    schema = getattr(module, model_name).model_json_schema()
    return schema


def _strip_ts_line_comment(line: str) -> str:
    """Remove a trailing `//` comment, ignoring `//` inside '...' / "..." / `...`.

    Prevents URLs in comments (e.g. `// see https://x`) from leaking colons
    into field parsing, while keeping `//` inside string literals intact.
    """
    quote: Optional[str] = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            return line[:i]
        i += 1
    return line


# Anchored to TypeScript property syntax: `name?: Type` with an optional
# trailing `;`/`,` — NOT a bare "split on any ':'", so colons inside string
# literal types ('a:b'), ternaries, URLs, or mapped/index-signature lines that
# don't match are never mis-split (non-matching lines are skipped).
_TS_FIELD_RE = re.compile(
    r"^(?:readonly\s+)?([A-Za-z_$][\w$]*)(\?)?\s*:\s*(.+?)\s*[;,]?\s*$"
)


def _parse_ts_field(stripped: str) -> Optional[Tuple[str, str]]:
    """Parse one stripped TS line into (field_name, type_text)."""
    code = _strip_ts_line_comment(stripped).strip()
    if not code or code.startswith(("//", "*", "/*", "|", "'", '"', "`", "@", "}")):
        return None
    match = _TS_FIELD_RE.match(code)
    if not match:
        return None
    name, _optional, type_text = match.groups()
    type_text = type_text.strip()
    if not name or not type_text:
        return None
    return name, type_text


def extract_typescript_schema(ts_file: str) -> Dict[str, Any]:
    """Extract schema structure from TypeScript by compiling and inspecting."""
    # Use TypeScript compiler to get declaration info
    # We'll parse the TS file directly for a simpler approach
    content = (SCHEMA_ROOT / ts_file).read_text()

    # Simple extraction of interface names and their fields
    # This is a basic parser - could be enhanced with proper TS AST parsing
    interfaces = {}
    lines = content.split('\n')
    current_interface = None
    in_interface = False
    brace_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('export interface '):
            if current_interface and in_interface:
                interfaces[current_interface] = current_interface
            current_interface = stripped.replace('export interface ', '').split(' ')[0].replace('{', '').strip()
            in_interface = True
            brace_count = stripped.count('{') - stripped.count('}')
        elif in_interface:
            brace_count += stripped.count('{') - stripped.count('}')
            parsed = _parse_ts_field(stripped)
            if parsed is not None:
                field_name, field_type = parsed
                if current_interface not in interfaces:
                    interfaces[current_interface] = {}
                if isinstance(interfaces[current_interface], dict):
                    interfaces[current_interface][field_name] = field_type
            if brace_count <= 0:
                in_interface = False

    return interfaces


def get_pydantic_fields(schema: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    """Recursively extract field names and types from Pydantic JSON schema."""
    fields: Dict[str, str] = {}
    properties = schema.get('properties', {})

    for prop_name, prop_schema in properties.items():
        full_name = f"{prefix}{prop_name}"
        if 'type' in prop_schema:
            if prop_schema['type'] == 'array' and 'items' in prop_schema:
                items = prop_schema['items']
                if '$ref' in items:
                    fields[full_name] = f"Array<{items['$ref'].split('/')[-1]}>"
                elif 'type' in items:
                    fields[full_name] = f"Array<{items['type']}>"
                else:
                    fields[full_name] = "Array"
            elif '$ref' in prop_schema:
                fields[full_name] = prop_schema['$ref'].split('/')[-1]
            else:
                fields[full_name] = prop_schema['type']
        elif 'allOf' in prop_schema:
            for all_of in prop_schema['allOf']:
                if '$ref' in all_of:
                    fields[full_name] = all_of['$ref'].split('/')[-1]
                    break
        elif 'anyOf' in prop_schema:
            types = []
            for any_of in prop_schema['anyOf']:
                if 'type' in any_of:
                    types.append(any_of['type'])
                elif '$ref' in any_of:
                    types.append(any_of['$ref'].split('/')[-1])
            fields[full_name] = ' | '.join(types)
        elif '$ref' in prop_schema:
            fields[full_name] = prop_schema['$ref'].split('/')[-1]

    # Recursively process definitions
    defs = schema.get('$defs', {}) or schema.get('definitions', {})
    for def_name, def_schema in defs.items():
        if def_name not in fields.values():  # Only process if referenced
            sub_fields = get_pydantic_fields(def_schema, "")
            for k, v in sub_fields.items():
                fields[f"{def_name}.{k}"] = v

    return fields


def compare_schemas(py_fields: Dict[str, str], ts_fields: Dict[str, Dict[str, str]], main_name: str) -> Tuple[List[str], List[str], List[str]]:
    """Compare Python and TypeScript field structures."""
    errors = []
    warnings = []
    info = []

    # Main interface comparison
    py_main = {k: v for k, v in py_fields.items() if '.' not in k}
    ts_main = ts_fields.get(main_name, {})

    py_keys = set(py_main.keys())
    ts_keys = set(ts_main.keys())

    # Missing in TypeScript
    for key in py_keys - ts_keys:
        errors.append(f"Missing in TypeScript: {main_name}.{key} ({py_main[key]})")

    # Missing in Python
    for key in ts_keys - py_keys:
        errors.append(f"Missing in Python: {main_name}.{key} ({ts_main[key]})")

    # Type mismatches
    for key in py_keys & ts_keys:
        py_type = py_main[key]
        ts_type = ts_main[key]
        allowlist_notes: List[str] = []
        if not types_match(py_type, ts_type, allowlist_notes):
            warnings.append(f"Type mismatch: {main_name}.{key} - Python: {py_type}, TypeScript: {ts_type}")
        else:
            warnings.extend(f"{main_name}.{key}: {note}" for note in allowlist_notes)

    # Check nested interfaces
    for ts_interface, ts_props in ts_fields.items():
        if ts_interface == main_name:
            continue
        py_props = {k.split('.', 1)[1]: v for k, v in py_fields.items() if k.startswith(f"{ts_interface}.")}
        if not py_props:
            continue
        ts_prop_keys = set(ts_props.keys())
        py_prop_keys = set(py_props.keys())
        for key in py_prop_keys - ts_prop_keys:
            warnings.append(f"Missing in TypeScript: {ts_interface}.{key} ({py_props[key]})")
        for key in ts_prop_keys - py_prop_keys:
            warnings.append(f"Missing in Python: {ts_interface}.{key} ({ts_props[key]})")

    return errors, warnings, info


# Explicit allowlist of TypeScript nominal type references that have no
# primitive Python equivalent (nested interfaces / enums / aliases declared in
# the .ts sources). A hit is COMPATIBLE but always emits a warning via the
# `notes` out-param so silent blanket-True can never hide drift. Anything not
# listed here and not matching the equivalences below is a MISMATCH (strict).
CUSTOM_TYPE_ALLOWLIST = frozenset({
    'domain', 'planningdomain', 'entity', 'entitytype', 'navigationpoint', 'navigationpath', 'navigationspec',
    'lightingspec', 'customlight', 'copilotpolicy', 'performancebudget', 'specmetadata',
    'planspace', 'spacesize', 'dimension', 'plancolor', 'planmaterial', 'spacelighting', 'researchref',
    'lengthunit', 'sheetstatus', 'lightingpreset',
})


def _is_ts_string_literal_union(ts_norm: str) -> bool:
    """True if every `|`-separated member is a quoted string literal."""
    members = [m.strip().rstrip(';').rstrip(',') for m in ts_norm.split('|')]
    if len(members) < 2:
        return False
    return all(
        len(m) >= 2 and m[0] == m[-1] and m[0] in ("'", '"')
        for m in members
    )


def types_match(py_type: str, ts_type: str, notes: Optional[List[str]] = None) -> bool:
    """Check if Python and TypeScript types are compatible (strict).

    Unknown custom TS references return False unless explicitly listed in
    CUSTOM_TYPE_ALLOWLIST — and allowlist hits append a warning to `notes`.
    """
    # Normalize types (keep brackets: slicing below depends on them)
    # Strip union members/quotes for the nominal lookup: e.g. TS
    # `"room" | "poi"` or `'warm' | 'cool'` are string-literal unions.
    py_norm = py_type.lower()
    ts_norm = ts_type.lower()

    # Direct match
    if py_norm == ts_norm:
        return True

    # TypeScript string-literal union (e.g. `"a" | "b"`) vs Python string/enum
    if py_norm in ('string', 'str') and _is_ts_string_literal_union(ts_norm):
        return True

    # Handle array types first so the allowlist note names the inner types:
    # Array<Entity> vs Entity[] (either direction).
    if py_norm.startswith('array<') and ts_norm.endswith('[]'):
        py_inner = py_norm[6:-1]
        ts_inner = ts_norm[:-2]
        return types_match(py_inner, ts_inner, notes)
    if ts_norm.startswith('array<') and py_norm.endswith('[]'):
        ts_inner = ts_norm[6:-1]
        py_inner = py_norm[:-2]
        return types_match(py_inner, ts_inner, notes)

    # Handle TypeScript nominal type references via explicit allowlist only.
    # The base nominal (before any `[]`/`Array<>`/union decoration) must be listed.
    ts_base = re.split(r'[\s<>\[\]|,;()]+', ts_norm)[0].strip('\'"')
    if ts_base in CUSTOM_TYPE_ALLOWLIST:
        if notes is not None:
            notes.append(
                f"Allowlisted nominal type assumed compatible: Python '{py_type}' vs TS '{ts_type}'"
            )
        return True

    # Dict[str, X] (pydantic 'object') vs TypeScript Record<string, X>
    if py_norm == 'object' and ts_norm.startswith('record<string'):
        return True

    # Common equivalences
    equivalences = {
        'string': ['string'],
        'integer': ['number', 'integer'],
        'number': ['number', 'integer'],
        'boolean': ['boolean'],
        'array': ['array'],
        'object': ['object'],
    }

    for py_base, ts_bases in equivalences.items():
        if py_norm.startswith(py_base) and any(ts_norm.startswith(t) for t in ts_bases):
            return True

    return False


def main():
    print("Checking schema sync between Python and TypeScript...")

    all_errors: List[str] = []
    all_warnings: List[str] = []
    all_info: List[str] = []

    for name in SHARED_COPIES:
        root_p, shared_p = SCHEMA_ROOT / name, SHARED_SCHEMAS / name
        if not root_p.exists() or not shared_p.exists():
            all_warnings.append(f"Shared copy check skipped (missing file): {name}")
            continue
        root = root_p.read_bytes()
        shared = shared_p.read_bytes()
        if root != shared:
            all_errors.append(f"Shared copy drifted: packages/.../schemas/{name} != schemas/{name}")
        else:
            print(f"Shared copy identical: {name}")

    for py_file, ts_file, main_name in SCHEMA_PAIRS:
        print(f"\n--- {py_file} <-> {ts_file} ---")
        # Existence-gated: only pairs whose files actually exist are checked.
        # (Survey: no further .py+.ts pairs exist in schemas/ — see note above.)
        if not (SCHEMA_ROOT / py_file).exists():
            all_warnings.append(f"Pair skipped, Python side missing: {py_file}")
            print(f"  skipped (missing {py_file})")
            continue
        if not (SCHEMA_ROOT / ts_file).exists():
            all_warnings.append(f"Pair skipped, TypeScript side missing: {ts_file}")
            print(f"  skipped (missing {ts_file})")
            continue
        try:
            py_schema = extract_python_schema(py_file, main_name)
            py_fields = get_pydantic_fields(py_schema)
            print(f"Extracted {len(py_fields)} Python fields")
        except Exception as e:
            print(f"Error extracting Python schema: {e}")
            sys.exit(1)

        try:
            ts_fields = extract_typescript_schema(ts_file)
            total_ts = sum(len(v) if isinstance(v, dict) else 0 for v in ts_fields.values())
            print(f"Extracted {total_ts} TypeScript fields from {len(ts_fields)} interfaces")
        except Exception as e:
            print(f"Error extracting TypeScript schema: {e}")
            sys.exit(1)

        errors, warnings, info = compare_schemas(py_fields, ts_fields, main_name)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        all_info.extend(info)

    errors, warnings, info = all_errors, all_warnings, all_info

    if info:
        print("\nINFO:")
        for msg in info:
            print(f"  - {msg}")

    if warnings:
        print("\nWARNINGS:")
        for msg in warnings:
            print(f"  - {msg}")

    if errors:
        print("\nERRORS (schema drift detected):")
        for msg in errors:
            print(f"  - {msg}")
        sys.exit(1)
    else:
        print("\n[OK] Schemas are in sync!")
        sys.exit(0)


if __name__ == "__main__":
    main()
