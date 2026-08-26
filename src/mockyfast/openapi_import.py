"""Turning an OpenAPI document into a starting configuration.

A spec already describes the API a client expects, so writing the mock by hand
means transcribing it. `mkf init --from-openapi` reads the document and writes
the routes that answer it, mapping each response schema onto the templates
MockyFast already renders so the mock returns plausible data rather than empty
objects.

This is a starting point, not a translation. A spec says what an API *may*
return; a mock says what it *does* return. One response is picked per
operation - the lowest success status - and the result is meant to be edited.
"""

import copy
import math
from pathlib import Path
from typing import Any

import yaml

# The order operations are written in, so a generated config reads like the
# spec it came from rather than like a dictionary.
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

STRING_FORMATS = {
    "uuid": "{{uuid}}",
    "date-time": "{{now}}",
    "date": "{{now:%Y-%m-%d}}",
    "email": "user@example.com",
    "uri": "https://example.com",
    "url": "https://example.com",
    "hostname": "example.com",
    "ipv4": "127.0.0.1",
    "password": "s3cret",
    "byte": "bW9ja3lmYXN0",
}

DEFAULT_INTEGER_RANGE = (1, 1000)

DEFAULT_NUMBER_RANGE = (0, 100)

# Enough items for a list response to look like a list.
ARRAY_ITEMS = 2


def load_openapi_document(path: Path) -> dict:
    """Read a spec written as YAML or as JSON; YAML parses both."""
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI document not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        document = yaml.safe_load(file)

    if not isinstance(document, dict):
        raise ValueError("The OpenAPI document must contain a root object.")

    return document


def check_supported(document: dict) -> None:
    version = document.get("openapi")

    if isinstance(version, str) and version.startswith("3."):
        return

    if "swagger" in document:
        raise ValueError(
            f"MockyFast reads OpenAPI 3 documents, and this one declares "
            f"Swagger {document['swagger']}. Convert it to OpenAPI 3 first."
        )

    raise ValueError(
        "The document must declare an 'openapi' version starting with '3.'."
    )


def resolve_ref(document: dict, ref: Any) -> dict:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(
            f"Only references inside the document are supported, and this one "
            f"points elsewhere: {ref!r}. Bundle the spec into a single file first."
        )

    node: Any = document

    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")

        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"This reference does not resolve: {ref!r}.")

        node = node[key]

    if not isinstance(node, dict):
        raise ValueError(f"This reference does not point at an object: {ref!r}.")

    return node


def schema_type(schema: dict) -> str | None:
    """The type of a schema, ignoring the 'null' an OpenAPI 3.1 union adds."""
    declared = schema.get("type")

    if isinstance(declared, list):
        declared = next((item for item in declared if item != "null"), None)

    return declared if isinstance(declared, str) else None


def merge_all_of(schema: dict, document: dict) -> dict:
    merged: dict[str, Any] = {"type": "object", "properties": {}}

    for part in schema["allOf"]:
        resolved = part

        if isinstance(part, dict) and "$ref" in part:
            resolved = resolve_ref(document, part["$ref"])

        if isinstance(resolved, dict):
            merged["properties"].update(resolved.get("properties") or {})

    return merged


def enum_example(values: list) -> Any:
    """An enum becomes a `{{choice:...}}`, when the template can carry it.

    The template hands back the text of the option it picked, so only a list of
    strings survives the round trip with its type intact. Anything else keeps
    its first value, which is at least of the right type.
    """
    if not values:
        return None

    strings = [value for value in values if isinstance(value, str)]

    if len(strings) != len(values) or any("|" in value for value in strings):
        return values[0]

    return "{{choice:" + "|".join(strings) + "}}"


def numeric_bound(value: Any, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback

    return value


def integer_example(schema: dict) -> str:
    # A bound on an integer is still a JSON number, so a spec generated from
    # Python types writes `maximum: 9999.0` and means 9999.
    low = math.ceil(numeric_bound(schema.get("minimum"), DEFAULT_INTEGER_RANGE[0]))
    high = math.floor(numeric_bound(schema.get("maximum"), DEFAULT_INTEGER_RANGE[1]))

    if low > high:
        low, high = DEFAULT_INTEGER_RANGE

    return f"{{{{randint:{low}:{high}}}}}"


def number_example(schema: dict) -> str:
    low = numeric_bound(schema.get("minimum"), DEFAULT_NUMBER_RANGE[0])
    high = numeric_bound(schema.get("maximum"), DEFAULT_NUMBER_RANGE[1])

    if low > high:
        low, high = DEFAULT_NUMBER_RANGE

    return f"{{{{randfloat:{low}:{high}}}}}"


def string_example(schema: dict) -> str:
    return STRING_FORMATS.get(schema.get("format"), "string")


def example_for_schema(schema: Any, document: dict, seen: tuple = ()) -> Any:
    """A value a response of this shape could really hold."""
    if not isinstance(schema, dict):
        return {}

    if "$ref" in schema:
        ref = schema["$ref"]

        # A schema that contains itself would otherwise never bottom out.
        if ref in seen:
            return {}

        return example_for_schema(
            resolve_ref(document, ref), document, (*seen, ref)
        )

    # An example written into the spec beats anything that can be inferred.
    for key in ("example", "default"):
        if key in schema:
            return schema[key]

    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]

    if isinstance(schema.get("allOf"), list):
        return example_for_schema(merge_all_of(schema, document), document, seen)

    for key in ("oneOf", "anyOf"):
        alternatives = schema.get(key)
        if isinstance(alternatives, list) and alternatives:
            return example_for_schema(alternatives[0], document, seen)

    if isinstance(schema.get("enum"), list):
        return enum_example(schema["enum"])

    kind = schema_type(schema)

    if kind == "object" or "properties" in schema:
        return {
            str(name): example_for_schema(sub_schema, document, seen)
            for name, sub_schema in (schema.get("properties") or {}).items()
        }

    if kind == "array":
        item = example_for_schema(schema.get("items"), document, seen)
        # Independent copies, or the YAML would come out full of anchors
        # pointing at one shared item.
        return [copy.deepcopy(item) for _ in range(ARRAY_ITEMS)]

    if kind == "integer":
        return integer_example(schema)

    if kind == "number":
        return number_example(schema)

    if kind == "boolean":
        return True

    if kind == "string":
        return string_example(schema)

    return {}


def choose_response(operation: dict) -> tuple[int, dict]:
    """The response a mock should answer with: the lowest success status."""
    responses = operation.get("responses")

    if not isinstance(responses, dict) or not responses:
        return 200, {}

    codes = sorted(int(code) for code in responses if str(code).isdigit())
    successes = [code for code in codes if 200 <= code < 300]

    if successes:
        chosen = successes[0]
    elif "default" in responses:
        return 200, responses["default"] or {}
    elif codes:
        chosen = codes[0]
    else:
        return 200, {}

    # YAML reads `200:` as an integer key, JSON always as a string.
    return chosen, responses.get(str(chosen)) or responses.get(chosen) or {}


def json_media_type(content: dict) -> dict | None:
    if "application/json" in content:
        return content["application/json"]

    for name, media in content.items():
        if "json" in str(name):
            return media

    return None


def response_body(response: dict, document: dict) -> Any:
    content = response.get("content")

    if not isinstance(content, dict):
        return None

    media = json_media_type(content)

    if not isinstance(media, dict):
        return None

    if "example" in media:
        return media["example"]

    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]

    if "schema" not in media:
        return None

    return example_for_schema(media["schema"], document)


def build_route(path: str, method: str, operation: dict, document: dict) -> dict:
    status, response = choose_response(operation)
    body = response_body(response, document)

    entry: dict[str, Any] = {}

    if status != 200:
        entry["status_code"] = status

    entry["body"] = {} if body is None else body

    return {
        "method": method.upper(),
        "path": path if path.startswith("/") else f"/{path}",
        "response": entry,
    }


def path_operations(item: dict, document: dict):
    if "$ref" in item:
        item = resolve_ref(document, item["$ref"])

    for method in HTTP_METHODS:
        operation = item.get(method)

        if isinstance(operation, dict):
            yield method, operation


def build_config_from_openapi(document: dict) -> dict:
    """Derive a MockyFast configuration from an OpenAPI 3 document."""
    check_supported(document)

    paths = document.get("paths")

    if not isinstance(paths, dict) or not paths:
        raise ValueError("The OpenAPI document declares no paths to mock.")

    routes = []

    for path, item in paths.items():
        if not isinstance(item, dict):
            continue

        for method, operation in path_operations(item, document):
            routes.append(build_route(str(path), method, operation, document))

    if not routes:
        raise ValueError("The OpenAPI document declares no operations to mock.")

    return {"routes": routes}
