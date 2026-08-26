"""Query parameters that shape a `mode: all` response.

Enabled per data source with `list_query: true`, which the `resources:`
shorthand turns on for the list route. Reserved names start with an underscore
so they cannot collide with a field of the data.
"""

from typing import Any

from mockyfast.matchers import as_number

RESERVED_QUERY_PARAMS = {"_limit", "_offset", "_page", "_sort", "_order"}


def sort_key(value: Any) -> tuple[int, float, str]:
    """Order numbers before text, so a mixed column still sorts predictably."""
    number = as_number(value)

    if number is not None:
        return (0, number, "")

    return (1, 0.0, "" if value is None else str(value))


def apply_field_filters(
    rows: list[dict[str, Any]],
    query_params: dict[str, Any],
    consumed: set[str],
) -> list[dict[str, Any]]:
    filtered = rows

    for key, value in query_params.items():
        if key in RESERVED_QUERY_PARAMS or key in consumed:
            continue

        filtered = [row for row in filtered if str(row.get(key)) == str(value)]

    return filtered


def apply_sorting(
    rows: list[dict[str, Any]],
    query_params: dict[str, Any],
) -> list[dict[str, Any]]:
    requested = query_params.get("_sort")

    if not requested:
        return rows

    fields = [field.strip() for field in str(requested).split(",") if field.strip()]

    if not fields:
        return rows

    descending = str(query_params.get("_order", "asc")).lower() == "desc"

    return sorted(
        rows,
        key=lambda row: [sort_key(row.get(field)) for field in fields],
        reverse=descending,
    )


def parse_count(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed >= 0 else None


def apply_pagination(
    rows: list[dict[str, Any]],
    query_params: dict[str, Any],
) -> list[dict[str, Any]]:
    limit = parse_count(query_params.get("_limit"))
    page = parse_count(query_params.get("_page"))
    offset = parse_count(query_params.get("_offset")) or 0

    # _page is 1-based and only means something together with _limit.
    if page is not None and page >= 1 and limit is not None:
        offset = (page - 1) * limit

    if limit is None:
        return rows[offset:] if offset else rows

    return rows[offset : offset + limit]


def apply_list_query(
    rows: list[dict[str, Any]],
    query_params: dict[str, Any],
    consumed: set[str],
) -> tuple[list[dict[str, Any]], int]:
    """Filter, sort and paginate. Returns the page and the pre-page total."""
    filtered = apply_field_filters(rows, query_params, consumed)
    ordered = apply_sorting(filtered, query_params)

    return apply_pagination(ordered, query_params), len(ordered)
