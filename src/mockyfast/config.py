import json
import re
from pathlib import Path

import yaml

from mockyfast.datasources.csv_source import SUPPORTED_SCHEMA_TYPES
from mockyfast.matchers import COMPARISON_KEYS, iter_matchers
from mockyfast.paths import resolve_data_path
from mockyfast.resources import build_config_from_data, expand_resources

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Suffixes that make `mkf serve <path>` run without a YAML file at all.
DATA_PATH_SUFFIXES = {".json", ".csv"}

GENERATED_CONFIG_NAME = "mockyfast.generated.yaml"

# Methods a mutable data source knows how to serve.
MUTABLE_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Methods that write to the in-memory store.
MUTABLE_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Write methods addressing one existing resource, so they need a 'where'.
MUTABLE_TARGETED_METHODS = {"PUT", "PATCH", "DELETE"}


def is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_config(path: str) -> dict:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError("The YAML file must contain a root object.")

    routes = data.get("routes")
    resources = data.get("resources")

    if routes is None and resources is None:
        raise ValueError("Missing 'routes' or 'resources' key in YAML file.")

    if routes is not None and not isinstance(routes, list):
        raise ValueError("'routes' must be a list.")

    data = expand_resources(data)

    validate_routes(data, path)

    return data


def is_data_path(path: str) -> bool:
    """True when the path is a data file or folder rather than a YAML config."""
    candidate = Path(path)

    if candidate.is_dir():
        return True

    return candidate.suffix.lower() in DATA_PATH_SUFFIXES


def load_config_source(path: str) -> tuple[dict, str]:
    """Load a YAML config, or derive one from a data file or folder.

    Returns the config and the path its relative file references resolve
    against. In data mode that path names a file that is never written: only
    its parent directory matters.
    """
    if not is_data_path(path):
        return load_config(path), path

    config, base_path = build_config_from_data(Path(path))
    config = expand_resources(config)

    generated_path = str(base_path / GENERATED_CONFIG_NAME)
    validate_routes(config, generated_path)

    return config, generated_path


def path_shadows(pattern: str, target: str) -> bool:
    """True when `pattern` swallows every request that `target` would answer."""
    if pattern == target:
        return False

    pattern_parts = pattern.strip("/").split("/")
    target_parts = target.strip("/").split("/")

    if len(pattern_parts) != len(target_parts):
        return False

    has_param = False

    for pattern_part, target_part in zip(pattern_parts, target_parts, strict=True):
        if pattern_part.startswith("{") and pattern_part.endswith("}"):
            if target_part.startswith("{") and target_part.endswith("}"):
                return False

            has_param = True
            continue

        if pattern_part != target_part:
            return False

    return has_param


def collect_warnings(config: dict) -> list[str]:
    """Problems that do not make a config invalid but will surprise the user."""
    warnings = []
    seen: list[tuple[str, str, int]] = []

    for index, route in enumerate(config.get("routes") or [], start=1):
        method = str(route["method"]).upper()
        path = route["path"]

        for earlier_method, earlier_path, earlier_index in seen:
            if earlier_method == method and path_shadows(earlier_path, path):
                warnings.append(
                    f"Route #{index} {method} {path} is unreachable: "
                    f"route #{earlier_index} {earlier_method} {earlier_path} "
                    f"matches those requests first."
                )

        seen.append((method, path, index))

    return warnings


def validate_routes(config: dict, config_path: str) -> None:
    routes = config.get("routes", [])

    for index, route in enumerate(routes, start=1):
        if not isinstance(route, dict):
            raise ValueError(f"Route #{index} must be an object.")

        if "method" not in route:
            raise ValueError(f"Route #{index} is missing 'method'.")

        if "path" not in route:
            raise ValueError(f"Route #{index} is missing 'path'.")

        if "response" not in route:
            raise ValueError(f"Route #{index} is missing 'response'.")

        method = route["method"]
        if not isinstance(method, str):
            raise ValueError(f"'method' in route #{index} must be a string.")

        method = method.upper()
        if method not in HTTP_METHODS:
            allowed = ", ".join(sorted(HTTP_METHODS))
            raise ValueError(f"'method' in route #{index} must be one of: {allowed}.")

        path = route["path"]
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError(
                f"'path' in route #{index} must be a string starting with '/'."
            )

        request = route.get("request")
        if request is not None and not isinstance(request, dict):
            raise ValueError(f"'request' in route #{index} must be an object.")

        if request is not None:
            query = request.get("query")
            if query is not None and not isinstance(query, dict):
                raise ValueError(
                    f"'request.query' in route #{index} must be an object."
                )

            headers = request.get("headers")
            if headers is not None and not isinstance(headers, dict):
                raise ValueError(
                    f"'request.headers' in route #{index} must be an object."
                )

            expected_json = request.get("json")
            if expected_json is not None and not isinstance(
                expected_json, (dict, list)
            ):
                raise ValueError(
                    f"'request.json' in route #{index} must be an object or a list."
                )

            validate_matchers(request, index)

        response = route["response"]

        if not isinstance(response, dict):
            raise ValueError(f"'response' in route #{index} must be an object.")

        has_body = "body" in response
        has_body_from = "body_from" in response
        has_data_source = "data_source" in response

        selected_response_sources = sum([has_body, has_body_from, has_data_source])

        if selected_response_sources > 1:
            raise ValueError(
                f"Route #{index} can only define one of 'body', 'body_from', or 'data_source'."
            )

        if has_body_from:
            load_json_file(config_path, response["body_from"])

        if has_data_source:
            validate_data_source(response["data_source"], config_path, index, method)

        # Checked by key presence: an explicit 'status_code:' with no value is a
        # mistake, not an omission, and would reach JSONResponse as None.
        if "status_code" in response:
            status_code = response["status_code"]

            if not is_integer(status_code):
                raise ValueError(
                    f"'response.status_code' in route #{index} must be an integer."
                )

            if status_code < 100 or status_code > 599:
                raise ValueError(
                    f"'response.status_code' in route #{index} must be a valid HTTP status code."
                )

        if "delay_ms" in response:
            delay_ms = response["delay_ms"]

            if not is_integer(delay_ms):
                raise ValueError(
                    f"'response.delay_ms' in route #{index} must be an integer."
                )

            if delay_ms < 0:
                raise ValueError(
                    f"'response.delay_ms' in route #{index} cannot be negative."
                )


def validate_matchers(request: dict, index: int) -> None:
    """Catch broken matcher operators before the server starts."""
    for matcher in iter_matchers(request):
        if "matches" in matcher:
            try:
                re.compile(str(matcher["matches"]))
            except re.error as exc:
                raise ValueError(
                    f"'request' in route #{index} has an invalid regular "
                    f"expression {matcher['matches']!r}: {exc}"
                ) from exc

        if "one_of" in matcher and not isinstance(matcher["one_of"], list):
            raise ValueError(
                f"'one_of' in route #{index} must be a list."
            )

        for operator in COMPARISON_KEYS:
            if operator in matcher and not isinstance(
                matcher[operator], (int, float)
            ):
                raise ValueError(
                    f"'{operator}' in route #{index} must be a number."
                )


def validate_data_source(
    data_source: dict,
    config_path: str,
    index: int,
    method: str,
) -> None:
    if not isinstance(data_source, dict):
        raise ValueError(f"'response.data_source' in route #{index} must be an object.")

    source_type = data_source.get("type")
    if source_type not in {"csv", "json"}:
        raise ValueError(
            f"'response.data_source.type' in route #{index} must be 'csv' or 'json'."
        )

    file_path = data_source.get("file")
    if not isinstance(file_path, str):
        raise ValueError(
            f"'response.data_source.file' in route #{index} must be a string."
        )

    if source_type == "csv":
        load_csv_file_reference(config_path, file_path)
    else:
        load_json_file(config_path, file_path)

    mutable = data_source.get("mutable")
    if mutable is not None and not isinstance(mutable, bool):
        raise ValueError(
            f"'response.data_source.mutable' in route #{index} must be a boolean."
        )

    # 'mode' shapes a read response, so it carries no meaning on a write route.
    mode = data_source.get("mode")
    mode_is_optional = bool(mutable) and method in MUTABLE_WRITE_METHODS

    if not (mode is None and mode_is_optional) and mode not in {"first", "all"}:
        raise ValueError(
            f"'response.data_source.mode' in route #{index} must be 'first' or 'all'."
        )

    where = data_source.get("where")
    if where is not None:
        if not isinstance(where, dict):
            raise ValueError(
                f"'response.data_source.where' in route #{index} must be an object."
            )

        key_name = "column" if source_type == "csv" else "field"
        if key_name not in where:
            raise ValueError(
                f"'response.data_source.where.{key_name}' in route #{index} is required."
            )

        has_path_param = "equals_path_param" in where
        has_query_param = "equals_query_param" in where

        if has_path_param == has_query_param:
            raise ValueError(
                f"'response.data_source.where' in route #{index} must define exactly one of "
                f"'equals_path_param' or 'equals_query_param'."
            )

    wrap = data_source.get("wrap")
    if wrap is not None and not isinstance(wrap, str):
        raise ValueError(
            f"'response.data_source.wrap' in route #{index} must be a string."
        )

    if "not_found_status" in data_source:
        not_found_status = data_source["not_found_status"]

        if not is_integer(not_found_status):
            raise ValueError(
                f"'response.data_source.not_found_status' in route #{index} must be an integer."
            )

        if not_found_status < 100 or not_found_status > 599:
            raise ValueError(
                f"'response.data_source.not_found_status' in route #{index} "
                f"must be a valid HTTP status code."
            )

    not_found_body = data_source.get("not_found_body")
    if not_found_body is not None and not isinstance(
        not_found_body, (dict, list, str, int, float, bool)
    ):
        raise ValueError(
            f"'response.data_source.not_found_body' in route #{index} "
            f"must be a valid JSON-compatible value."
        )

    coerce_types = data_source.get("coerce_types")
    if coerce_types is not None and not isinstance(coerce_types, bool):
        raise ValueError(
            f"'response.data_source.coerce_types' in route #{index} must be a boolean."
        )

    schema = data_source.get("schema")
    if schema is not None:
        if source_type != "csv":
            raise ValueError(
                f"'response.data_source.schema' in route #{index} "
                f"is only supported for 'csv' data sources."
            )

        if not isinstance(schema, dict):
            raise ValueError(
                f"'response.data_source.schema' in route #{index} must be an object."
            )

        for field_name, field_type in schema.items():
            if not isinstance(field_name, str):
                raise ValueError(
                    f"'response.data_source.schema' in route #{index} must use string field names."
                )

            if field_type not in SUPPORTED_SCHEMA_TYPES:
                allowed = ", ".join(sorted(SUPPORTED_SCHEMA_TYPES))
                raise ValueError(
                    f"'response.data_source.schema.{field_name}' in route #{index} "
                    f"must be one of: {allowed}."
                )

    key_field = data_source.get("key_field")
    if key_field is not None and not isinstance(key_field, str):
        raise ValueError(
            f"'response.data_source.key_field' in route #{index} must be a string."
        )

    resource_name = data_source.get("resource_name")
    if resource_name is not None and not isinstance(resource_name, str):
        raise ValueError(
            f"'response.data_source.resource_name' in route #{index} must be a string."
        )

    if mutable:
        if not key_field:
            raise ValueError(
                f"'response.data_source.key_field' in route #{index} "
                f"is required when mutable is true."
            )

        # Without an explicit name the store falls back to the route path, so
        # /users and /users/{user_id} would silently hold separate copies.
        if not resource_name:
            raise ValueError(
                f"'response.data_source.resource_name' in route #{index} "
                f"is required when mutable is true."
            )

        if method not in MUTABLE_METHODS:
            allowed = ", ".join(sorted(MUTABLE_METHODS))
            raise ValueError(
                f"'method' in route #{index} must be one of: {allowed} when mutable is true."
            )

        if method in MUTABLE_TARGETED_METHODS and where is None:
            raise ValueError(
                f"'response.data_source.where' in route #{index} is required "
                f"for {method} on a mutable data source."
            )


def load_json_file(config_path: str, relative_json_path: str):
    json_path = resolve_data_path(config_path, relative_json_path, "JSON")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_csv_file_reference(config_path: str, relative_csv_path: str) -> None:
    resolve_data_path(config_path, relative_csv_path, "CSV")
