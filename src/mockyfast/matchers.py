"""Operators for `request:` matching.

A matcher value is either a plain scalar, meaning exact equality, or an object
made only of operator keys:

    Authorization: { matches: "^Bearer .+" }
    page:          { one_of: ["1", "2"] }
    age:           { gte: 18 }
    trace_id:      { absent: true }

Restricting matchers to objects whose keys are *all* operators keeps a nested
body object like `{"user": {"name": "x"}}` a structural comparison.
"""

import re
from typing import Any

COMPARISON_KEYS = {"gt", "gte", "lt", "lte"}

MATCHER_KEYS = {
    "equals",
    "matches",
    "contains",
    "one_of",
    "present",
    "absent",
} | COMPARISON_KEYS


def is_matcher(expected: Any) -> bool:
    return (
        isinstance(expected, dict)
        and len(expected) > 0
        and all(key in MATCHER_KEYS for key in expected)
    )


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def equals_matches(expected: Any, actual: Any, stringify: bool) -> bool:
    if stringify:
        return str(actual) == str(expected)

    return actual == expected


def contains_matches(expected: Any, actual: Any) -> bool:
    if isinstance(actual, str):
        return str(expected) in actual

    if isinstance(actual, (list, tuple, dict)):
        return expected in actual

    return str(expected) in str(actual)


def one_of_matches(options: Any, actual: Any, stringify: bool) -> bool:
    if not isinstance(options, (list, tuple)):
        return False

    if stringify:
        return str(actual) in [str(option) for option in options]

    return actual in options


def comparison_matches(operator: str, expected: Any, actual: Any) -> bool:
    left = as_number(actual)
    right = as_number(expected)

    if left is None or right is None:
        return False

    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right

    return left <= right


def apply_matcher(
    matcher: dict,
    actual: Any,
    *,
    present: bool,
    stringify: bool,
) -> bool:
    if "absent" in matcher:
        if bool(matcher["absent"]) is present:
            return False
        if bool(matcher["absent"]):
            return True

    if "present" in matcher:
        if bool(matcher["present"]) is not present:
            return False
        if not bool(matcher["present"]):
            return True

    # Every remaining operator needs a value to look at.
    if not present:
        return False

    if "equals" in matcher and not equals_matches(
        matcher["equals"], actual, stringify
    ):
        return False

    if "matches" in matcher:
        try:
            if re.search(str(matcher["matches"]), str(actual)) is None:
                return False
        except re.error:
            return False

    if "contains" in matcher and not contains_matches(matcher["contains"], actual):
        return False

    if "one_of" in matcher and not one_of_matches(
        matcher["one_of"], actual, stringify
    ):
        return False

    for operator in COMPARISON_KEYS:
        if operator in matcher and not comparison_matches(
            operator, matcher[operator], actual
        ):
            return False

    return True


def value_matches(
    expected: Any,
    actual: Any,
    *,
    present: bool,
    stringify: bool,
) -> bool:
    if is_matcher(expected):
        return apply_matcher(expected, actual, present=present, stringify=stringify)

    if not present:
        return False

    return equals_matches(expected, actual, stringify)


def iter_matchers(node: Any):
    """Yield every matcher object inside a `request:` matching tree."""
    if is_matcher(node):
        yield node
        return

    if isinstance(node, dict):
        for item in node.values():
            yield from iter_matchers(item)
    elif isinstance(node, list):
        for item in node:
            yield from iter_matchers(item)
