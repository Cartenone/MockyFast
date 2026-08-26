import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from test_readme import readme_configs
from typer.testing import CliRunner

from mockyfast.cli import app
from mockyfast.models import config_json_schema

runner = CliRunner()

PUBLISHED_SCHEMA = Path(__file__).resolve().parent.parent / "mockyfast.schema.json"


@pytest.fixture(scope="module")
def validator():
    return Draft202012Validator(config_json_schema())


def test_the_published_schema_matches_the_models():
    published = json.loads(PUBLISHED_SCHEMA.read_text(encoding="utf-8"))

    assert published == config_json_schema(), (
        "mockyfast.schema.json is out of date; regenerate it with "
        "'mkf schema -o mockyfast.schema.json'"
    )


def test_the_schema_is_a_valid_json_schema():
    Draft202012Validator.check_schema(config_json_schema())


def test_a_not_set_field_does_not_advertise_a_null_default():
    route = config_json_schema()["$defs"]["Response"]["properties"]["status_code"]

    assert "default" not in route


@pytest.mark.parametrize("block", readme_configs(), ids=range(len(readme_configs())))
def test_the_schema_accepts_every_readme_example(validator, block):
    assert list(validator.iter_errors(yaml.safe_load(block))) == []


def test_the_schema_accepts_a_lowercase_method(validator):
    config = {"routes": [{"method": "get", "path": "/x", "response": {"body": {}}}]}

    assert list(validator.iter_errors(config)) == []


def test_the_schema_rejects_an_unknown_key(validator):
    config = {"routes": [{"method": "GET", "path": "/x", "respones": {}}]}

    assert list(validator.iter_errors(config))


def test_schema_command_prints_the_schema():
    result = runner.invoke(app, ["schema"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == config_json_schema()


def test_schema_command_writes_a_file(tmp_path):
    target = tmp_path / "mockyfast.schema.json"

    result = runner.invoke(app, ["schema", "--output", str(target)])

    assert result.exit_code == 0
    assert json.loads(target.read_text(encoding="utf-8")) == config_json_schema()
