"""An OpenAPI document describing what the mock actually answers.

FastAPI builds `/openapi.json` from the signature of each endpoint, and every
route here is served by the same generic handler, so the page it produced was a
list of identical `Handler` operations with empty schemas.

The configuration knows what the signature cannot: the status codes a route can
return, the shape of the data behind it, the parameters it matches on. This
builds the document from that instead. Everything in it is inferred, so a data
file that cannot be read costs a schema, never a running server.
"""

import re
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from mockyfast.config import iter_route_responses, load_json_file
from mockyfast.datasources.csv_source import load_csv_rows, normalize_rows
from mockyfast.datasources.json_source import load_json_rows
from mockyfast.matchers import is_matcher
from mockyfast.templating import TemplateContext, render_template

OPENAPI_VERSION = "3.1.0"

PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")

WRITE_SUMMARIES = {
    "POST": "Create",
    "PUT": "Replace",
    "PATCH": "Update",
    "DELETE": "Delete",
}

LIST_QUERY_PARAMETERS = {
    "_limit": ("integer", "Page size."),
    "_page": ("integer", "Page number, 1-based, used together with _limit."),
    "_offset": ("integer", "Rows to skip, as an alternative to _page."),
    "_sort": ("string", "Field to sort by; several are separated by commas."),
    "_order": ("string", "'desc' reverses the sort."),
}


def mockyfast_version() -> str:
    try:
        return version("mockyfast")
    except PackageNotFoundError:
        return "0"


def group_routes(routes: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Routes by the (method, path) pair they are registered under.

    Several routes can share one pair and be told apart by their matchers; the
    server registers one endpoint for the group, and the document describes one
    operation for it.
    """
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for route in routes:
        grouped[(str(route["method"]).upper(), route["path"])].append(route)

    return grouped


# --------------------------------------------------------------- schema shapes


def json_schema_for(value: Any) -> dict:
    """The schema of one JSON value, read off the value itself."""
    if isinstance(value, bool):
        return {"type": "boolean"}

    if isinstance(value, int):
        return {"type": "integer"}

    if isinstance(value, float):
        return {"type": "number"}

    if isinstance(value, str):
        return {"type": "string"}

    if isinstance(value, list):
        return {
            "type": "array",
            "items": merge_schemas([json_schema_for(item) for item in value]),
        }

    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {
                str(key): json_schema_for(item) for key, item in value.items()
            },
        }

    return {}


def merge_schemas(schemas: list[dict]) -> dict:
    """One schema covering several values, left open where they disagree."""
    if not schemas:
        return {}

    if all(schema == schemas[0] for schema in schemas):
        return schemas[0]

    if all(schema.get("type") == "object" for schema in schemas):
        properties: dict[str, list[dict]] = defaultdict(list)

        for schema in schemas:
            for key, sub_schema in schema.get("properties", {}).items():
                properties[key].append(sub_schema)

        return {
            "type": "object",
            "properties": {
                key: merge_schemas(found) for key, found in properties.items()
            },
        }

    types = {schema.get("type") for schema in schemas}

    return {"type": types.pop()} if len(types) == 1 and None not in types else {}


def rows_schema(rows: list[dict]) -> dict:
    """The schema of one row, merged across every row of a data source."""
    if not rows:
        return {"type": "object"}

    schema = merge_schemas([json_schema_for(row) for row in rows])

    shared = set(rows[0])
    for row in rows[1:]:
        shared &= set(row)

    if shared and schema.get("type") == "object":
        schema["required"] = sorted(shared)

    return schema


def read_rows(data_source: dict, config_path: str) -> list[dict] | None:
    """The rows a data source serves, or None when the file cannot be read.

    `mkf validate` is what reports an unreadable file. Here it only means the
    document has nothing to say about that route's shape.
    """
    try:
        if data_source["type"] == "csv":
            return normalize_rows(
                load_csv_rows(config_path, data_source["file"]),
                schema=data_source.get("schema"),
                coerce_types=data_source.get("coerce_types", False),
            )

        return load_json_rows(config_path, data_source["file"])
    except (OSError, ValueError):
        return None


def data_source_content(data_source: dict, config_path: str) -> tuple[dict, Any]:
    rows = read_rows(data_source, config_path)
    row_schema = rows_schema(rows) if rows is not None else {"type": "object"}

    if data_source.get("mode") == "all":
        schema: dict = {"type": "array", "items": row_schema}
        example: Any = rows[:2] if rows else []
    else:
        schema = row_schema
        example = rows[0] if rows else None

    wrap = data_source.get("wrap")
    if wrap is not None:
        schema = {"type": "object", "properties": {wrap: schema}}
        example = {wrap: example}

    return schema, example


def rendered_content(body: Any) -> tuple[dict, Any]:
    """A template renders to the type it will really have, so infer from that.

    `"{{randint:1:5}}"` is a string in the file and a number in the response;
    reading the schema off the rendered value keeps the document honest.
    """
    rendered = render_template(body, TemplateContext())

    return json_schema_for(rendered), rendered


def response_content(response: dict, config_path: str) -> tuple[dict, Any]:
    data_source = response.get("data_source")

    if data_source is not None:
        return data_source_content(data_source, config_path)

    if "body_from" in response:
        try:
            return rendered_content(load_json_file(config_path, response["body_from"]))
        except (OSError, ValueError):
            return {}, None

    return rendered_content(response.get("body", {}))


def schema_from_matcher(expected: Any) -> dict:
    """The shape a `request.json` matcher demands, with operators left open."""
    if is_matcher(expected):
        return {}

    if isinstance(expected, dict):
        return {
            "type": "object",
            "properties": {
                str(key): schema_from_matcher(value) for key, value in expected.items()
            },
        }

    if isinstance(expected, list):
        return {
            "type": "array",
            "items": merge_schemas([schema_from_matcher(item) for item in expected]),
        }

    return json_schema_for(expected)


# ------------------------------------------------------------------ parameters


def where_descriptions(group: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """What each `where` reads, keyed by the path and query parameter it uses."""
    from_path: dict[str, str] = {}
    from_query: dict[str, str] = {}

    for route in group:
        for response in iter_route_responses(route):
            where = (response.get("data_source") or {}).get("where")

            if not where:
                continue

            field = where.get("column") or where.get("field")
            description = f"Selects the rows whose '{field}' equals this value."

            if "equals_path_param" in where:
                from_path[where["equals_path_param"]] = description
            elif "equals_query_param" in where:
                from_query[where["equals_query_param"]] = description

    return from_path, from_query


def uses_list_query(group: list[dict]) -> bool:
    return any(
        (response.get("data_source") or {}).get("list_query", False)
        for route in group
        for response in iter_route_responses(route)
    )


def matched_values(group: list[dict], key: str) -> dict[str, Any]:
    """Every `request.query` or `request.headers` name the group matches on."""
    names: dict[str, Any] = {}

    for route in group:
        for name, expected in ((route.get("request") or {}).get(key) or {}).items():
            names.setdefault(name, expected)

    return names


def describe_expectation(expected: Any) -> str:
    if is_matcher(expected):
        operators = ", ".join(sorted(expected))
        return f"Matched by a route on this path ({operators})."

    return f"Matched by a route on this path, against {expected!r}."


def build_parameters(group: list[dict], path: str) -> list[dict]:
    from_path, from_query = where_descriptions(group)

    parameters = [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "description": from_path.get(name, "Path parameter."),
        }
        for name in PATH_PARAMETER.findall(path)
    ]

    for name, expected in matched_values(group, "query").items():
        parameters.append(
            {
                "name": name,
                "in": "query",
                # A route further down the group may answer without it.
                "required": False,
                "schema": {"type": "string"},
                "description": describe_expectation(expected),
            }
        )

    for name, description in from_query.items():
        parameters.append(
            {
                "name": name,
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "description": description,
            }
        )

    if uses_list_query(group):
        for name, (kind, description) in LIST_QUERY_PARAMETERS.items():
            parameters.append(
                {
                    "name": name,
                    "in": "query",
                    "required": False,
                    "schema": {"type": kind},
                    "description": description,
                }
            )

    for name, expected in matched_values(group, "headers").items():
        parameters.append(
            {
                "name": name,
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": describe_expectation(expected),
            }
        )

    return deduplicate_parameters(parameters)


def deduplicate_parameters(parameters: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}

    for parameter in parameters:
        seen.setdefault((parameter["name"], parameter["in"]), parameter)

    return list(seen.values())


# ------------------------------------------------------------------- responses


def media_type(schema: dict, example: Any) -> dict:
    content = {"schema": schema}

    if example is not None:
        content["example"] = example

    return {"application/json": content}


def add_response(
    responses: dict,
    status: int,
    description: str,
    schema: dict,
    example: Any = None,
    headers: dict | None = None,
) -> None:
    """Record a status this operation can answer with, merging repeats.

    Two routes on one path can answer the same status with different bodies;
    the merged schema stays true for both rather than describing only the first.
    """
    key = str(status)
    existing = responses.get(key)

    if existing is None:
        responses[key] = {
            "description": description,
            "content": media_type(schema, example),
        }

        if headers:
            responses[key]["headers"] = headers

        return

    current = existing["content"]["application/json"]
    current["schema"] = merge_schemas([current["schema"], schema])

    if headers:
        existing.setdefault("headers", {}).update(headers)


def total_count_header() -> dict:
    return {
        "X-Total-Count": {
            "description": "Number of rows before paging.",
            "schema": {"type": "integer"},
        }
    }


def add_data_source_responses(
    responses: dict,
    data_source: dict,
    method: str,
) -> None:
    mutable = bool(data_source.get("mutable"))

    not_found_needed = data_source.get("mode") == "first" or (
        mutable and method in {"PUT", "PATCH", "DELETE"}
    )

    if not_found_needed:
        not_found_body = data_source.get(
            "not_found_body", {"detail": "Resource not found"}
        )
        add_response(
            responses,
            data_source.get("not_found_status", 404),
            "Nothing matched.",
            json_schema_for(not_found_body),
            not_found_body,
        )

    if not mutable or method not in {"POST", "PUT", "PATCH"}:
        return

    add_response(
        responses,
        400,
        "The request body is not a JSON object, is missing the key field, "
        "or tries to change it.",
        json_schema_for({"detail": "string"}),
    )

    if method == "POST":
        add_response(
            responses,
            409,
            "A resource with that key field already exists.",
            json_schema_for({"detail": "string"}),
        )


def build_responses(group: list[dict], method: str, config_path: str) -> dict:
    responses: dict = {}

    for route in group:
        for response in iter_route_responses(route):
            data_source = response.get("data_source")
            headers = None

            if data_source and data_source.get("list_query", False):
                headers = total_count_header()

            if data_source and data_source.get("mutable") and method == "DELETE":
                schema, example = json_schema_for({"deleted": True}), {"deleted": True}
            else:
                schema, example = response_content(response, config_path)

            add_response(
                responses,
                response.get("status_code", 200),
                "The mocked response.",
                schema,
                example,
                headers,
            )

            if data_source:
                add_data_source_responses(responses, data_source, method)

            fault = response.get("fault")
            if isinstance(fault, dict):
                fault_body = fault.get("body", {"detail": "Injected fault"})
                add_response(
                    responses,
                    fault.get("status_code", 500),
                    "Injected fault.",
                    json_schema_for(fault_body),
                    fault_body,
                )

    if not responses:
        responses["200"] = {"description": "The mocked response."}

    return responses


def build_request_body(group: list[dict], method: str, config_path: str) -> dict | None:
    if method not in {"POST", "PUT", "PATCH"}:
        return None

    for route in group:
        expected_json = (route.get("request") or {}).get("json")

        if expected_json is not None:
            return {
                "required": True,
                "description": "The body the route matches on.",
                "content": media_type(schema_from_matcher(expected_json), None),
            }

        for response in iter_route_responses(route):
            data_source = response.get("data_source")

            if not data_source or not data_source.get("mutable"):
                continue

            rows = read_rows(data_source, config_path)
            schema = rows_schema(rows) if rows is not None else {"type": "object"}

            if method == "PATCH":
                # A merge only needs the fields it changes.
                schema = {
                    key: value for key, value in schema.items() if key != "required"
                }

            return {
                "required": True,
                "description": "The resource to write.",
                "content": media_type(schema, rows[0] if rows else None),
            }

    return None


# ---------------------------------------------------------------- descriptions


def resource_label(path: str) -> str:
    parts = [
        part
        for part in path.strip("/").split("/")
        if not (part.startswith("{") and part.endswith("}"))
    ]

    return parts[-1] if parts else "root"


def build_summary(group: list[dict], method: str, path: str) -> str:
    label = resource_label(path)

    for route in group:
        for response in iter_route_responses(route):
            data_source = response.get("data_source")

            if data_source is None:
                continue

            if method == "GET":
                return (
                    f"List {label}"
                    if data_source.get("mode") == "all"
                    else f"Get one {label}"
                )

            if method in WRITE_SUMMARIES:
                return f"{WRITE_SUMMARIES[method]} {label}"

    for route in group:
        if route.get("responses"):
            return f"Response sequence of {len(route['responses'])} calls"

    if len(group) > 1:
        return "Static response, selected by request matching"

    return "Static response"


def describe_source(route: dict) -> str:
    """Where a route's body comes from, without naming a file on disk.

    The document is served over the network, so it says what kind of source
    answers rather than where it lives.
    """
    if route.get("responses"):
        return f"a sequence of {len(route['responses'])} responses, one per call"

    response = route.get("response") or {}
    data_source = response.get("data_source")

    if data_source is not None:
        kind = "writable" if data_source.get("mutable") else "read-only"
        return f"a {kind} {data_source['type']} data source"

    if "body_from" in response:
        return "a body read from a JSON file"

    return "an inline body"


def describe_conditions(route: dict) -> str:
    request = route.get("request") or {}
    conditions = []

    for key in ("query", "headers"):
        names = request.get(key)
        if names:
            conditions.append(f"{key} {', '.join(sorted(names))} match")

    if request.get("json") is not None:
        conditions.append("the JSON body matches")

    return f"when {' and '.join(conditions)}" if conditions else "otherwise"


def build_description(group: list[dict]) -> str:
    if len(group) == 1:
        return f"Served from {describe_source(group[0])}."

    lines = [
        "Several routes answer this path. The first one whose conditions match "
        "wins:",
        "",
    ]

    for position, route in enumerate(group, start=1):
        lines.append(
            f"{position}. {describe_conditions(route)} - {describe_source(route)}"
        )

    return "\n".join(lines)


def operation_id(method: str, path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_") or "root"

    return f"{method.lower()}_{slug}"


# ----------------------------------------------------------------- the document


def build_operation(
    group: list[dict],
    method: str,
    path: str,
    config_path: str,
) -> dict:
    operation = {
        "summary": build_summary(group, method, path),
        "description": build_description(group),
        "operationId": operation_id(method, path),
        "tags": [resource_label(path)],
        "responses": build_responses(group, method, config_path),
    }

    parameters = build_parameters(group, path)
    if parameters:
        operation["parameters"] = parameters

    request_body = build_request_body(group, method, config_path)
    if request_body is not None:
        operation["requestBody"] = request_body

    return operation


def build_openapi(config: dict, config_path: str) -> dict:
    """The OpenAPI document for a loaded configuration."""
    paths: dict[str, dict] = {}

    for (method, path), group in group_routes(config.get("routes") or []).items():
        paths.setdefault(path, {})[method.lower()] = build_operation(
            group, method, path, config_path
        )

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "MockyFast",
            "version": mockyfast_version(),
            "description": (
                "A mock API served by MockyFast. Every schema and example below "
                "is inferred from the configuration and the data behind it."
            ),
        },
        "paths": paths,
    }
