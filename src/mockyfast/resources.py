"""Shorthand that expands a resource declaration into CRUD routes.

Writing the five routes of a REST resource by hand means repeating the same
data source block five times. A `resources:` entry describes the resource once
and expands to the equivalent `routes:` entries before validation runs, so
everything downstream keeps working on plain routes.
"""

import csv
import json
from pathlib import Path
from typing import Any

DEFAULT_KEY_FIELD = "id"

SUPPORTED_SOURCE_TYPES = {"csv", "json"}

DATA_FILE_SUFFIXES = {".json": "json", ".csv": "csv"}

# Each action maps to the HTTP methods it generates and whether it addresses a
# single resource (and therefore needs a path parameter).
RESOURCE_ACTIONS: dict[str, tuple[tuple[str, ...], bool]] = {
    "list": (("GET",), False),
    "get": (("GET",), True),
    "create": (("POST",), False),
    "update": (("PUT", "PATCH"), True),
    "delete": (("DELETE",), True),
}

DEFAULT_ACTIONS = ["list", "get", "create", "update", "delete"]


def where_key_for(source_type: str) -> str:
    return "column" if source_type == "csv" else "field"


def build_data_source(
    source_type: str,
    file_path: str,
    key_field: str,
    resource_name: str,
) -> dict[str, Any]:
    return {
        "type": source_type,
        "file": file_path,
        "mutable": True,
        "key_field": key_field,
        "resource_name": resource_name,
    }


def apply_not_found(data_source: dict, resource: dict) -> None:
    if "not_found_status" in resource:
        data_source["not_found_status"] = resource["not_found_status"]

    if "not_found_body" in resource:
        data_source["not_found_body"] = resource["not_found_body"]


def validate_resource(resource: Any, index: int) -> None:
    label = f"Resource #{index}"

    if not isinstance(resource, dict):
        raise ValueError(f"{label} must be an object.")

    name = resource.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"'name' in {label.lower()} must be a non-empty string.")

    path = resource.get("path", f"/{name}")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError(
            f"'path' in {label.lower()} must be a string starting with '/'."
        )

    source = resource.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"'source' in {label.lower()} must be an object.")

    if source.get("type") not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"'source.type' in {label.lower()} must be 'csv' or 'json'.")

    if not isinstance(source.get("file"), str):
        raise ValueError(f"'source.file' in {label.lower()} must be a string.")

    key_field = resource.get("key_field", DEFAULT_KEY_FIELD)
    if not isinstance(key_field, str) or not key_field:
        raise ValueError(f"'key_field' in {label.lower()} must be a non-empty string.")

    actions = resource.get("methods", DEFAULT_ACTIONS)
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"'methods' in {label.lower()} must be a non-empty list.")

    for action in actions:
        if action not in RESOURCE_ACTIONS:
            allowed = ", ".join(DEFAULT_ACTIONS)
            raise ValueError(
                f"'methods' in {label.lower()} must only contain: {allowed}."
            )


def build_resource_routes(resource: dict, index: int) -> list[dict[str, Any]]:
    validate_resource(resource, index)

    name = resource["name"]
    path = resource.get("path", f"/{name}")
    source = resource["source"]
    source_type = source["type"]
    file_path = source["file"]
    key_field = resource.get("key_field", DEFAULT_KEY_FIELD)
    actions = resource.get("methods", DEFAULT_ACTIONS)

    detail_path = f"{path}/{{{key_field}}}"
    where = {
        where_key_for(source_type): key_field,
        "equals_path_param": key_field,
    }

    routes: list[dict[str, Any]] = []

    for action in actions:
        methods, targets_one = RESOURCE_ACTIONS[action]

        for method in methods:
            data_source = build_data_source(source_type, file_path, key_field, name)

            if action == "list":
                data_source["mode"] = "all"
                if "wrap" in resource:
                    data_source["wrap"] = resource["wrap"]
            elif action == "get":
                data_source["mode"] = "first"

            if targets_one:
                data_source["where"] = dict(where)
                apply_not_found(data_source, resource)

            response: dict[str, Any] = {"data_source": data_source}

            if action == "create":
                response["status_code"] = 201

            if "delay_ms" in resource:
                response["delay_ms"] = resource["delay_ms"]

            routes.append(
                {
                    "method": method,
                    "path": detail_path if targets_one else path,
                    "response": response,
                }
            )

    return routes


def expand_resources(config: dict) -> dict:
    """Return a config whose 'resources' entries have become 'routes'."""
    resources = config.get("resources")

    if resources is None:
        return config

    if not isinstance(resources, list):
        raise ValueError("'resources' must be a list.")

    generated: list[dict[str, Any]] = []
    seen_names: dict[str, int] = {}

    for index, resource in enumerate(resources, start=1):
        routes = build_resource_routes(resource, index)
        name = resource["name"]

        # The name is the store identity, so two resources sharing it would
        # silently serve one another's data.
        if name in seen_names:
            raise ValueError(
                f"Resource #{index} reuses the name '{name}' already taken by "
                f"resource #{seen_names[name]}; resource names must be unique."
            )

        seen_names[name] = index
        generated.extend(routes)

    declared = config.get("routes") or []
    if not isinstance(declared, list):
        raise ValueError("'routes' must be a list.")

    expanded = dict(config)

    # Declared routes come first so an explicit /users/me still wins over the
    # generated /users/{id}.
    expanded["routes"] = list(declared) + generated

    return expanded


def detect_key_field(data_file: Path, source_type: str) -> str:
    """Pick the key field of a data file: 'id' when present, else the first column."""
    try:
        if source_type == "csv":
            with data_file.open("r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                fields = reader.fieldnames or []
        else:
            with data_file.open("r", encoding="utf-8") as file:
                rows = json.load(file)
            fields = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
    except (OSError, ValueError):
        return DEFAULT_KEY_FIELD

    if DEFAULT_KEY_FIELD in fields:
        return DEFAULT_KEY_FIELD

    return fields[0] if fields else DEFAULT_KEY_FIELD


def find_data_files(data_path: Path) -> list[Path]:
    if data_path.is_file():
        return [data_path]

    return sorted(
        candidate
        for candidate in data_path.iterdir()
        if candidate.is_file() and candidate.suffix.lower() in DATA_FILE_SUFFIXES
    )


def build_config_from_data(data_path: Path) -> tuple[dict, Path]:
    """Derive a full CRUD config from a data file or a folder of data files.

    Returns the config and the base directory its relative paths resolve against.
    """
    resolved = data_path.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Data path not found: {data_path}")

    base_path = resolved.parent if resolved.is_file() else resolved
    data_files = find_data_files(resolved)

    if not data_files:
        raise ValueError(
            f"No .json or .csv data file found in: {data_path}"
        )

    seen_stems: dict[str, str] = {}
    resources = []

    for data_file in data_files:
        source_type = DATA_FILE_SUFFIXES[data_file.suffix.lower()]

        # users.json and users.csv would both want to be the 'users' resource.
        if data_file.stem in seen_stems:
            raise ValueError(
                f"'{data_file.name}' and '{seen_stems[data_file.stem]}' would both "
                f"become the '{data_file.stem}' resource. Rename one, or write a "
                f"config with 'mkf init --from-data'."
            )

        seen_stems[data_file.stem] = data_file.name

        resources.append(
            {
                "name": data_file.stem,
                "path": f"/{data_file.stem}",
                "source": {"type": source_type, "file": f"./{data_file.name}"},
                "key_field": detect_key_field(data_file, source_type),
            }
        )

    return {"resources": resources}, base_path
