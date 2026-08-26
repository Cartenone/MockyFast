import json
from typing import Any

from mockyfast.paths import resolve_data_path


def load_json_rows(config_path: str, relative_json_path: str) -> list[dict[str, Any]]:
    json_path = resolve_data_path(config_path, relative_json_path, "JSON")

    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("JSON data source must contain a root list.")

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"JSON data source item #{index} must be an object.")

    return data


def resolve_expected_value(
    where: dict[str, Any],
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> str | None:
    if "equals_path_param" in where:
        param_name = where["equals_path_param"]
        value = path_params.get(param_name)
        return None if value is None else str(value)

    if "equals_query_param" in where:
        param_name = where["equals_query_param"]
        value = query_params.get(param_name)
        return None if value is None else str(value)

    return None


def filter_json_rows(
    rows: list[dict[str, Any]],
    where: dict[str, Any] | None,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> list[dict[str, Any]]:
    if where is None:
        return rows

    field = where["field"]
    expected_value = resolve_expected_value(where, path_params, query_params)

    if expected_value is None:
        return []

    return [row for row in rows if str(row.get(field)) == expected_value]


def query_json_data(
    config_path: str,
    relative_json_path: str,
    mode: str,
    where: dict[str, Any] | None,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> dict[str, Any] | list[dict[str, Any]] | None:
    rows = load_json_rows(config_path, relative_json_path)
    filtered_rows = filter_json_rows(rows, where, path_params, query_params)

    if mode == "all":
        return filtered_rows

    if mode == "first":
        return filtered_rows[0] if filtered_rows else None

    raise ValueError(f"Unsupported JSON query mode: {mode}")