"""Loading a configuration, and the checks a schema cannot express.

The shape of a configuration lives in `mockyfast.models`, so `mkf validate` and
the published JSON Schema agree by construction. What is left here is what only
a running program can know: that the file exists, that the files it points at
exist and stay inside its directory, and that no route hides another.
"""

import json
from pathlib import Path

import yaml

from mockyfast.datasources.json_source import load_json_rows
from mockyfast.models import validate_shape
from mockyfast.paths import resolve_data_path
from mockyfast.resources import build_config_from_data, expand_resources

__all__ = [
    "collect_warnings",
    "is_data_path",
    "iter_route_responses",
    "load_config",
    "load_config_source",
    "load_json_file",
    "path_shadows",
    "validate_config",
]

# Suffixes that make `mkf serve <path>` run without a YAML file at all.
DATA_PATH_SUFFIXES = {".json", ".csv"}

GENERATED_CONFIG_NAME = "mockyfast.generated.yaml"


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

    validate_config(data, path)

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
    validate_config(config, generated_path)

    return config, generated_path


def validate_config(config: dict, config_path: str) -> None:
    validate_shape(config)
    check_referenced_files(config, config_path)


def iter_route_responses(route: dict):
    """Every response a route can produce, sequence entries included."""
    if route.get("responses"):
        yield from route["responses"]
        return

    response = route.get("response")

    if response:
        yield response


def check_referenced_files(config: dict, config_path: str) -> None:
    """Open every file the configuration points at.

    A JSON Schema can say that `body_from` is a string; only this can say the
    file is there, parses, and has not escaped the configuration directory.
    """
    for index, route in enumerate(config.get("routes") or [], start=1):
        for response in iter_route_responses(route):
            if "body_from" in response:
                # A whole body may be any JSON value, so only the parse matters.
                load_json_file(config_path, response["body_from"])

            data_source = response.get("data_source")

            if not data_source:
                continue

            if data_source["type"] == "csv":
                load_csv_file_reference(config_path, data_source["file"])
                continue

            try:
                load_json_rows(config_path, data_source["file"])
            except ValueError as exc:
                raise ValueError(
                    f"'response.data_source.file' in route #{index}: {exc}"
                ) from exc


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


def load_json_file(config_path: str, relative_json_path: str):
    json_path = resolve_data_path(config_path, relative_json_path, "JSON")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_csv_file_reference(config_path: str, relative_csv_path: str) -> None:
    resolve_data_path(config_path, relative_csv_path, "CSV")
