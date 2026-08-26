from pathlib import Path

import typer
import uvicorn

from mockyfast.app import create_app
from mockyfast.config import load_config

app = typer.Typer(help="Serve API mocks from YAML")


@app.callback()
def main() -> None:
    pass


@app.command("init")
def init_command(output: str = "mockyfast.yaml") -> None:
    """
    Create a sample configuration file.
    """
    content = """routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
"""

    path = Path(output)

    if path.exists():
        typer.echo(f"The file '{output}' already exists.")
        raise typer.Exit(code=1)

    path.write_text(content, encoding="utf-8")
    typer.echo(f"Sample file created: {output}")


@app.command("validate")
def validate_command(config: str = typer.Argument(..., help="Path to the YAML file")) -> None:
    """
    Validate the configuration file.
    """
    try:
        load_config(config)
    except Exception as exc:
        typer.echo(f"Invalid configuration: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("Configuration is valid.")


@app.command("serve")
def serve_command(
    config: str = typer.Argument(..., help="Path to the YAML file"),
    host: str = typer.Option("127.0.0.1", help="Host"),
    port: int = typer.Option(8000, help="Port"),
) -> None:
    """
    Start the mock server.
    """
    fastapi_app = create_app(config)
    uvicorn.run(fastapi_app, host=host, port=port)


if __name__ == "__main__":
    app()