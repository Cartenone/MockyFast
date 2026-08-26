"""Checking a mock against the spec it is standing in for.

A mock drifts quietly. A field gets renamed in the real API, or a status code
is added, and the mock keeps answering what it always did, so the tests written
against it keep passing and the client breaks in production.

`mkf validate CONFIG --against spec.yaml` compares what each route answers with
what the document declares for the same operation, and reports the differences.
It compares the response a route really produces - rendered templates, real
rows from the data file - rather than the configuration that describes it.
"""

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from mockyfast.config import iter_route_responses
from mockyfast.openapi import response_content
from mockyfast.openapi_import import (
    HTTP_METHODS,
    check_supported,
    json_media_type,
    merge_all_of,
    resolve_ref,
)

PATH_PARAMETER = re.compile(r"\{[^{}]+\}")

TEMPLATE = re.compile(r"\{\{.*?\}\}|\{[A-Za-z_][A-Za-z0-9_]*\}")

TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float))
    and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "null": lambda value: value is None,
}

TYPE_NAMES = {
    str: "a string",
    bool: "a boolean",
    int: "an integer",
    float: "a number",
    dict: "an object",
    list: "a list",
}

# The same names, keyed by what a schema calls them.
DECLARED_NAMES = {
    "string": "a string",
    "integer": "an integer",
    "number": "a number",
    "boolean": "a boolean",
    "object": "an object",
    "array": "a list",
    "null": "null",
}


@dataclass
class ConformanceReport:
    """What comparing a configuration with a document turned up."""

    problems: list[str] = field(default_factory=list)
    checked_routes: int = 0
    uncovered_operations: int = 0


def normalize_path(path: str) -> str:
    """A path with its parameter names removed, so `{id}` and `{userId}` meet."""
    return PATH_PARAMETER.sub("{}", path.rstrip("/") or "/")


def spec_operations(document: dict) -> dict[tuple[str, str], dict]:
    operations = {}

    for path, item in (document.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue

        if "$ref" in item:
            item = resolve_ref(document, item["$ref"])

        for method in HTTP_METHODS:
            operation = item.get(method)

            if isinstance(operation, dict):
                operations[(method.upper(), normalize_path(str(path)))] = operation

    return operations


def declared_paths(document: dict) -> set[str]:
    return {
        normalize_path(str(path)) for path in (document.get("paths") or {}) if path
    }


def dereference(schema: Any, document: dict, seen: tuple) -> tuple[dict | None, tuple]:
    """Follow `$ref` and flatten `allOf`, stopping if a schema contains itself."""
    if not isinstance(schema, dict):
        return None, seen

    while "$ref" in schema:
        ref = schema["$ref"]

        if ref in seen:
            return None, seen

        seen = (*seen, ref)
        schema = resolve_ref(document, ref)

    if isinstance(schema.get("allOf"), list):
        schema = merge_all_of(schema, document)

    return schema, seen


def declared_types(schema: dict) -> list[str]:
    declared = schema.get("type")

    if isinstance(declared, list):
        return [item for item in declared if isinstance(item, str)]

    return [declared] if isinstance(declared, str) else []


def type_allows(schema: dict, value: Any) -> bool:
    kinds = declared_types(schema)

    if not kinds:
        return True

    return any(TYPE_CHECKS.get(kind, lambda _: True)(value) for kind in kinds)


def describe_value(value: Any) -> str:
    if value is None:
        return "null"

    return TYPE_NAMES.get(type(value), "a value")


def looks_templated(value: Any) -> bool:
    """A placeholder that could not be rendered says nothing about the type."""
    return isinstance(value, str) and TEMPLATE.search(value) is not None


def join(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def compare_object(
    value: dict,
    schema: dict,
    document: dict,
    prefix: str,
    seen: tuple,
) -> list[str]:
    problems = []
    properties = schema.get("properties") or {}

    # A schema with no properties describes a free-form object, and every key
    # in the response is as declared as any other.
    if not properties:
        return problems

    for name in value:
        if name in properties:
            continue

        close = difflib.get_close_matches(str(name), list(properties), n=1)
        hint = f" The spec declares '{close[0]}'." if close else ""

        problems.append(
            f"field '{join(prefix, str(name))}' is not declared in the spec.{hint}"
        )

    for name in schema.get("required") or []:
        if name not in value:
            problems.append(
                f"field '{join(prefix, str(name))}' is required by the spec, "
                f"and the response does not carry it."
            )

    for name, sub_schema in properties.items():
        if name in value:
            problems.extend(
                compare_value(
                    value[name], sub_schema, document, join(prefix, str(name)), seen
                )
            )

    return problems


def compare_value(
    value: Any,
    schema: Any,
    document: dict,
    prefix: str,
    seen: tuple = (),
) -> list[str]:
    resolved, seen = dereference(schema, document, seen)

    if resolved is None:
        return []

    # An alternation says the value may take several shapes; reporting against
    # the first would be guessing.
    if any(key in resolved for key in ("oneOf", "anyOf")):
        return []

    if looks_templated(value):
        return []

    if not type_allows(resolved, value):
        expected = " or ".join(
            DECLARED_NAMES.get(kind, kind) for kind in declared_types(resolved)
        )
        where = f"field '{prefix}'" if prefix else "the response body"

        return [f"{where} is {describe_value(value)}, and the spec declares {expected}."]

    kinds = declared_types(resolved)

    if isinstance(value, dict) and ("object" in kinds or "properties" in resolved):
        return compare_object(value, resolved, document, prefix, seen)

    if isinstance(value, list) and "array" in kinds and value:
        return compare_value(
            value[0], resolved.get("items"), document, f"{prefix}[]", seen
        )

    return []


def status_is_declared(operation: dict, status: int) -> bool:
    responses = operation.get("responses")

    if not isinstance(responses, dict):
        return False

    if "default" in responses:
        return True

    keys = {str(key) for key in responses}

    return str(status) in keys or f"{status // 100}XX" in keys


def declared_statuses(operation: dict) -> str:
    responses = operation.get("responses")

    if not isinstance(responses, dict) or not responses:
        return "none"

    return ", ".join(sorted(str(key) for key in responses))


def response_statuses(response: dict) -> list[int]:
    """Every status one response entry can answer with."""
    statuses = [response.get("status_code", 200)]

    data_source = response.get("data_source")
    if isinstance(data_source, dict) and (
        data_source.get("mode") == "first" or data_source.get("mutable")
    ):
        statuses.append(data_source.get("not_found_status", 404))

    fault = response.get("fault")
    if isinstance(fault, dict):
        statuses.append(fault.get("status_code", 500))

    return statuses


def spec_response_schema(operation: dict, status: int) -> Any:
    responses = operation.get("responses")

    if not isinstance(responses, dict):
        return None

    entry = responses.get(str(status)) or responses.get(status)

    if entry is None:
        entry = responses.get(f"{status // 100}XX") or responses.get("default")

    if not isinstance(entry, dict):
        return None

    content = entry.get("content")

    if not isinstance(content, dict):
        return None

    media = json_media_type(content)

    return media.get("schema") if isinstance(media, dict) else None


def check_route(
    route: dict,
    index: int,
    config_path: str,
    document: dict,
    operations: dict,
    paths: set[str],
) -> list[str]:
    method = str(route["method"]).upper()
    path = route["path"]
    label = f"Route #{index} {method} {path}"

    if normalize_path(path) not in paths:
        return [f"{label} answers a path the spec does not declare."]

    operation = operations.get((method, normalize_path(path)))

    if operation is None:
        return [f"{label}: the spec declares no {method} for that path."]

    problems = []

    for response in iter_route_responses(route):
        for status in response_statuses(response):
            if not status_is_declared(operation, status):
                problems.append(
                    f"{label}: the spec declares no status {status} for it, "
                    f"only {declared_statuses(operation)}."
                )

        schema = spec_response_schema(operation, response.get("status_code", 200))

        if schema is None:
            continue

        _, example = response_content(response, config_path)

        if example is None:
            continue

        problems.extend(
            f"{label}: {problem}"
            for problem in compare_value(example, schema, document, "")
        )

    return problems


def check_against_spec(
    config: dict, config_path: str, document: dict
) -> ConformanceReport:
    """Compare what a configuration answers with what a document declares."""
    check_supported(document)

    operations = spec_operations(document)
    paths = declared_paths(document)

    report = ConformanceReport()
    answered = set()

    for index, route in enumerate(config.get("routes") or [], start=1):
        report.checked_routes += 1
        answered.add((str(route["method"]).upper(), normalize_path(route["path"])))

        report.problems.extend(
            check_route(route, index, config_path, document, operations, paths)
        )

    report.uncovered_operations = len(set(operations) - answered)

    # The same problem can reach here once per response of a sequence.
    report.problems = list(dict.fromkeys(report.problems))

    return report
