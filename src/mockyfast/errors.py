"""Turning a Pydantic failure into the message `mkf validate` prints.

Pydantic reports where an error happened as a tuple of keys and indexes, and
describes the value in its own words. Both need translating: the location has
parts in it that are not keys of the file, and the wording has to stay the one
this CLI has always used.
"""

from typing import Any

from pydantic import ValidationError


class ConfigError(ValueError):
    """A validation failure that carries the key it belongs to.

    Pydantic reports the location of the model that raised an error, not the
    field inside it, so a check spanning several fields has to name its own key.
    """

    def __init__(self, field: str | None, message: str) -> None:
        self.field = field
        self.message = message

        super().__init__(message if field is None else f"'{field}' {message}")


# What a Pydantic error type means in the wording this CLI has always used.
ERROR_PHRASES = {
    "string_type": "must be a string",
    "bool_type": "must be a boolean",
    "int_type": "must be an integer",
    "float_type": "must be a number",
    "dict_type": "must be an object",
    "model_type": "must be an object",
    "model_attributes_type": "must be an object",
    "list_type": "must be a list",
    "too_short": "must be a non-empty list",
    "extra_forbidden": "is not a known configuration key",
}

# The top-level keys whose entries are numbered in an error message.
NUMBERED_KEYS = {"routes": "route", "resources": "resource"}


def resolve_error_location(data: Any, error: dict) -> tuple:
    """Keep only the parts of a Pydantic location that are keys in the file.

    A union member contributes its own tag to the location, so `delay_ms: -1`
    reports `('delay_ms', 'int')`, and a bad mapping key adds `'[key]'`. Neither
    appears in the YAML, so the location is walked against the parsed document
    and anything that does not resolve is dropped.
    """
    location = tuple(error["loc"])
    missing = ()

    if error["type"] == "missing" and location:
        # A key that is absent will never resolve, and is exactly the key the
        # message has to name.
        location, missing = location[:-1], location[-1:]

    resolved = []
    node = data

    for part in location:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and isinstance(part, int) and part < len(node):
            node = node[part]
        else:
            continue

        resolved.append(part)

    return tuple(resolved) + missing


def select_error(errors: list[dict], data: Any) -> tuple[tuple, dict]:
    """The one error worth showing, out of everything Pydantic collected.

    A union reports each member's shallow failure next to the deep one that
    actually describes the value, so an error whose location is a prefix of
    another's is the less useful of the two.
    """
    resolved = [(resolve_error_location(data, error), error) for error in errors]

    specific = [
        (location, error)
        for location, error in resolved
        if not any(
            other != location and other[: len(location)] == location
            for other, _ in resolved
        )
    ]

    return (specific or resolved)[0]


def join_path(*parts: str | None) -> str:
    return ".".join(part for part in parts if part)


def describe_validation_error(exc: ValidationError, data: Any) -> str:
    """Render a Pydantic failure as the message `mkf validate` prints."""
    location, error = select_error(exc.errors(), data)

    kind = number = None
    if len(location) >= 2 and location[0] in NUMBERED_KEYS:
        kind = NUMBERED_KEYS[location[0]]
        number = location[1] + 1
        location = location[2:]

    subject = f"{kind} #{number}" if kind else None
    path = join_path(*(str(part) for part in location))
    cause = (error.get("ctx") or {}).get("error")

    if isinstance(cause, ConfigError):
        return render_message(subject, join_path(path, cause.field), cause.message)

    if error["type"] == "value_error":
        return render_message(subject, path, str(cause) if cause else error["msg"])

    if error["type"] == "missing":
        # A route's own keys have always been reported this way, and reading
        # "Route #1 is missing 'method'" beats naming a key that is not there.
        if kind == "route" and "." not in path:
            return f"Route #{number} is missing '{path}'."

        return render_message(subject, path, "is required")

    phrase = ERROR_PHRASES.get(error["type"], f"is invalid: {error['msg']}")

    return render_message(subject, path, phrase)


def render_message(subject: str | None, path: str, phrase: str) -> str:
    if not path:
        return f"{subject[0].upper()}{subject[1:]} {phrase}." if subject else f"{phrase}."

    return f"'{path}'{f' in {subject}' if subject else ''} {phrase}."
