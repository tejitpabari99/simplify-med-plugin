"""A tiny JSON Schema validator for the one schema the simplify skill ships.

Supports only the subset `schema/plan.schema.json` uses: `type`, `properties`,
`required`, `additionalProperties: false`, `items`, `enum`, `minLength`,
`minItems`, `maxItems`, `$ref` to `#/definitions/<name>`, and `anyOf`.
Any other validation keyword raises `UnsupportedKeyword`, so a schema change
cannot make a test pass by being silently ignored. Test-only; the skill itself
runs no code.
"""

from __future__ import annotations

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}

SUPPORTED = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minLength", "minItems", "maxItems", "$ref", "anyOf",
}
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "definitions", "examples", "default"}


class UnsupportedKeyword(ValueError):
    pass


def _check_keywords(schema: dict, where: str) -> None:
    unknown = set(schema) - SUPPORTED - ANNOTATIONS
    if unknown:
        raise UnsupportedKeyword(f"{where}: unsupported schema keyword(s) {sorted(unknown)}")
    extra = schema.get("additionalProperties")
    if extra not in (None, False):
        raise UnsupportedKeyword(f"{where}: only additionalProperties: false is supported")


def _type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    return any(_TYPES[name](value) for name in names)


def _check(value, schema: dict, root: dict, path: str, errors: list[str]) -> None:
    where = path or "$"
    _check_keywords(schema, where)
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            raise UnsupportedKeyword(f"{where}: unsupported $ref {ref!r}")
        _check(value, root["definitions"][ref[len("#/definitions/"):]], root, path, errors)
        return
    if "anyOf" in schema:
        if all(validate_against(value, option, root) for option in schema["anyOf"]):
            errors.append(f"{where}: matches no anyOf option")
        return
    expected = schema.get("type")
    if expected and not _type_ok(value, expected):
        errors.append(f"{where}: expected {expected}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} not in {schema['enum']}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: shorter than minLength")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{where}: more than maxItems")
        for index, item in enumerate(value):
            _check(item, schema.get("items", {}), root, f"{path}[{index}]", errors)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing {key!r}")
        for key, item in value.items():
            if key in properties:
                _check(item, properties[key], root, f"{path}.{key}" if path else key, errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{where}: unexpected {key!r}")


def validate_against(value, schema: dict, root: dict) -> list[str]:
    errors: list[str] = []
    _check(value, schema, root, "", errors)
    return errors


def validate(value, schema: dict) -> list[str]:
    """Return a list of errors; empty means `value` matches `schema`."""
    return validate_against(value, schema, schema)
