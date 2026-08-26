import json

import pytest
import yaml
from typer.testing import CliRunner

from mockyfast.cli import app as cli
from mockyfast.config import load_config_source
from mockyfast.conformance import check_against_spec
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


USER_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "active": {"type": "boolean"},
    },
    "required": ["id", "name"],
}


def user_spec() -> dict:
    return document({"/users/{id}": {"get": json_response(USER_SCHEMA)}})


def problems_for(tmp_path, config_body: str, spec: dict) -> list[str]:
    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(config_body, encoding="utf-8")

    config, resolved_path = load_config_source(str(config_path))

    return check_against_spec(config, resolved_path, spec).problems


def route_config(body: dict, status: int | None = None, path: str = "/users/{id}") -> str:
    response: dict = {"body": body}

    if status is not None:
        response["status_code"] = status

    return yaml.safe_dump(
        {"routes": [{"method": "GET", "path": path, "response": response}]}
    )


# ------------------------------------------------------------------ agreement


def test_a_matching_mock_reports_nothing(tmp_path):
    body = {"id": 1, "name": "Mario", "active": True}

    assert problems_for(tmp_path, route_config(body), user_spec()) == []


def test_a_path_parameter_may_be_named_differently(tmp_path):
    """`/users/{user_id}` and `/users/{id}` are the same operation."""
    config = route_config({"id": 1, "name": "Mario"}, path="/users/{user_id}")

    assert problems_for(tmp_path, config, user_spec()) == []


def test_a_config_imported_from_a_spec_conforms_to_it(tmp_path):
    spec = user_spec()

    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(
        yaml.safe_dump(build_config_from_openapi(spec)), encoding="utf-8"
    )

    config, resolved_path = load_config_source(str(config_path))

    assert check_against_spec(config, resolved_path, spec).problems == []


def test_a_free_form_object_accepts_any_field(tmp_path):
    spec = document({"/anything": {"get": json_response({"type": "object"})}})
    config = route_config({"whatever": 1}, path="/anything")

    assert problems_for(tmp_path, config, spec) == []


def test_an_unrendered_placeholder_is_not_judged_on_its_type(tmp_path):
    """`{id}` is a path parameter, and its real type is not knowable here."""
    config = route_config({"id": "{id}", "name": "Mario"})

    assert problems_for(tmp_path, config, user_spec()) == []


# --------------------------------------------------------------- disagreement


def test_a_renamed_field_is_reported_from_both_sides(tmp_path):
    config = route_config({"id": 1, "fullName": "Mario"})

    problems = problems_for(tmp_path, config, user_spec())

    assert any("'fullName' is not declared in the spec" in p for p in problems)
    assert any("'name' is required by the spec" in p for p in problems)


def test_a_near_miss_names_the_field_the_spec_declares(tmp_path):
    config = route_config({"id": 1, "name": "Mario", "activ": True})

    problems = problems_for(tmp_path, config, user_spec())

    assert any("The spec declares 'active'." in problem for problem in problems)


def test_a_field_of_the_wrong_type_is_reported(tmp_path):
    config = route_config({"id": "1", "name": "Mario"})

    problems = problems_for(tmp_path, config, user_spec())

    assert problems == [
        "Route #1 GET /users/{id}: field 'id' is a string, and the spec "
        "declares an integer."
    ]


def test_an_undeclared_status_is_reported(tmp_path):
    config = route_config({"id": 1, "name": "Mario"}, status=418)

    problems = problems_for(tmp_path, config, user_spec())

    assert problems == [
        "Route #1 GET /users/{id}: the spec declares no status 418 for it, only 200."
    ]


def test_a_status_wildcard_covers_its_range(tmp_path):
    spec = document(
        {"/users/{id}": {"get": {"responses": {"2XX": {"description": "ok"}}}}}
    )

    assert problems_for(tmp_path, route_config({}, status=201), spec) == []


def test_a_default_response_covers_every_status(tmp_path):
    spec = document(
        {"/users/{id}": {"get": {"responses": {"default": {"description": "any"}}}}}
    )

    assert problems_for(tmp_path, route_config({}, status=599), spec) == []


def test_a_path_the_spec_does_not_declare_is_reported(tmp_path):
    config = route_config({"ok": True}, path="/internal/debug")

    assert problems_for(tmp_path, config, user_spec()) == [
        "Route #1 GET /internal/debug answers a path the spec does not declare."
    ]


def test_a_method_the_spec_does_not_declare_is_reported(tmp_path):
    config = yaml.safe_dump(
        {
            "routes": [
                {
                    "method": "DELETE",
                    "path": "/users/{id}",
                    "response": {"body": {}},
                }
            ]
        }
    )

    assert problems_for(tmp_path, config, user_spec()) == [
        "Route #1 DELETE /users/{id}: the spec declares no DELETE for that path."
    ]


def test_a_nested_field_is_reported_with_its_path(tmp_path):
    spec = document(
        {
            "/orders": {
                "get": json_response(
                    {
                        "type": "object",
                        "properties": {
                            "customer": {
                                "type": "object",
                                "properties": {"email": {"type": "string"}},
                            }
                        },
                    }
                )
            }
        }
    )

    config = route_config({"customer": {"mail": "a@b.c"}}, path="/orders")

    assert problems_for(tmp_path, config, spec) == [
        "Route #1 GET /orders: field 'customer.mail' is not declared in the spec. "
        "The spec declares 'email'."
    ]


def test_a_list_is_compared_through_its_items(tmp_path):
    spec = document(
        {"/users": {"get": json_response({"type": "array", "items": USER_SCHEMA})}}
    )

    config = route_config([{"id": 1, "name": "Mario", "extra": 1}], path="/users")

    assert problems_for(tmp_path, config, spec) == [
        "Route #1 GET /users: field '[].extra' is not declared in the spec."
    ]


def test_a_data_source_is_compared_through_the_rows_it_serves(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(
        '[{"id": 1, "nome": "Mario"}]', encoding="utf-8"
    )

    spec = document(
        {"/users": {"get": json_response({"type": "array", "items": USER_SCHEMA})}}
    )

    config = yaml.safe_dump(
        {
            "routes": [
                {
                    "method": "GET",
                    "path": "/users",
                    "response": {
                        "data_source": {
                            "type": "json",
                            "file": "./data/users.json",
                            "mode": "all",
                        }
                    },
                }
            ]
        }
    )

    problems = problems_for(tmp_path, config, spec)

    assert any("'[].nome' is not declared" in problem for problem in problems)
    assert any("'[].name' is required" in problem for problem in problems)


def test_a_reference_is_followed(tmp_path):
    spec = document(
        {"/users/{id}": {"get": json_response({"$ref": "#/components/schemas/User"})}},
        components={"schemas": {"User": USER_SCHEMA}},
    )

    config = route_config({"id": 1, "name": "Mario", "nope": 1})

    assert problems_for(tmp_path, config, spec) == [
        "Route #1 GET /users/{id}: field 'nope' is not declared in the spec."
    ]


def test_a_self_referencing_schema_terminates(tmp_path):
    spec = document(
        {"/nodes": {"get": json_response({"$ref": "#/components/schemas/Node"})}},
        components={
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                }
            }
        },
    )

    config = route_config({"child": {"child": {}}}, path="/nodes")

    assert problems_for(tmp_path, config, spec) == []


def test_an_alternation_is_left_alone(tmp_path):
    """A value that may take several shapes cannot be judged against one."""
    spec = document(
        {
            "/thing": {
                "get": json_response(
                    {"oneOf": [{"type": "string"}, {"type": "integer"}]}
                )
            }
        }
    )

    assert problems_for(tmp_path, route_config({}, path="/thing"), spec) == []


# ----------------------------------------------------------------- the report


def test_operations_no_route_answers_are_counted(tmp_path):
    spec = document(
        {
            "/users/{id}": {"get": json_response(USER_SCHEMA)},
            "/orders": {"get": json_response({"type": "object"})},
            "/carts": {"get": json_response({"type": "object"})},
        }
    )

    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(
        route_config({"id": 1, "name": "Mario"}), encoding="utf-8"
    )

    config, resolved_path = load_config_source(str(config_path))
    report = check_against_spec(config, resolved_path, spec)

    assert report.checked_routes == 1
    assert report.uncovered_operations == 2
    assert report.problems == []


def test_a_swagger_2_document_is_refused(tmp_path):
    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(route_config({}), encoding="utf-8")

    config, resolved_path = load_config_source(str(config_path))

    with pytest.raises(ValueError, match="Convert it to OpenAPI 3 first"):
        check_against_spec(config, resolved_path, {"swagger": "2.0", "paths": {}})


# ------------------------------------------------------------------- the flag


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_spec(directory, spec) -> str:
    path = directory / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    return str(path)


def test_validate_against_a_matching_spec_succeeds(workdir):
    (workdir / "mockyfast.yaml").write_text(
        route_config({"id": 1, "name": "Mario"}), encoding="utf-8"
    )
    spec_path = write_spec(workdir, user_spec())

    result = runner.invoke(cli, ["validate", "mockyfast.yaml", "--against", spec_path])

    assert result.exit_code == 0
    assert "Checked 1 route(s) against the spec." in result.output
    assert "Not conformant" not in result.output


def test_validate_against_a_spec_fails_on_a_difference(workdir):
    (workdir / "mockyfast.yaml").write_text(
        route_config({"id": 1, "fullName": "Mario"}), encoding="utf-8"
    )
    spec_path = write_spec(workdir, user_spec())

    result = runner.invoke(cli, ["validate", "mockyfast.yaml", "--against", spec_path])

    assert result.exit_code == 1
    assert "Configuration is valid." in result.output
    assert "Not conformant: Route #1 GET /users/{id}: field 'fullName'" in result.output


def test_validate_reports_the_operations_it_found_no_route_for(workdir):
    (workdir / "mockyfast.yaml").write_text(
        route_config({"id": 1, "name": "Mario"}), encoding="utf-8"
    )
    spec = user_spec()
    spec["paths"]["/orders"] = {"get": json_response({"type": "object"})}
    spec_path = write_spec(workdir, spec)

    result = runner.invoke(cli, ["validate", "mockyfast.yaml", "--against", spec_path])

    assert result.exit_code == 0
    assert "declares 1 operation(s) that no route answers" in result.output


def test_validate_against_a_missing_spec_fails(workdir):
    (workdir / "mockyfast.yaml").write_text(route_config({}), encoding="utf-8")

    result = runner.invoke(
        cli, ["validate", "mockyfast.yaml", "--against", "./nope.yaml"]
    )

    assert result.exit_code == 1
    assert "Cannot read the OpenAPI document" in result.output


def test_validate_without_the_flag_says_nothing_about_conformance(workdir):
    (workdir / "mockyfast.yaml").write_text(route_config({}), encoding="utf-8")

    result = runner.invoke(cli, ["validate", "mockyfast.yaml"])

    assert result.exit_code == 0
    assert "against the spec" not in result.output
