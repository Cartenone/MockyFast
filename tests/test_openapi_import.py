import json

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typer.testing import CliRunner

from mockyfast.app import create_app
from mockyfast.cli import app as cli
from mockyfast.config import load_config
from mockyfast.openapi_import import build_config_from_openapi

runner = CliRunner()


def document(paths: dict, **extra) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": paths,
        **extra,
    }


def json_response(schema: dict, status: str = "200") -> dict:
    return {
        "responses": {
            status: {
                "description": "ok",
                "content": {"application/json": {"schema": schema}},
            }
        }
    }


def body_for(schema: dict):
    config = build_config_from_openapi(
        document({"/thing": {"get": json_response(schema)}})
    )

    return config["routes"][0]["response"]["body"]


# ------------------------------------------------------------------ the routes


def test_each_operation_becomes_a_route():
    config = build_config_from_openapi(
        document(
            {
                "/users": {
                    "get": json_response({"type": "object"}),
                    "post": json_response({"type": "object"}, status="201"),
                },
                "/users/{user_id}": {"get": json_response({"type": "object"})},
            }
        )
    )

    assert [(route["method"], route["path"]) for route in config["routes"]] == [
        ("GET", "/users"),
        ("POST", "/users"),
        ("GET", "/users/{user_id}"),
    ]


def test_a_non_default_status_is_written_down():
    config = build_config_from_openapi(
        document({"/users": {"post": json_response({"type": "object"}, status="201")}})
    )

    assert config["routes"][0]["response"]["status_code"] == 201


def test_a_200_is_left_implicit():
    config = build_config_from_openapi(
        document({"/users": {"get": json_response({"type": "object"})}})
    )

    assert "status_code" not in config["routes"][0]["response"]


def test_the_lowest_success_status_is_the_one_mocked():
    operation = {
        "responses": {
            "500": {"description": "boom"},
            "204": {"description": "gone"},
            "201": {"description": "made"},
        }
    }

    config = build_config_from_openapi(document({"/users": {"post": operation}}))

    assert config["routes"][0]["response"]["status_code"] == 201


def test_an_operation_with_only_errors_still_produces_a_route():
    operation = {"responses": {"404": {"description": "nope"}}}

    config = build_config_from_openapi(document({"/users": {"get": operation}}))

    assert config["routes"][0]["response"]["status_code"] == 404


# ------------------------------------------------------------- schema mapping


def test_an_integer_becomes_a_randint_within_its_bounds():
    assert body_for(
        {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 18, "maximum": 99}},
        }
    ) == {"age": "{{randint:18:99}}"}


def test_an_integer_bound_written_as_a_float_is_honoured():
    """A spec generated from Python types writes `maximum: 9999.0`."""
    assert body_for(
        {
            "type": "object",
            "properties": {"id": {"type": "integer", "minimum": 1.0, "maximum": 9999.0}},
        }
    ) == {"id": "{{randint:1:9999}}"}


def test_a_number_becomes_a_randfloat():
    assert body_for({"type": "number"}) == "{{randfloat:0:100}}"


def test_a_string_enum_becomes_a_choice():
    assert body_for({"type": "string", "enum": ["gold", "silver"]}) == (
        "{{choice:gold|silver}}"
    )


def test_a_non_string_enum_keeps_its_first_value():
    """`{{choice:1|2}}` would render the text '1', not the number."""
    assert body_for({"type": "integer", "enum": [1, 2]}) == 1


def test_an_enum_option_holding_a_pipe_keeps_its_first_value():
    assert body_for({"type": "string", "enum": ["a|b", "c"]}) == "a|b"


def test_a_string_format_maps_to_the_matching_template():
    assert body_for(
        {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "created_at": {"type": "string", "format": "date-time"},
                "email": {"type": "string", "format": "email"},
                "name": {"type": "string"},
            },
        }
    ) == {
        "id": "{{uuid}}",
        "created_at": "{{now}}",
        "email": "user@example.com",
        "name": "string",
    }


def test_a_boolean_becomes_true():
    assert body_for({"type": "boolean"}) is True


def test_a_nullable_type_uses_the_type_that_is_not_null():
    assert body_for({"type": ["string", "null"]}) == "string"


def test_an_array_becomes_a_list_of_independent_items():
    body = body_for({"type": "array", "items": {"type": "object", "properties": {}}})

    assert len(body) == 2
    # Sharing one object would make the written YAML a nest of anchors.
    assert body[0] is not body[1]


def test_an_example_in_the_spec_wins_over_generation():
    assert body_for(
        {"type": "object", "properties": {"id": {"type": "integer", "example": 42}}}
    ) == {"id": 42}


def test_a_media_type_example_wins_over_the_schema():
    operation = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "application/json": {
                        "schema": {"type": "object"},
                        "example": {"handwritten": True},
                    }
                },
            }
        }
    }

    config = build_config_from_openapi(document({"/thing": {"get": operation}}))

    assert config["routes"][0]["response"]["body"] == {"handwritten": True}


def test_a_response_without_content_gets_an_empty_body():
    operation = {"responses": {"204": {"description": "no content"}}}

    config = build_config_from_openapi(document({"/thing": {"delete": operation}}))

    assert config["routes"][0]["response"]["body"] == {}


# ----------------------------------------------------------------- references


def test_a_reference_is_resolved():
    spec = document(
        {"/users": {"get": json_response({"$ref": "#/components/schemas/User"})}},
        components={
            "schemas": {
                "User": {"type": "object", "properties": {"name": {"type": "string"}}}
            }
        },
    )

    assert build_config_from_openapi(spec)["routes"][0]["response"]["body"] == {
        "name": "string"
    }


def test_a_schema_that_contains_itself_terminates():
    spec = document(
        {"/nodes": {"get": json_response({"$ref": "#/components/schemas/Node"})}},
        components={
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "child": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        },
    )

    assert build_config_from_openapi(spec)["routes"][0]["response"]["body"] == {
        "name": "string",
        "child": {},
    }


def test_all_of_merges_the_properties_of_its_parts():
    spec = document(
        {
            "/users": {
                "get": json_response(
                    {
                        "allOf": [
                            {"$ref": "#/components/schemas/Named"},
                            {"properties": {"age": {"type": "integer"}}},
                        ]
                    }
                )
            }
        },
        components={
            "schemas": {
                "Named": {"type": "object", "properties": {"name": {"type": "string"}}}
            }
        },
    )

    assert set(build_config_from_openapi(spec)["routes"][0]["response"]["body"]) == {
        "name",
        "age",
    }


def test_one_of_takes_the_first_alternative():
    assert body_for({"oneOf": [{"type": "string"}, {"type": "integer"}]}) == "string"


def test_a_reference_outside_the_document_is_refused():
    spec = document({"/users": {"get": json_response({"$ref": "common.yaml#/User"})}})

    with pytest.raises(ValueError, match="Bundle the spec into a single file"):
        build_config_from_openapi(spec)


def test_a_reference_that_does_not_resolve_is_reported():
    spec = document(
        {"/users": {"get": json_response({"$ref": "#/components/schemas/Gone"})}}
    )

    with pytest.raises(ValueError, match="does not resolve"):
        build_config_from_openapi(spec)


# ------------------------------------------------------------ refused documents


def test_a_swagger_2_document_is_refused():
    with pytest.raises(ValueError, match="Convert it to OpenAPI 3 first"):
        build_config_from_openapi({"swagger": "2.0", "paths": {}})


def test_a_document_without_an_openapi_version_is_refused():
    with pytest.raises(ValueError, match="must declare an 'openapi' version"):
        build_config_from_openapi({"paths": {}})


def test_a_document_without_paths_is_refused():
    with pytest.raises(ValueError, match="declares no paths to mock"):
        build_config_from_openapi(document({}))


def test_a_document_whose_paths_hold_no_operations_is_refused():
    with pytest.raises(ValueError, match="declares no operations to mock"):
        build_config_from_openapi(document({"/users": {"summary": "just a note"}}))


# -------------------------------------------------------------- the round trip


def test_the_generated_config_loads(tmp_path):
    spec = document(
        {
            "/users": {
                "get": json_response(
                    {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/User"},
                    }
                )
            }
        },
        components={
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "role": {"type": "string", "enum": ["admin", "user"]},
                    },
                }
            }
        },
    )

    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(
        yaml.safe_dump(build_config_from_openapi(spec), sort_keys=False),
        encoding="utf-8",
    )

    assert load_config(str(config_path))["routes"][0]["method"] == "GET"


def build_demo_spec() -> dict:
    """A spec from a real generator, rather than one written to suit the reader."""

    class User(BaseModel):
        id: int = Field(ge=1, le=9999)
        name: str
        role: str
        active: bool
        score: float

    api = FastAPI(title="Demo")

    @api.get("/users", response_model=list[User])
    def list_users(): ...

    @api.get("/users/{user_id}", response_model=User)
    def get_user(user_id: int): ...

    @api.post("/users", response_model=User, status_code=201)
    def create_user(user: User): ...

    return api.openapi()


def test_a_spec_from_fastapi_becomes_a_mock_that_answers_it(tmp_path):
    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(
        yaml.safe_dump(
            build_config_from_openapi(build_demo_spec()), sort_keys=False
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app(str(config_path)))

    listed = client.get("/users")
    created = client.post("/users", json={})

    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert 1 <= listed.json()[0]["id"] <= 9999
    assert isinstance(listed.json()[0]["active"], bool)
    assert isinstance(listed.json()[0]["score"], float)

    assert created.status_code == 201
    assert client.get("/users/7").status_code == 200


# --------------------------------------------------------------- the cli option


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_spec(directory, spec) -> str:
    path = directory / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    return str(path)


def test_init_from_openapi_writes_a_config_that_validates(workdir):
    spec_path = write_spec(
        workdir, document({"/users": {"get": json_response({"type": "object"})}})
    )

    result = runner.invoke(cli, ["init", "--from-openapi", spec_path])

    assert result.exit_code == 0
    assert "Configuration written to" in result.output
    assert "path: /users" in (workdir / "mockyfast.yaml").read_text(encoding="utf-8")
    assert runner.invoke(cli, ["validate", "mockyfast.yaml"]).exit_code == 0


def test_init_reads_a_spec_written_as_yaml(workdir):
    spec_path = workdir / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(document({"/users": {"get": json_response({"type": "object"})}})),
        encoding="utf-8",
    )

    assert runner.invoke(cli, ["init", "--from-openapi", str(spec_path)]).exit_code == 0


def test_init_from_a_broken_spec_writes_nothing(workdir):
    spec_path = write_spec(workdir, {"swagger": "2.0", "paths": {}})

    result = runner.invoke(cli, ["init", "--from-openapi", spec_path])

    assert result.exit_code == 1
    assert "Cannot read the OpenAPI document" in result.output
    assert not (workdir / "mockyfast.yaml").exists()


def test_init_from_a_missing_spec_fails(workdir):
    result = runner.invoke(cli, ["init", "--from-openapi", "./nope.yaml"])

    assert result.exit_code == 1
    assert "OpenAPI document not found" in result.output


def test_init_refuses_two_sources_at_once(workdir):
    result = runner.invoke(
        cli, ["init", "--from-data", "./data", "--from-openapi", "./spec.yaml"]
    )

    assert result.exit_code == 1
    assert "not both" in result.output
    assert not (workdir / "mockyfast.yaml").exists()
