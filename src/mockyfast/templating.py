"""Placeholder substitution for response bodies.

Two syntaxes share one pass:

    {user_id}          the original path-parameter form
    {{query.page}}     scoped lookups and generators

A string made of exactly one token becomes that token's native value, so
``"{{randint:1:5}}"`` yields the number ``3`` rather than the string ``"3"``.
Unknown tokens are left untouched: a mock config is more useful when a typo
shows up in the response than when it raises.
"""

import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

TOKEN_PATTERN = re.compile(r"\{\{\s*(.*?)\s*\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")

SCOPES = {"path", "query", "header", "body"}


@dataclass
class TemplateContext:
    """Everything a placeholder is allowed to read from the request."""

    path_params: dict[str, Any] = field(default_factory=dict)
    query_params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None


def parse_numbers(argument: str, count: int) -> list[str] | None:
    parts = [part.strip() for part in argument.split(":") if part.strip() != ""]

    return parts if len(parts) == count else None


def resolve_generator(name: str, argument: str) -> tuple[bool, Any]:
    if name == "uuid":
        return True, str(uuid.uuid4())

    if name == "now":
        moment = datetime.now(timezone.utc)
        return True, moment.strftime(argument) if argument else moment.isoformat()

    if name == "timestamp":
        return True, int(datetime.now(timezone.utc).timestamp())

    if name == "randint":
        bounds = parse_numbers(argument, 2)
        if bounds is None:
            return False, None
        try:
            return True, random.randint(int(bounds[0]), int(bounds[1]))
        except ValueError:
            return False, None

    if name == "randfloat":
        bounds = parse_numbers(argument, 2)
        if bounds is None:
            return False, None
        try:
            low, high = float(bounds[0]), float(bounds[1])
        except ValueError:
            return False, None
        return True, round(random.uniform(low, high), 2)

    if name == "choice":
        options = [option for option in argument.split("|") if option != ""]
        return (True, random.choice(options)) if options else (False, None)

    return False, None


def walk_path(data: Any, dotted_path: str) -> tuple[bool, Any]:
    current = data

    for step in dotted_path.split("."):
        if isinstance(current, dict) and step in current:
            current = current[step]
            continue

        if isinstance(current, list) and step.isdigit():
            index = int(step)
            if index < len(current):
                current = current[index]
                continue

        return False, None

    return True, current


def resolve_lookup(scope: str, lookup: str, context: TemplateContext) -> tuple[bool, Any]:
    if scope == "path":
        return lookup in context.path_params, context.path_params.get(lookup)

    if scope == "query":
        return lookup in context.query_params, context.query_params.get(lookup)

    if scope == "header":
        headers = {key.lower(): value for key, value in context.headers.items()}
        key = lookup.lower()
        return key in headers, headers.get(key)

    if scope == "body":
        return walk_path(context.body, lookup)

    return False, None


def resolve_token(expression: str, context: TemplateContext) -> tuple[bool, Any]:
    scope, dot, lookup = expression.partition(".")
    if dot and scope.strip() in SCOPES:
        return resolve_lookup(scope.strip(), lookup, context)

    name, _, argument = expression.partition(":")

    return resolve_generator(name.strip(), argument)


def resolve_match(match: re.Match, context: TemplateContext) -> tuple[bool, Any]:
    expression = match.group(1)

    if expression is not None:
        return resolve_token(expression, context)

    name = match.group(2)

    return name in context.path_params, context.path_params.get(name)


def render_string(value: str, context: TemplateContext) -> Any:
    matches = list(TOKEN_PATTERN.finditer(value))

    if not matches:
        return value

    # One token and nothing else: hand back the real type, not its text.
    if len(matches) == 1 and matches[0].group(0) == value:
        resolved, resolved_value = resolve_match(matches[0], context)
        return resolved_value if resolved else value

    def replace(match: re.Match) -> str:
        resolved, resolved_value = resolve_match(match, context)

        return str(resolved_value) if resolved else match.group(0)

    return TOKEN_PATTERN.sub(replace, value)


def render_key(key: Any, context: TemplateContext) -> Any:
    if not isinstance(key, str):
        return key

    rendered = render_string(key, context)

    return rendered if isinstance(rendered, str) else str(rendered)


def render_template(value: Any, context: TemplateContext) -> Any:
    if isinstance(value, str):
        return render_string(value, context)

    if isinstance(value, dict):
        return {
            render_key(key, context): render_template(item, context)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [render_template(item, context) for item in value]

    return value
