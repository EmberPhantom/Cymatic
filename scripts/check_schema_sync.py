#!/usr/bin/env python3
"""
Schema Sync Check - Compares Python Pydantic models with TypeScript interfaces.

This script extracts field names and types from both schemas and reports any drift.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import importlib.util

SCHEMA_ROOT = Path(__file__).parent.parent / "schemas"
# (python file, typescript file, root model/interface name)
SCHEMA_PAIRS = [
    ("simulation_spec.py", "simulation_spec.ts", "SimulationSpec"),
    ("planning_sheet.py", "planning_sheet.ts", "PlanningSheet"),
]


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
            if ':' in stripped and not stripped.startswith('//'):
                # Field definition
                parts = stripped.split(':')
                field_name = parts[0].replace('?', '').strip()
                if field_name and not field_name.startswith('//'):
                    if current_interface not in interfaces:
                        interfaces[current_interface] = {}
                    if isinstance(interfaces[current_interface], dict):
                        interfaces[current_interface][field_name] = parts[1].split(';')[0].strip()
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
        if not types_match(py_type, ts_type):
            warnings.append(f"Type mismatch: {main_name}.{key} - Python: {py_type}, TypeScript: {ts_type}")

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


def types_match(py_type: str, ts_type: str) -> bool:
    """Check if Python and TypeScript types are compatible."""
    # Normalize types (keep brackets: slicing below depends on them)
    py_norm = py_type.lower()
    ts_norm = ts_type.lower()

    # Direct match
    if py_norm == ts_norm:
        return True

    # Handle TypeScript type references (Domain, Entity, etc.)
    if ts_norm in ['domain', 'planningdomain', 'entity', 'entitytype', 'navigationpoint', 'navigationpath', 'navigationspec',
                    'lightingspec', 'customlight', 'copilotpolicy', 'performancebudget', 'specmetadata',
                    'planspace', 'spacesize', 'dimension', 'plancolor', 'planmaterial', 'spacelighting', 'researchref',
                    'lengthunit', 'sheetstatus']:
        return True

    # Handle array types: Array<Entity> vs Entity[]
    if py_norm.startswith('array<') and ts_norm.endswith('[]'):
        py_inner = py_norm[6:-1]
        ts_inner = ts_norm[:-2]
        return types_match(py_inner, ts_inner)
    if ts_norm.startswith('array<') and py_norm.endswith('[]'):
        ts_inner = ts_norm[6:-1]
        py_inner = py_norm[:-2]
        return types_match(py_inner, ts_inner)
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

    for py_file, ts_file, main_name in SCHEMA_PAIRS:
        print(f"\n--- {py_file} <-> {ts_file} ---")
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