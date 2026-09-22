#!/usr/bin/env python3
"""A small, hand-written JSON Schema validator.

Supports exactly the subset of JSON Schema (draft-07-ish) used by the
schemas in ../schema/: `type`, `properties`, `required`,
`additionalProperties`, `items`, `enum`, `minimum`, `maximum`, `minLength`,
`maxItems`, `minItems`, `$ref` (to `#/definitions/<name>` within the same
document), `definitions`, and `anyOf`. Anything else present in a schema is
silently ignored.

Stdlib only. Runnable as ``python3 validate.py --schema S --file F`` and
importable as ``validate`` for ``validate(instance, schema)`` /
``load_schema(name)``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_DIR = os.path.normpath(os.path.join(_SCRIPTS_DIR, "..", "schema"))

def load_schema(name: str) -> dict:
    """Resolve a bare schema name (e.g. "care_plan") to its file under
    schema/ and return the parsed schema. A path ending in .json is used
    as-is (relative paths are resolved against the cwd)."""
    if name.endswith(".json"):
        path = name
    else:
        path = os.path.join(_SCHEMA_DIR, f"{name}.schema.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _type_matches(value, type_spec) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    for t in types:
        if t == "boolean":
            if isinstance(value, bool):
                return True
        elif t == "object":
            if isinstance(value, dict):
                return True
        elif t == "array":
            if isinstance(value, list):
                return True
        elif t == "string":
            if isinstance(value, str):
                return True
        elif t == "null":
            if value is None:
                return True
        elif t == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif t == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
        # Unknown types are ignored (never match).
    return False


def _resolve_ref(ref: str, root: dict) -> dict:
    prefix = "#/definitions/"
    if not ref.startswith(prefix):
        raise ValueError(f"Unsupported $ref: {ref!r} (only '#/definitions/<name>' is supported)")
    name = ref[len(prefix):]
    definitions = root.get("definitions", {})
    if name not in definitions:
        raise ValueError(f"$ref target not found in definitions: {ref!r}")
    return definitions[name]


def _fmt_value(value) -> str:
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)


def _validate(instance, schema, root: dict, path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], root)
        _validate(instance, resolved, root, path, errors)
        return

    if "anyOf" in schema:
        sub_errors_per_option = []
        matched = False
        for option in schema["anyOf"]:
            option_errors: list[str] = []
            _validate(instance, option, root, path, option_errors)
            if not option_errors:
                matched = True
                break
            sub_errors_per_option.append(option_errors)
        if not matched:
            errors.append(
                f"{path or '$'}: value {_fmt_value(instance)} did not match any option in anyOf"
            )
        return

    if "type" in schema:
        if not _type_matches(instance, schema["type"]):
            expected = schema["type"]
            errors.append(
                f"{path or '$'}: expected type {expected!r}, got {_fmt_value(instance)}"
            )
            return

    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(
                f"{path or '$'}: expected one of {schema['enum']!r}, got {_fmt_value(instance)}"
            )

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(
                f"{path or '$'}: string shorter than minLength {schema['minLength']} "
                f"(got length {len(instance)})"
            )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path or '$'}: {instance} is less than minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path or '$'}: {instance} is greater than maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(
                f"{path or '$'}: array shorter than minItems {schema['minItems']} "
                f"(got length {len(instance)})"
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(
                f"{path or '$'}: array longer than maxItems {schema['maxItems']} "
                f"(got length {len(instance)})"
            )
        if "items" in schema:
            item_schema = schema["items"]
            for i, item in enumerate(instance):
                _validate(item, item_schema, root, f"{path}[{i}]", errors)

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path or '$'}: missing required property {key!r}")

        for key, value in instance.items():
            sub_path = f"{path}.{key}" if path else key
            if key in properties:
                _validate(value, properties[key], root, sub_path, errors)
            else:
                additional = schema.get("additionalProperties", True)
                if additional is False:
                    errors.append(f"{path or '$'}: additional property {key!r} is not allowed")
                elif isinstance(additional, dict):
                    _validate(value, additional, root, sub_path, errors)
                # additional is True (or absent) -> no constraint


def validate(instance, schema) -> list[str]:
    """Validate `instance` against `schema`. Returns a list of human-readable
    error strings; an empty list means the instance is valid."""
    errors: list[str] = []
    _validate(instance, schema, schema, "", errors)
    return errors


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a JSON file against a JSON Schema")
    parser.add_argument("--schema", required=True, help="Path to the schema file, or a bare name resolved under schema/")
    parser.add_argument("--file", required=True, help="Path to the JSON instance file to validate")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        schema = load_schema(args.schema)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load schema {args.schema!r}: {exc}")
        return 1

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            instance = json.load(f)
    except OSError as exc:
        print(f"Could not read file {args.file!r}: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.file!r}: {exc}")
        return 1

    errors = validate(instance, schema)
    if not errors:
        print("OK")
        return 0

    for error in errors:
        print(error)
    return 1


if __name__ == "__main__":
    sys.exit(main())
