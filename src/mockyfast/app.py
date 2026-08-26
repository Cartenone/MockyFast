import asyncio
import html
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from mockyfast.config import load_config_source, load_json_file
from mockyfast.datasources.csv_source import load_csv_rows, query_csv_data
from mockyfast.datasources.json_source import load_json_rows, query_json_data
from mockyfast.state_store import InMemoryResourceStore


@dataclass
class ResponseOutcome:
    """What a matched route decided to answer, before it becomes a response."""

    body: Any
    status_code: int


def render_template(value, path_params: dict):
    if isinstance(value, str):
        try:
            return value.format(**path_params)
        except Exception:
            return value

    if isinstance(value, dict):
        return {key: render_template(val, path_params) for key, val in value.items()}

    if isinstance(value, list):
        return [render_template(item, path_params) for item in value]

    return value


def query_matches(expected_query: dict, actual_query: dict) -> bool:
    for key, expected_value in expected_query.items():
        actual_value = actual_query.get(key)
        if actual_value != str(expected_value):
            return False
    return True


def headers_matches(expected_headers: dict, actual_headers: dict) -> bool:
    normalized_actual_headers = {
        key.lower(): value for key, value in actual_headers.items()
    }

    for key, expected_value in expected_headers.items():
        actual_value = normalized_actual_headers.get(key.lower())
        if actual_value != str(expected_value):
            return False
    return True


def json_matches(expected, actual) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False

        for key, expected_value in expected.items():
            if key not in actual:
                return False
            if not json_matches(expected_value, actual[key]):
                return False

        return True

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False

        if len(expected) != len(actual):
            return False

        for expected_item, actual_item in zip(expected, actual, strict=True):
            if not json_matches(expected_item, actual_item):
                return False

        return True

    return expected == actual


async def route_matches(route: dict, request: Request) -> bool:
    request_config = route.get("request", {})

    expected_query = request_config.get("query")
    if expected_query:
        actual_query = dict(request.query_params)
        if not query_matches(expected_query, actual_query):
            return False

    expected_headers = request_config.get("headers")
    if expected_headers:
        actual_headers = dict(request.headers)
        if not headers_matches(expected_headers, actual_headers):
            return False

    expected_json = request_config.get("json")
    if expected_json is not None:
        try:
            actual_json = await request.json()
        except Exception:
            return False

        if not json_matches(expected_json, actual_json):
            return False

    return True


def get_resource_name(route: dict) -> str:
    response_config = route.get("response", {})
    data_source = response_config["data_source"]

    if "resource_name" in data_source:
        return data_source["resource_name"]

    return route["path"]


def get_response_status_code(route: dict) -> int:
    response_config = route.get("response", {})
    return response_config.get("status_code", 200)


def get_response_delay_ms(route: dict) -> int:
    response_config = route.get("response", {})
    return int(response_config.get("delay_ms", 0))


async def apply_response_delay(route: dict) -> None:
    delay_ms = get_response_delay_ms(route)

    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000)


def seed_mutable_store_for_route(
    route: dict,
    config_path: str,
    store: InMemoryResourceStore,
) -> None:
    response_config = route.get("response", {})
    data_source = response_config.get("data_source")

    if not data_source or not data_source.get("mutable", False):
        return

    resource_name = get_resource_name(route)

    # A resource expands to several routes sharing one store, so without this
    # the same file would be read once per route.
    if store.has(resource_name):
        return

    if data_source["type"] == "csv":
        rows = load_csv_rows(config_path, data_source["file"])
    elif data_source["type"] == "json":
        rows = load_json_rows(config_path, data_source["file"])
    else:
        raise ValueError(f"Unsupported data source type: {data_source['type']}")

    store.seed(resource_name, rows)


def resolve_where_expected_value(
    where: dict[str, Any],
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> Any:
    if "equals_path_param" in where:
        return path_params.get(where["equals_path_param"])

    if "equals_query_param" in where:
        return query_params.get(where["equals_query_param"])

    return None


def get_where_field(where: dict[str, Any]) -> str | None:
    return where.get("column") or where.get("field")


def query_mutable_data_source(
    route: dict,
    store: InMemoryResourceStore,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> Any:
    response_config = route.get("response", {})
    data_source = response_config["data_source"]

    resource_name = get_resource_name(route)
    mode = data_source["mode"]
    where = data_source.get("where")

    rows = store.list(resource_name)

    if where is None:
        filtered_rows = rows
    else:
        compare_key = get_where_field(where)
        expected_value = resolve_where_expected_value(where, path_params, query_params)

        if expected_value is None:
            filtered_rows = []
        else:
            filtered_rows = [
                row for row in rows if str(row.get(compare_key)) == str(expected_value)
            ]

    if mode == "all":
        return filtered_rows

    if mode == "first":
        return filtered_rows[0] if filtered_rows else None

    raise ValueError(f"Unsupported mutable data source mode: {mode}")


def build_not_found_outcome(data_source: dict) -> ResponseOutcome:
    return ResponseOutcome(
        body=data_source.get("not_found_body", {"detail": "Resource not found"}),
        status_code=data_source.get("not_found_status", 404),
    )


def build_data_source_response(
    route: dict,
    config_path: str,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
    store: InMemoryResourceStore,
) -> ResponseOutcome:
    response_config = route.get("response", {})
    data_source = response_config["data_source"]

    if data_source.get("mutable", False):
        result = query_mutable_data_source(
            route=route,
            store=store,
            path_params=path_params,
            query_params=query_params,
        )
    elif data_source["type"] == "csv":
        result = query_csv_data(
            config_path=config_path,
            relative_csv_path=data_source["file"],
            mode=data_source["mode"],
            where=data_source.get("where"),
            path_params=path_params,
            query_params=query_params,
            schema=data_source.get("schema"),
            coerce_types=data_source.get("coerce_types", False),
        )
    elif data_source["type"] == "json":
        result = query_json_data(
            config_path=config_path,
            relative_json_path=data_source["file"],
            mode=data_source["mode"],
            where=data_source.get("where"),
            path_params=path_params,
            query_params=query_params,
        )
    else:
        raise ValueError(f"Unsupported data source type: {data_source['type']}")

    if data_source.get("mode") == "first" and result is None:
        return build_not_found_outcome(data_source)

    wrap = data_source.get("wrap")
    if wrap is not None:
        result = {wrap: result}

    return ResponseOutcome(body=result, status_code=get_response_status_code(route))


def build_response_body(
    route: dict,
    config_path: str,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
    store: InMemoryResourceStore,
) -> ResponseOutcome:
    response_config = route.get("response", {})

    if "data_source" in response_config:
        return build_data_source_response(
            route=route,
            config_path=config_path,
            path_params=path_params,
            query_params=query_params,
            store=store,
        )

    if "body_from" in response_config:
        body = load_json_file(config_path, response_config["body_from"])
    else:
        body = response_config.get("body", {})

    return ResponseOutcome(
        body=render_template(body, path_params),
        status_code=get_response_status_code(route),
    )


async def read_json_object(request: Request) -> tuple[Any, ResponseOutcome | None]:
    """Parse the request body, returning an error outcome instead of raising."""
    try:
        payload = await request.json()
    except Exception:
        return None, ResponseOutcome(
            body={"detail": "Request body must be valid JSON."},
            status_code=400,
        )

    if not isinstance(payload, dict):
        return None, ResponseOutcome(
            body={"detail": "Request body must be a JSON object."},
            status_code=400,
        )

    return payload, None


def resolve_mutable_match(
    data_source: dict,
    request: Request,
) -> tuple[str | None, Any]:
    """Field and value identifying the single resource a write targets."""
    where = data_source.get("where", {})

    match_field = get_where_field(where)
    match_value = resolve_where_expected_value(
        where,
        request.path_params,
        dict(request.query_params),
    )

    return match_field, match_value


async def handle_mutable_create(
    route: dict,
    data_source: dict,
    request: Request,
    store: InMemoryResourceStore,
) -> ResponseOutcome:
    payload, error = await read_json_object(request)
    if error is not None:
        return error

    key_field = data_source["key_field"]

    if key_field not in payload:
        return ResponseOutcome(
            body={"detail": f"Request body must contain the key field '{key_field}'."},
            status_code=400,
        )

    resource_name = get_resource_name(route)
    key_value = payload[key_field]

    if store.get_by_key(resource_name, key_field, key_value) is not None:
        return ResponseOutcome(
            body={
                "detail": f"A resource with {key_field}={key_value} already exists."
            },
            status_code=409,
        )

    created = store.create(resource_name, payload)

    return ResponseOutcome(body=created, status_code=get_response_status_code(route))


async def handle_mutable_update(
    route: dict,
    data_source: dict,
    request: Request,
    store: InMemoryResourceStore,
    *,
    replace: bool,
) -> ResponseOutcome:
    payload, error = await read_json_object(request)
    if error is not None:
        return error

    resource_name = get_resource_name(route)
    key_field = data_source["key_field"]
    match_field, match_value = resolve_mutable_match(data_source, request)

    if match_field is None or match_value is None:
        return build_not_found_outcome(data_source)

    existing = store.get_by_key(resource_name, match_field, match_value)
    if existing is None:
        return build_not_found_outcome(data_source)

    if key_field in payload and str(payload[key_field]) != str(existing.get(key_field)):
        return ResponseOutcome(
            body={"detail": f"The key field '{key_field}' cannot be changed."},
            status_code=400,
        )

    write = store.replace if replace else store.update

    updated = write(
        resource_name=resource_name,
        key_field=match_field,
        key_value=match_value,
        payload=payload,
    )

    if updated is None:
        return build_not_found_outcome(data_source)

    return ResponseOutcome(body=updated, status_code=get_response_status_code(route))


def handle_mutable_delete(
    route: dict,
    data_source: dict,
    request: Request,
    store: InMemoryResourceStore,
) -> ResponseOutcome:
    resource_name = get_resource_name(route)
    match_field, match_value = resolve_mutable_match(data_source, request)

    if match_field is None or match_value is None:
        return build_not_found_outcome(data_source)

    deleted = store.delete(
        resource_name=resource_name,
        key_field=match_field,
        key_value=match_value,
    )

    if not deleted:
        return build_not_found_outcome(data_source)

    return ResponseOutcome(
        body={"deleted": True},
        status_code=get_response_status_code(route),
    )


async def build_route_outcome(
    route: dict,
    config_path: str,
    request: Request,
    store: InMemoryResourceStore,
) -> ResponseOutcome:
    response_config = route.get("response", {})
    data_source = response_config.get("data_source")

    if data_source and data_source.get("mutable", False):
        method = request.method.upper()

        if method == "POST":
            return await handle_mutable_create(route, data_source, request, store)

        # PUT replaces the resource, PATCH merges into it.
        if method in {"PUT", "PATCH"}:
            return await handle_mutable_update(
                route,
                data_source,
                request,
                store,
                replace=method == "PUT",
            )

        if method == "DELETE":
            return handle_mutable_delete(route, data_source, request, store)

        if method != "GET":
            return ResponseOutcome(
                body={
                    "detail": f"Method {method} is not supported on a mutable data source."
                },
                status_code=405,
            )

    return build_response_body(
        route=route,
        config_path=config_path,
        path_params=request.path_params,
        query_params=dict(request.query_params),
        store=store,
    )


def describe_routes(routes: list[dict]) -> list[dict[str, Any]]:
    """A compact, serialisable summary of what the server is serving."""
    described = []

    for route in routes:
        entry: dict[str, Any] = {
            "method": str(route["method"]).upper(),
            "path": route["path"],
        }

        data_source = route.get("response", {}).get("data_source")
        if data_source:
            # Only the file name: the index is reachable over the network and
            # the directory layout is nobody else's business.
            source = data_source.get("file")
            entry["source"] = PurePosixPath(source).name if source else None
            entry["mutable"] = bool(data_source.get("mutable", False))

            resource_name = data_source.get("resource_name")
            if resource_name:
                entry["resource"] = resource_name

        described.append(entry)

    return described


def render_index_html(entries: list[dict[str, Any]]) -> str:
    rows = []

    for entry in entries:
        badge = "mutable" if entry.get("mutable") else ""
        source = entry.get("source") or ""

        rows.append(
            "<tr>"
            f'<td><span class="m m-{html.escape(entry["method"].lower())}">'
            f'{html.escape(entry["method"])}</span></td>'
            f'<td><code>{html.escape(entry["path"])}</code></td>'
            f'<td class="dim">{html.escape(source)}</td>'
            f'<td><span class="tag">{html.escape(badge)}</span></td>'
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MockyFast</title>
<style>
:root {{ color-scheme: light dark; --fg:#111; --dim:#666; --bd:#e3e3e3; --bg:#fff; --tag:#eef; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg:#eee; --dim:#999; --bd:#333; --bg:#151515; --tag:#243; }}
}}
body {{ font:15px/1.5 ui-sans-serif,system-ui,sans-serif; margin:0; padding:2.5rem 1.5rem;
       color:var(--fg); background:var(--bg); }}
main {{ max-width:52rem; margin:0 auto; }}
h1 {{ font-size:1.4rem; margin:0 0 .25rem; }}
p.sub {{ color:var(--dim); margin:0 0 2rem; }}
table {{ border-collapse:collapse; width:100%; }}
td, th {{ text-align:left; padding:.55rem .6rem; border-bottom:1px solid var(--bd); }}
th {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.05em; color:var(--dim); }}
code {{ font:13px ui-monospace,monospace; }}
.dim {{ color:var(--dim); font-size:.85rem; }}
.m {{ font:600 11px ui-monospace,monospace; padding:.15rem .4rem; border-radius:3px;
     border:1px solid var(--bd); }}
.m-get {{ color:#2a7; }} .m-post {{ color:#e83; }} .m-put, .m-patch {{ color:#39c; }}
.m-delete {{ color:#d55; }}
.tag:not(:empty) {{ background:var(--tag); font-size:.7rem; padding:.15rem .4rem;
                   border-radius:3px; }}
</style></head>
<body><main>
<h1>MockyFast</h1>
<p class="sub">{len(entries)} route(s) served. This index is generated because no
route is declared for <code>/</code>.</p>
<table><thead><tr><th>Method</th><th>Path</th><th>Source</th><th></th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
</main></body></html>"""


def add_index_route(app: FastAPI, routes: list[dict]) -> None:
    entries = describe_routes(routes)

    async def index(request: Request):
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(render_index_html(entries))

        return JSONResponse({"routes": entries})

    app.add_api_route("/", index, methods=["GET"], include_in_schema=False)


def create_app(
    config_path: str,
    *,
    with_index: bool = True,
    with_cors: bool = True,
) -> FastAPI:
    config, resolved_config_path = load_config_source(config_path)
    app = FastAPI(title="MockyFast")
    app.state.store = InMemoryResourceStore()

    if with_cors:
        # A mock server exists to be called from a dev server on another port,
        # so a browser would block every request without this.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    routes = config.get("routes") or []
    app.state.routes = routes
    grouped_routes = defaultdict(list)

    for route in routes:
        seed_mutable_store_for_route(route, resolved_config_path, app.state.store)

    for route in routes:
        method = route["method"].upper()
        path = route["path"]
        grouped_routes[(method, path)].append(route)

    for (method, path), route_group in grouped_routes.items():

        async def handler(
            request: Request,
            _route_group=route_group,
            _config_path=resolved_config_path,
        ):
            for route in _route_group:
                if not await route_matches(route, request):
                    continue

                outcome = await build_route_outcome(
                    route=route,
                    config_path=_config_path,
                    request=request,
                    store=request.app.state.store,
                )

                await apply_response_delay(route)

                return JSONResponse(
                    content=outcome.body,
                    status_code=outcome.status_code,
                )

            return JSONResponse(
                content={"detail": "No matching mock route found"},
                status_code=404,
            )

        app.add_api_route(path, handler, methods=[method])

    if with_index and not any(route["path"] == "/" for route in routes):
        add_index_route(app, routes)

    return app


def create_app_from_env() -> FastAPI:
    """Factory used by `mkf serve --reload`, which needs an import string."""
    config_path = os.environ["MOCKYFAST_CONFIG"]
    with_index = os.environ.get("MOCKYFAST_INDEX", "1") != "0"
    with_cors = os.environ.get("MOCKYFAST_CORS", "1") != "0"

    return create_app(config_path, with_index=with_index, with_cors=with_cors)
