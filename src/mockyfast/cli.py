import importlib.util
import os
from pathlib import Path

import typer
import uvicorn
import yaml

from mockyfast.app import create_app, describe_routes
from mockyfast.config import collect_warnings, load_config_source
from mockyfast.resources import build_config_from_data

app = typer.Typer(help="Serve API mocks from YAML")

# File patterns `--reload` watches: the config itself plus the data it serves.
RELOAD_PATTERNS = ["*.yaml", "*.yml", "*.json", "*.csv"]

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


@app.command("init")
def init_command(
    output: str = "mockyfast.yaml",
    from_data: str = typer.Option(
        None,
        "--from-data",
        help="Generate the config from a data file or folder instead of a sample",
    ),
) -> None:
    """
    Create a sample configuration file.
    """
    path = Path(output)

    if path.exists():
        typer.echo(f"The file '{output}' already exists.")
        raise typer.Exit(code=1)

    if from_data:
        try:
            config, base_path = build_config_from_data(Path(from_data))
        except Exception as exc:
            typer.echo(f"Cannot read data path: {exc}")
            raise typer.Exit(code=1) from exc

        rebase_source_files(config, base_path, path.resolve().parent)
        content = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    else:
        content = SAMPLE_CONFIG

    path.write_text(content, encoding="utf-8")
    typer.echo(f"Sample file created: {output}")


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
