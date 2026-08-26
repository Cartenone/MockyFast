import importlib.util
import json
import os
from pathlib import Path

import typer
import uvicorn
import yaml

from mockyfast.app import create_app, describe_routes
from mockyfast.config import collect_warnings, load_config_source
from mockyfast.explain import describe_response, explain_request
from mockyfast.models import config_json_schema, validate_shape
from mockyfast.openapi import build_openapi
from mockyfast.openapi_import import (
    build_config_from_openapi,
    load_openapi_document,
)
from mockyfast.resources import build_config_from_data

app = typer.Typer(help="Serve API mocks from YAML")

# File patterns `--reload` watches: the config itself plus the data it serves.
RELOAD_PATTERNS = ["*.yaml", "*.yml", "*.json", "*.csv"]

YAML_SUFFIXES = {".yaml", ".yml"}

SAMPLE_CONFIG = """routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
"""


@app.callback()
def main() -> None:
    pass


def load_or_exit(config: str) -> tuple[dict, str]:
    try:
        return load_config_source(config)
    except Exception as exc:
        typer.echo(f"Invalid configuration: {exc}")
        raise typer.Exit(code=1) from exc


def echo_warnings(config: dict) -> None:
    for warning in collect_warnings(config):
        typer.echo(f"Warning: {warning}")


def echo_route_table(config: dict) -> None:
    entries = describe_routes(config.get("routes") or [])

    if not entries:
        return

    width = max(len(entry["method"]) for entry in entries)

    typer.echo(f"Serving {len(entries)} route(s):")
    for entry in entries:
        tag = "  [mutable]" if entry.get("mutable") else ""
        typer.echo(f"  {entry['method']:<{width}}  {entry['path']}{tag}")


def rebase_source_files(config: dict, base_path: Path, output_dir: Path) -> None:
    """Rewrite generated file references so they resolve from the written config.

    build_config_from_data names files relative to the data folder; once the
    config is written somewhere else, those paths have to point back at it.
    """
    for resource in config.get("resources") or []:
        source = resource["source"]
        data_file = (base_path / source["file"]).resolve()
        relative = os.path.relpath(data_file, output_dir).replace(os.sep, "/")

        source["file"] = relative if relative.startswith(".") else f"./{relative}"


def watch_directory(config: str) -> str:
    path = Path(config).resolve()

    return str(path if path.is_dir() else path.parent)


def config_from_data(from_data: str, output_dir: Path) -> str:
    try:
        config, base_path = build_config_from_data(Path(from_data))
    except Exception as exc:
        typer.echo(f"Cannot read data path: {exc}")
        raise typer.Exit(code=1) from exc

    rebase_source_files(config, base_path, output_dir)

    return as_yaml(config)


def config_from_openapi(from_openapi: str) -> str:
    try:
        config = build_config_from_openapi(load_openapi_document(Path(from_openapi)))
        # A generated config that does not load would be worse than none.
        validate_shape(config)
    except Exception as exc:
        typer.echo(f"Cannot read the OpenAPI document: {exc}")
        raise typer.Exit(code=1) from exc

    return as_yaml(config)


def as_yaml(config: dict) -> str:
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True)


@app.command("init")
def init_command(
    output: str = "mockyfast.yaml",
    from_data: str = typer.Option(
        None,
        "--from-data",
        help="Generate the config from a data file or folder instead of a sample",
    ),
    from_openapi: str = typer.Option(
        None,
        "--from-openapi",
        help="Generate the config from an OpenAPI 3 document instead of a sample",
    ),
) -> None:
    """
    Create a configuration file, from a sample or from what you already have.
    """
    if from_data and from_openapi:
        typer.echo("Use one of --from-data and --from-openapi, not both.")
        raise typer.Exit(code=1)

    path = Path(output)

    if path.exists():
        typer.echo(f"The file '{output}' already exists.")
        raise typer.Exit(code=1)

    if from_data:
        content = config_from_data(from_data, path.resolve().parent)
    elif from_openapi:
        content = config_from_openapi(from_openapi)
    else:
        content = SAMPLE_CONFIG

    path.write_text(content, encoding="utf-8")

    if from_data or from_openapi:
        typer.echo(f"Configuration written to: {output}")
        return

    typer.echo(f"Sample file created: {output}")


@app.command("schema")
def schema_command(
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the schema to this file instead of standard output",
    ),
) -> None:
    """
    Print the JSON Schema of the configuration format.
    """
    content = json.dumps(config_json_schema(), indent=2)

    if output is None:
        typer.echo(content)
        return

    Path(output).write_text(content + "\n", encoding="utf-8")
    typer.echo(f"Schema written to: {output}")


@app.command("openapi")
def openapi_command(
    config: str = typer.Argument(..., help="Path to the YAML file, or a data file/folder"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the document to this file instead of standard output",
    ),
) -> None:
    """
    Print the OpenAPI document describing what the mock answers.
    """
    loaded, resolved_path = load_or_exit(config)

    document = build_openapi(loaded, resolved_path)

    if output is None:
        typer.echo(json.dumps(document, indent=2))
        return

    path = Path(output)

    if path.suffix.lower() in YAML_SUFFIXES:
        content = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    else:
        content = json.dumps(document, indent=2) + "\n"

    path.write_text(content, encoding="utf-8")
    typer.echo(f"OpenAPI document written to: {output}")


@app.command("validate")
def validate_command(
    config: str = typer.Argument(..., help="Path to the YAML file, or a data file/folder"),
) -> None:
    """
    Validate the configuration file.
    """
    loaded, _ = load_or_exit(config)

    echo_warnings(loaded)
    typer.echo("Configuration is valid.")


def parse_header_options(values: list[str] | None) -> dict[str, str]:
    headers = {}

    for value in values or []:
        name, separator, content = value.partition(":")
        if not separator:
            raise typer.BadParameter(f"Header must look like 'Name: value': {value!r}")
        headers[name.strip()] = content.strip()

    return headers


@app.command("explain")
def explain_command(
    config: str = typer.Argument(..., help="Path to the YAML file, or a data file/folder"),
    method: str = typer.Argument(..., help="HTTP method, e.g. GET"),
    target: str = typer.Argument(..., help="Path to test, query string included"),
    header: list[str] = typer.Option(
        None,
        "--header",
        "-H",
        help="Request header as 'Name: value'; repeatable",
    ),
    body: str = typer.Option(None, "--body", help="JSON request body"),
) -> None:
    """
    Show which route answers a request, and why the others do not.
    """
    loaded, _ = load_or_exit(config)

    parsed_body = None
    if body is not None:
        try:
            parsed_body = json.loads(body)
        except ValueError as exc:
            typer.echo(f"--body must be valid JSON: {exc}")
            raise typer.Exit(code=1) from exc

    verdicts = explain_request(
        loaded,
        method=method,
        target=target,
        headers=parse_header_options(header),
        body=parsed_body,
    )

    typer.echo(f"{method.upper()} {target}")
    typer.echo("")

    routes = loaded.get("routes") or []
    winner = None

    for verdict in verdicts:
        if verdict.matched and not verdict.shadowed:
            mark, winner = "->", verdict
        elif verdict.shadowed:
            mark = " ~"
        else:
            mark = "  "

        typer.echo(
            f"{mark} route #{verdict.index}  {verdict.method} {verdict.path}"
            f"  -  {verdict.reason}"
        )

    typer.echo("")

    if winner is None:
        typer.echo("No route answers this request: the server would return 404.")
        raise typer.Exit(code=1)

    route = routes[winner.index - 1]
    typer.echo(f"Answered by route #{winner.index}: {describe_response(route)}")

    if winner.path_params:
        rendered = ", ".join(f"{k}={v}" for k, v in winner.path_params.items())
        typer.echo(f"Path parameters: {rendered}")


@app.command("serve")
def serve_command(
    config: str = typer.Argument(..., help="Path to the YAML file, or a data file/folder"),
    host: str = typer.Option("127.0.0.1", help="Host"),
    port: int = typer.Option(8000, help="Port"),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Restart the server when the configuration changes",
    ),
    index: bool = typer.Option(
        True,
        "--index/--no-index",
        help="Serve a generated route index at /",
    ),
    cors: bool = typer.Option(
        True,
        "--cors/--no-cors",
        help="Allow requests from any origin, so a browser app can call the mock",
    ),
) -> None:
    """
    Start the mock server.
    """
    loaded, _ = load_or_exit(config)

    echo_warnings(loaded)
    echo_route_table(loaded)

    if reload:
        if importlib.util.find_spec("watchfiles") is None:
            # Without watchfiles uvicorn falls back to a reloader that only
            # watches *.py, so it would run but never notice a config change.
            typer.echo(
                "Reload needs the 'watchfiles' package: pip install watchfiles"
            )
            raise typer.Exit(code=1)

        os.environ["MOCKYFAST_CONFIG"] = str(Path(config).resolve())
        os.environ["MOCKYFAST_INDEX"] = "1" if index else "0"
        os.environ["MOCKYFAST_CORS"] = "1" if cors else "0"

        uvicorn.run(
            "mockyfast.app:create_app_from_env",
            factory=True,
            reload=True,
            reload_dirs=[watch_directory(config)],
            # uvicorn only watches *.py by default, which is never what changes here.
            reload_includes=RELOAD_PATTERNS,
            host=host,
            port=port,
        )
        return

    fastapi_app = create_app(config, with_index=index, with_cors=cors)
    uvicorn.run(fastapi_app, host=host, port=port)


if __name__ == "__main__":
    app()
