import csv
from typing import Any

from mockyfast.paths import resolve_data_path

SUPPORTED_SCHEMA_TYPES = {"str", "int", "float", "bool"}


def load_csv_rows(config_path: str, relative_csv_path: str) -> list[dict[str, Any]]:
    csv_path = resolve_data_path(config_path, relative_csv_path, "CSV")

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def coerce_scalar(value: str) -> Any:
    normalized = value.strip()

    if normalized == "":
        return ""

    lowered = normalized.lower()

    if lowered == "true":
        return True

    if lowered == "false":
        return False

    try:
        if "." in normalized:
            return float(normalized)
        return int(normalized)
    except ValueError:
        return value


def cast_with_schema(value: Any, schema_type: str) -> Any:
    if schema_type == "str":
        return str(value)

    if schema_type == "int":
        return int(value)

    if schema_type == "float":
        return float(value)

    if schema_type == "bool":
        if isinstance(value, bool):
            return value

        lowered = str(value).strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

        raise ValueError(f"Cannot cast value '{value}' to bool.")

    raise ValueError(f"Unsupported schema type: {schema_type}")


def apply_schema_to_row(row: dict[str, Any], schema: dict[str, str]) -> dict[str, Any]:
    mapped_row = dict(row)

    for field_name, schema_type in schema.items():
        if field_name not in mapped_row:
            continue
        mapped_row[field_name] = cast_with_schema(mapped_row[field_name], schema_type)

    return mapped_row


def apply_coerce_types_to_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: coerce_scalar(value) for key, value in row.items()}


def normalize_rows(
    rows: list[dict[str, Any]],
    schema: dict[str, str] | None,
    coerce_types: bool,
) -> list[dict[str, Any]]:
    normalized_rows = rows

    if schema is not None:
        normalized_rows = [apply_schema_to_row(row, schema) for row in normalized_rows]
    elif coerce_types:
        normalized_rows = [apply_coerce_types_to_row(row) for row in normalized_rows]

    return normalized_rows


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


def filter_csv_rows(
    rows: list[dict[str, Any]],
    where: dict[str, Any] | None,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> list[dict[str, Any]]:
    if where is None:
        return rows

    column = where["column"]
    expected_value = resolve_expected_value(where, path_params, query_params)

    if expected_value is None:
        return []

    return [row for row in rows if str(row.get(column)) == expected_value]


def query_csv_data(
    config_path: str,
    relative_csv_path: str,
    mode: str,
    where: dict[str, Any] | None,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
    schema: dict[str, str] | None = None,
    coerce_types: bool = False,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    rows = load_csv_rows(config_path, relative_csv_path)
    rows = normalize_rows(rows, schema=schema, coerce_types=coerce_types)

    filtered_rows = filter_csv_rows(rows, where, path_params, query_params)

    if mode == "all":
        return filtered_rows

    if mode == "first":
        return filtered_rows[0] if filtered_rows else None

    raise ValueError(f"Unsupported CSV query mode: {mode}")