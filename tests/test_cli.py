from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mockyfast.app import create_app_from_env
from mockyfast.cli import app, echo_route_table, watch_directory

runner = CliRunner()


def test_init_creates_config_file():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "Sample file created" in result.stdout
        assert Path("mockyfast.yaml").exists()


def test_init_fails_if_file_already_exists():
    with runner.isolated_filesystem():
        Path("mockyfast.yaml").write_text("already exists", encoding="utf-8")

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 1
        assert "already exists" in result.stdout


def test_validate_succeeds_for_valid_config():
    with runner.isolated_filesystem():
        Path("mockyfast.yaml").write_text(
            """routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["validate", "mockyfast.yaml"])

        assert result.exit_code == 0
        assert "Configuration is valid." in result.stdout


def test_validate_fails_for_invalid_config():
    with runner.isolated_filesystem():
        Path("invalid.yaml").write_text(
            """name: example
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["validate", "invalid.yaml"])

        assert result.exit_code == 1
        assert "Invalid configuration" in result.stdout

def test_init_from_data_generates_a_resource_config():
    with runner.isolated_filesystem():
        data_dir = Path("data")
        data_dir.mkdir()
        (data_dir / "users.json").write_text('[{"id": 1}]', encoding="utf-8")

        result = runner.invoke(app, ["init", "--from-data", "./data"])

        assert result.exit_code == 0

        generated = Path("mockyfast.yaml").read_text(encoding="utf-8")
        assert "resources:" in generated
        assert "name: users" in generated

        # Paths must resolve from where the config was written, not from the
        # data folder it was derived from.
        assert "./data/users.json" in generated

        follow_up = runner.invoke(app, ["validate", "mockyfast.yaml"])
        assert follow_up.exit_code == 0


def test_init_from_a_missing_data_path_fails():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init", "--from-data", "./nope"])

        assert result.exit_code == 1
        assert "Cannot read data path" in result.stdout
        assert not Path("mockyfast.yaml").exists()


def test_validate_accepts_a_data_folder_without_any_yaml():
    with runner.isolated_filesystem():
        data_dir = Path("data")
        data_dir.mkdir()
        (data_dir / "users.json").write_text('[{"id": 1}]', encoding="utf-8")

        result = runner.invoke(app, ["validate", "./data"])

        assert result.exit_code == 0
        assert "Configuration is valid." in result.stdout


def test_validate_reports_shadowed_routes_as_warnings():
    with runner.isolated_filesystem():
        Path("mockyfast.yaml").write_text(
            """routes:
  - method: GET
    path: /users/{user_id}
    response:
      body:
        dynamic: true

  - method: GET
    path: /users/me
    response:
      body:
        static: true
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["validate", "mockyfast.yaml"])

        assert result.exit_code == 0
        assert "Warning:" in result.stdout
        assert "/users/me is unreachable" in result.stdout
        assert "Configuration is valid." in result.stdout


def test_echo_route_table_lists_methods_and_paths(capsys):
    config = {
        "routes": [
            {
                "method": "get",
                "path": "/users",
                "response": {"data_source": {"mutable": True, "file": "./u.json"}},
            },
            {"method": "GET", "path": "/health", "response": {"body": {}}},
        ]
    }

    echo_route_table(config)
    output = capsys.readouterr().out

    assert "Serving 2 route(s):" in output
    assert "GET  /users  [mutable]" in output
    assert "/health" in output


def test_watch_directory_resolves_a_file_to_its_parent(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text("routes: []", encoding="utf-8")

    assert watch_directory(str(config_file)) == str(tmp_path.resolve())
    assert watch_directory(str(tmp_path)) == str(tmp_path.resolve())


def test_create_app_from_env_reads_the_configured_path(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text('[{"id": 1, "name": "Mario"}]', encoding="utf-8")

    monkeypatch.setenv("MOCKYFAST_CONFIG", str(data_dir))
    monkeypatch.delenv("MOCKYFAST_INDEX", raising=False)

    client = TestClient(create_app_from_env())

    assert client.get("/users").json() == [{"id": 1, "name": "Mario"}]
    assert client.get("/").status_code == 200


def test_create_app_from_env_honours_the_index_flag(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text('[{"id": 1}]', encoding="utf-8")

    monkeypatch.setenv("MOCKYFAST_CONFIG", str(data_dir))
    monkeypatch.setenv("MOCKYFAST_INDEX", "0")

    client = TestClient(create_app_from_env(), raise_server_exceptions=False)

    assert client.get("/").status_code == 404
