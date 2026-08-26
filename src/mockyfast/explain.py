"""Answering "why does this request not hit the route I expected?".

Route resolution mixes path templates, declaration order and request matchers,
so a 404 on its own says very little. This walks the same decisions the server
makes and reports a verdict per route.
"""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from mockyfast.matchers import value_matches


@dataclass
class RouteVerdict:
    index: int
    method: str
    path: str
    matched: bool = False
    reason: str = ""
    path_params: dict[str, str] = field(default_factory=dict)
    shadowed: bool = False


def split_target(target: str) -> tuple[str, dict[str, str]]:
    """Split '/users?role=admin' into its path and query parameters."""
    parts = urlsplit(target)

    return parts.path or "/", dict(parse_qsl(parts.query))


def match_path(template: str, actual: str) -> tuple[bool, dict[str, str]]:
    template_parts = template.strip("/").split("/")
    actual_parts = actual.strip("/").split("/")

    if len(template_parts) != len(actual_parts):
        return False, {}

    params: dict[str, str] = {}

    for template_part, actual_part in zip(template_parts, actual_parts, strict=True):
        if template_part.startswith("{") and template_part.endswith("}"):
            params[template_part[1:-1]] = actual_part
            continue

        if template_part != actual_part:
            return False, {}

    return True, params


def first_scalar_mismatch(expected: dict, actual: dict, lower: bool) -> str | None:
    normalized = (
        {key.lower(): item for key, item in actual.items()} if lower else actual
    )

    for key, expected_value in expected.items():
        lookup = key.lower() if lower else key

        if not value_matches(
            expected_value,
            normalized.get(lookup),
            present=lookup in normalized,
            stringify=True,
        ):
            return key

    return None


def first_json_mismatch(expected: Any, actual: Any) -> str | None:
    from mockyfast.app import json_matches

    if not isinstance(expected, dict):
        return None if json_matches(expected, actual) else "body"

    for key, expected_value in expected.items():
        if not json_matches({key: expected_value}, actual):
            return key

    return None


def explain_route(
    route: dict,
    index: int,
    method: str,
    path: str,
    query: dict[str, str],
    headers: dict[str, str],
    body: Any,
) -> RouteVerdict:
    route_method = str(route["method"]).upper()
    route_path = route["path"]

    verdict = RouteVerdict(index=index, method=route_method, path=route_path)

    if route_method != method:
        verdict.reason = f"method is {route_method}"
        return verdict

    path_matched, params = match_path(route_path, path)
    if not path_matched:
        verdict.reason = "path does not match"
        return verdict

    verdict.path_params = params

    request_config = route.get("request") or {}

    expected_query = request_config.get("query")
    if expected_query:
        mismatch = first_scalar_mismatch(expected_query, query, lower=False)
        if mismatch is not None:
            verdict.reason = f"query param {mismatch!r} does not match"
            return verdict

    expected_headers = request_config.get("headers")
    if expected_headers:
        mismatch = first_scalar_mismatch(expected_headers, headers, lower=True)
        if mismatch is not None:
            verdict.reason = f"header {mismatch!r} does not match"
            return verdict

    expected_json = request_config.get("json")
    if expected_json is not None:
        if body is None:
            verdict.reason = "route matches on a JSON body, none was given"
            return verdict

        mismatch = first_json_mismatch(expected_json, body)
        if mismatch is not None:
            verdict.reason = f"body field {mismatch!r} does not match"
            return verdict

    verdict.matched = True
    verdict.reason = "matches"

    return verdict


def describe_response(route: dict) -> str:
    if "responses" in route:
        return f"sequence of {len(route['responses'])} responses"

    response = route.get("response") or {}

    if "data_source" in response:
        data_source = response["data_source"]
        kind = "mutable " if data_source.get("mutable") else ""
        return f"{kind}{data_source.get('type')} data source"

    if "body_from" in response:
        return f"body from {response['body_from']}"

    return "inline body"


def explain_request(
    config: dict,
    method: str,
    target: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
) -> list[RouteVerdict]:
    path, query = split_target(target)
    method = method.upper()

    verdicts = []
    already_matched = False

    for index, route in enumerate(config.get("routes") or [], start=1):
        verdict = explain_route(
            route=route,
            index=index,
            method=method,
            path=path,
            query=query,
            headers=headers or {},
            body=body,
        )

        # Starlette answers with the first registered route, so a later match
        # is reachable in theory and dead in practice.
        if verdict.matched and already_matched:
            verdict.shadowed = True
            verdict.reason = "would match, but an earlier route answers first"

        if verdict.matched and not already_matched:
            already_matched = True

        verdicts.append(verdict)

    return verdicts
