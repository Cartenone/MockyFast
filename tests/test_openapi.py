import json

import pytest
import yaml
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient
from openapi_spec_validator import validate as validate_openapi
from test_readme import readme_configs, write_example_data
from typer.testing import CliRunner

from mockyfast.app import create_app
from mockyfast.cli import app as cli
from mockyfast.config import load_config_source
from mockyfast.listing import RESERVED_QUERY_PARAMS
from mockyfast.openapi import LIST_QUERY_PARAMETERS, build_openapi

runner = CliRunner()

USERS_JSON = '[{"id": 1, "name": "Mario"}, {"id": 2, "name": "Luigi"}]'

USERS_CSV = "id,name,active\n1,Mario,true\n2,Luigi,false\n"


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")

    return str(config_file)


def write_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "users.json").write_text(USERS_JSON, encoding="utf-8")
    (data_dir / "users.csv").write_text(USERS_CSV, encoding="utf-8")


def spec_for(tmp_path, body):
    write_data(tmp_path)

    config, resolved_path = load_config_source(write_config(tmp_path, body))

    return build_openapi(config, resolved_path)


def json_schema(operation, status="200"):
    return operation["responses"][status]["content"]["application/json"]["schema"]


# ------------------------------------------------------------- response shapes


def test_a_data_source_route_documents_the_shape_of_its_rows(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        where:
          field: id
          equals_path_param: user_id
""",
    )

    assert json_schema(spec["paths"]["/users/{user_id}"]["get"]) == {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }


def test_a_list_route_documents_an_array_of_rows(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
""",
    )

    schema = json_schema(spec["paths"]["/users"]["get"])

    assert schema["type"] == "array"
    assert schema["items"]["properties"]["name"] == {"type": "string"}


def test_a_wrapped_list_is_documented_under_its_key(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        wrap: items
""",
    )

    schema = json_schema(spec["paths"]["/users"]["get"])

    assert schema["properties"]["items"]["type"] == "array"


def test_a_csv_source_documents_text_until_it_is_coerced(tmp_path):
    body = """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
"""

    plain = spec_for(tmp_path, body)
    coerced = spec_for(tmp_path, body + "        coerce_types: true\n")

    plain_items = json_schema(plain["paths"]["/users"]["get"])["items"]
    coerced_items = json_schema(coerced["paths"]["/users"]["get"])["items"]

    assert plain_items["properties"]["active"] == {"type": "string"}
    assert coerced_items["properties"]["active"] == {"type": "boolean"}
    assert coerced_items["properties"]["id"] == {"type": "integer"}


def test_a_template_is_documented_with_the_type_it_renders_to(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /orders
    response:
      body:
        id: "{{uuid}}"
        quantity: "{{randint:1:5}}"
""",
    )

    properties = json_schema(spec["paths"]["/orders"]["get"])["properties"]

    assert properties == {
        "id": {"type": "string"},
        "quantity": {"type": "integer"},
    }


def test_a_list_route_documents_the_total_count_header(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        list_query: true
""",
    )

    headers = spec["paths"]["/users"]["get"]["responses"]["200"]["headers"]

    assert headers["X-Total-Count"]["schema"] == {"type": "integer"}


# ------------------------------------------------------------- status coverage


def test_a_not_found_body_is_documented_with_its_status(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        where:
          field: id
          equals_path_param: user_id
        not_found_status: 410
        not_found_body:
          error: gone
""",
    )

    responses = spec["paths"]["/users/{user_id}"]["get"]["responses"]

    assert responses["410"]["content"]["application/json"]["example"] == {
        "error": "gone"
    }


def test_a_create_route_documents_the_write_failures(tmp_path):
    spec = spec_for(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
    )

    assert set(spec["paths"]["/users"]["post"]["responses"]) == {"201", "400", "409"}
    assert set(spec["paths"]["/users/{id}"]["put"]["responses"]) == {"200", "400", "404"}


def test_a_fault_status_is_documented(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /flaky
    response:
      body:
        ok: true
      fault:
        probability: 0.2
        status_code: 503
        body:
          error: overloaded
""",
    )

    responses = spec["paths"]["/flaky"]["get"]["responses"]

    assert responses["503"]["content"]["application/json"]["example"] == {
        "error": "overloaded"
    }


def test_a_sequence_documents_every_status_it_can_return(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /jobs/{job_id}
    responses:
      - status_code: 202
        body:
          status: accepted
      - status_code: 200
        body:
          status: done
""",
    )

    operation = spec["paths"]["/jobs/{job_id}"]["get"]

    assert set(operation["responses"]) == {"200", "202"}
    assert operation["summary"] == "Response sequence of 2 calls"


def test_a_delete_documents_the_body_it_really_returns(tmp_path):
    spec = spec_for(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
    )

    schema = json_schema(spec["paths"]["/users/{id}"]["delete"])

    assert schema["properties"] == {"deleted": {"type": "boolean"}}


# ----------------------------------------------------------------- parameters


def test_a_path_parameter_says_which_field_it_selects(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        where:
          field: id
          equals_path_param: user_id
""",
    )

    parameter = spec["paths"]["/users/{user_id}"]["get"]["parameters"][0]

    assert parameter["name"] == "user_id"
    assert parameter["in"] == "path"
    assert parameter["required"] is True
    assert "'id'" in parameter["description"]


def test_a_matched_query_parameter_is_documented(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /orders
    request:
      query:
        status: shipped
    response:
      body:
        items: []
""",
    )

    parameter = spec["paths"]["/orders"]["get"]["parameters"][0]

    assert parameter["name"] == "status"
    assert parameter["in"] == "query"
    assert "shipped" in parameter["description"]


def test_a_matched_header_is_documented(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /profile
    request:
      headers:
        Authorization: { matches: '^Bearer ' }
    response:
      body:
        user: mario
""",
    )

    parameter = spec["paths"]["/profile"]["get"]["parameters"][0]

    assert parameter["name"] == "Authorization"
    assert parameter["in"] == "header"


def test_the_documented_list_parameters_are_the_ones_listing_reserves():
    assert set(LIST_QUERY_PARAMETERS) == RESERVED_QUERY_PARAMS


# ------------------------------------------------------------------ operations


def test_routes_sharing_a_path_become_one_operation(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: GET
    path: /orders
    request:
      query:
        status: shipped
    response:
      status_code: 200
      body:
        items: []

  - method: GET
    path: /orders
    response:
      status_code: 404
      body:
        error: none
""",
    )

    operation = spec["paths"]["/orders"]["get"]

    assert set(operation["responses"]) == {"200", "404"}
    assert "1. when query status match" in operation["description"]
    assert "2. otherwise" in operation["description"]


def test_a_write_route_documents_the_body_it_expects(tmp_path):
    spec = spec_for(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
    )

    request_body = spec["paths"]["/users"]["post"]["requestBody"]
    schema = request_body["content"]["application/json"]["schema"]

    assert request_body["required"] is True
    assert schema["properties"]["name"] == {"type": "string"}


def test_a_patch_does_not_demand_the_whole_resource(tmp_path):
    spec = spec_for(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
    )

    schema = spec["paths"]["/users/{id}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"]

    assert "required" not in schema


def test_a_matched_body_becomes_the_documented_request_body(tmp_path):
    spec = spec_for(
        tmp_path,
        """
routes:
  - method: POST
    path: /login
    request:
      json:
        username: admin
        age: { gte: 18 }
    response:
      body:
        token: abc
""",
    )

    schema = spec["paths"]["/login"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]

    assert schema["properties"]["username"] == {"type": "string"}
    # An operator says what the value must satisfy, not what type it is.
    assert schema["properties"]["age"] == {}


def test_operation_ids_are_unique(tmp_path):
    spec = spec_for(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
    )

    ids = [
        operation["operationId"]
        for methods in spec["paths"].values()
        for operation in methods.values()
    ]

    assert len(ids) == len(set(ids))


def test_an_unreadable_data_file_leaves_the_document_open(tmp_path):
    """A missing file is for `validate` to report, not a reason to fail here."""
    config = {
        "routes": [
            {
                "method": "GET",
                "path": "/users",
                "response": {
                    "data_source": {
                        "type": "json",
                        "file": "./data/gone.json",
                        "mode": "all",
                    }
                },
            }
        ]
    }

    spec = build_openapi(config, str(tmp_path / "mockyfast.yaml"))

    assert json_schema(spec["paths"]["/users"]["get"])["items"] == {"type": "object"}


# --------------------------------------------------------------- the whole doc


@pytest.mark.parametrize("block", readme_configs(), ids=range(len(readme_configs())))
def test_every_readme_example_produces_a_valid_openapi_document(tmp_path, block):
    write_example_data(tmp_path)

    config, resolved_path = load_config_source(write_config(tmp_path, block))

    validate_openapi(build_openapi(config, resolved_path))


def test_the_server_serves_the_generated_document(tmp_path):
    write_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
""",
    )

    served = TestClient(create_app(config_path)).get("/openapi.json").json()

    assert served["paths"]["/users"]["get"]["summary"] == "List users"
    validate_openapi(served)


def test_fastapi_still_derives_no_request_parameters(tmp_path):
    """The published document is ours now, so check what FastAPI would infer.

    Closure state in a handler signature became an overridable query parameter
    once; the document no longer comes from those signatures, so it can no
    longer be the thing that catches it.
    """
    write_data(tmp_path)

    served = create_app(
        write_config(
            tmp_path,
            """
routes:
  - method: GET
    path: /x
    response:
      body:
        ok: true
""",
        )
    )

    derived = get_openapi(title="MockyFast", version="0", routes=served.routes)

    assert derived["paths"]["/x"]["get"].get("parameters", []) == []


# -------------------------------------------------------------- the cli command


def test_openapi_command_prints_the_document(tmp_path):
    write_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
""",
    )

    result = runner.invoke(cli, ["openapi", config_path])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["openapi"] == "3.1.0"


def test_openapi_command_writes_yaml_when_asked_for_it(tmp_path):
    write_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      body:
        ok: true
""",
    )

    target = tmp_path / "openapi.yaml"
    result = runner.invoke(cli, ["openapi", config_path, "-o", str(target)])

    assert result.exit_code == 0
    assert yaml.safe_load(target.read_text(encoding="utf-8"))["paths"].keys() == {
        "/users"
    }


def test_openapi_command_reports_an_invalid_configuration(tmp_path):
    config_path = write_config(tmp_path, "routes: not-a-list\n")

    result = runner.invoke(cli, ["openapi", config_path])

    assert result.exit_code == 1
    assert "Invalid configuration" in result.stdout
