"""Minimal JSON-schema validator (draft 2020-12 subset), standard library only.

Supported keywords: type, properties, required, additionalProperties (bool), items, minItems, maxItems,
enum, const, pattern, minLength, maxLength, uniqueItems, $ref (local '#/...'), $defs, description, title.
Unsupported keywords are ignored. Returns a list of error strings (empty = valid)."""
import re

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def validate(instance, schema, root=None, path="$", errors=None, _depth=0):
    if errors is None:
        errors = []
    if root is None:
        root = schema
    if _depth > 64:
        errors.append(f"{path}: schema recursion too deep")
        return errors
    if not isinstance(schema, dict):
        return errors
    if "$ref" in schema:
        target = _resolve_ref(root, schema["$ref"])
        merged = dict(target)
        for k, v in schema.items():
            if k != "$ref":
                merged[k] = v
        return validate(instance, merged, root, path, errors, _depth + 1)
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES.get(tt, lambda v: False)(instance) for tt in types):
            errors.append(f"{path}: expected type {t}, got {type(instance).__name__}")
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match pattern {schema['pattern']}")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property {req!r}")
        for k, v in instance.items():
            if k in props:
                validate(v, props[k], root, f"{path}.{k}", errors, _depth + 1)
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errors.append(f"{path}: additional property {k!r} not allowed")
                elif isinstance(ap, dict):
                    validate(v, ap, root, f"{path}.{k}", errors, _depth + 1)
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen = []
            for it in instance:
                if it in seen:
                    errors.append(f"{path}: duplicate item {it!r}")
                    break
                seen.append(it)
        if "items" in schema:
            for i, it in enumerate(instance):
                validate(it, schema["items"], root, f"{path}[{i}]", errors, _depth + 1)
    return errors


def is_valid(instance, schema):
    return not validate(instance, schema)
