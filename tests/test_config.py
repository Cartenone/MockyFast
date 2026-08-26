import pytest

from mockyfast.config import load_config, load_json_file


def test_load_config_reads_valid_yaml(tmp_path):
    config_file = tmp_path / "test.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert "routes" in config
    assert isinstance(config["routes"], list)
    assert config["routes"][0]["method"] == "GET"
    assert config["routes"][0]["path"] == "/health"


def test_load_config_raises_if_file_does_not_exist():
    with pytest.raises(FileNotFoundError):
        load_config("missing.yaml")


def test_load_config_raises_if_root_is_not_a_dict(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
- method: GET
  path: /health
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root object"):
        load_config(str(config_file))


def test_load_config_raises_if_routes_is_missing(tmp_path):
    config_file = tmp_path / "missing_routes.yaml"
    config_file.write_text(
        """
name: example
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing 'routes' or 'resources' key"):
        load_config(str(config_file))


def test_load_config_raises_if_routes_is_not_a_list(tmp_path):
    config_file = tmp_path / "invalid_routes.yaml"
    config_file.write_text(
        """
routes:
  method: GET
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="'routes' must be a list"):
        load_config(str(config_file))


def test_load_json_file_reads_json_relative_to_config(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text("routes: []", encoding="utf-8")

    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()

    json_file = responses_dir / "users.json"
    json_file.write_text(
        """
{
  "users": [
    { "id": 1, "name": "Mario" }
  ]
}
""",
        encoding="utf-8",
    )

    data = load_json_file(str(config_file), "./responses/users.json")

    assert data == {
        "users": [
            {"id": 1, "name": "Mario"}
        ]
    }


def test_load_json_file_raises_if_json_file_does_not_exist(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text("routes: []", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        load_json_file(str(config_file), "./responses/missing.json")


def test_load_config_raises_if_route_has_no_method(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - path: /health
    response:
      status_code: 200
      body:
        ok: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is missing 'method'"):
        load_config(str(config_file))


def test_load_config_raises_if_route_has_no_path(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    response:
      status_code: 200
      body:
        ok: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is missing 'path'"):
        load_config(str(config_file))


def test_load_config_raises_if_route_has_no_response(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /health
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is missing 'response'"):
        load_config(str(config_file))


def test_load_config_raises_if_body_and_body_from_are_both_present(tmp_path):
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()

    json_file = responses_dir / "health.json"
    json_file.write_text('{"ok": true}', encoding="utf-8")

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /health
    response:
      body:
        ok: true
      body_from: ./responses/health.json
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="can only define one of 'body', 'body_from', or 'data_source'",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_request_query_is_not_an_object(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /orders
    request:
      query: shipped
    response:
      status_code: 200
      body:
        items: []
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'request.query' in route #1 must be an object",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_request_headers_is_not_an_object(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /profile
    request:
      headers: Bearer secret-token
    response:
      status_code: 200
      body:
        user: mario
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'request.headers' in route #1 must be an object",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_request_json_is_not_object_or_list(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: POST
    path: /login
    request:
      json: hello
    response:
      status_code: 200
      body:
        token: fake-jwt-token
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'request.json' in route #1 must be an object or a list",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_response_delay_ms_is_not_an_int(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /slow
    response:
      status_code: 200
      delay_ms: hello
      body:
        ok: true
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.delay_ms' in route #1 must be an integer",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_response_delay_ms_is_negative(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /slow
    response:
      status_code: 200
      delay_ms: -100
      body:
        ok: true
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.delay_ms' in route #1 cannot be negative",
    ):
        load_config(str(config_file))

def test_load_config_accepts_csv_data_source(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name\n1,Mario\n2,Luigi\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: first
        where:
          column: id
          equals_path_param: user_id
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert "routes" in config


def test_load_config_raises_if_data_source_is_combined_with_body(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name\n1,Mario\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      body:
        ok: true
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="can only define one of 'body', 'body_from', or 'data_source'",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_data_source_mode_is_invalid(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name\n1,Mario\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: invalid
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.mode' in route #1 must be 'first' or 'all'",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_data_source_file_does_not_exist(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
""",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError):
        load_config(str(config_file))
def test_load_config_accepts_data_source_wrap(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        wrap: items
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert "routes" in config


def test_load_config_raises_if_data_source_wrap_is_not_string(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        wrap: 123
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.wrap' in route #1 must be a string",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_not_found_status_is_not_integer(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: first
        where:
          column: id
          equals_path_param: user_id
        not_found_status: nope
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.not_found_status' in route #1 must be an integer",
    ):
        load_config(str(config_file))

def test_load_config_accepts_data_source_coerce_types(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        coerce_types: true
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert "routes" in config


def test_load_config_raises_if_data_source_coerce_types_is_not_boolean(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        coerce_types: nope
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.coerce_types' in route #1 must be a boolean",
    ):
        load_config(str(config_file))


def test_load_config_accepts_data_source_schema(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name,active\n1,Mario,true\n", encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        schema:
          id: int
          active: bool
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert "routes" in config


def test_load_config_raises_if_data_source_schema_type_is_invalid(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        schema:
          id: number
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.schema.id' in route #1 must be one of",
    ):
        load_config(str(config_file))

def test_load_config_accepts_json_data_source(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        '[{"id": 1, "name": "Mario"}]',
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
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
        encoding="utf-8",
    )

    config = load_config(str(config_file))
    assert "routes" in config


def test_load_config_raises_if_json_data_source_where_field_is_missing(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        '[{"id": 1, "name": "Mario"}]',
        encoding="utf-8",
    )

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
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
          equals_path_param: user_id
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.where.field' in route #1 is required",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_schema_is_used_with_json_data_source(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        '[{"id": 1, "name": "Mario"}]',
        encoding="utf-8",
    )

    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        schema:
          id: int
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.schema' in route #1 is only supported for 'csv' data sources",
    ):
        load_config(str(config_file))


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


def write_json_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    json_file = data_dir / "users.json"
    json_file.write_text('[{"id": 1, "name": "Mario"}]', encoding="utf-8")

    return json_file


MUTABLE_DATA_SOURCE = """
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
"""


def test_load_config_raises_if_status_code_is_not_an_integer(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      status_code: "abc"
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.status_code' in route #1 must be an integer",
    ):
        load_config(config_path)


def test_load_config_raises_if_status_code_is_empty(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      status_code:
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.status_code' in route #1 must be an integer",
    ):
        load_config(config_path)


def test_load_config_raises_if_status_code_is_out_of_range(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      status_code: 999
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.status_code' in route #1 must be a valid HTTP status code",
    ):
        load_config(config_path)


def test_load_config_accepts_a_valid_status_code(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      status_code: 204
      body:
        ok: true
""",
    )

    config = load_config(config_path)

    assert config["routes"][0]["response"]["status_code"] == 204


def test_load_config_raises_if_delay_ms_is_empty(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      delay_ms:
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.delay_ms' in route #1 must be an integer",
    ):
        load_config(config_path)


def test_load_config_raises_if_method_is_not_a_known_http_method(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: FETCH
    path: /x
    response:
      body:
        ok: true
""",
    )

    with pytest.raises(ValueError, match="'method' in route #1 must be one of"):
        load_config(config_path)


def test_load_config_raises_if_path_does_not_start_with_a_slash(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: users
    response:
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'path' in route #1 must be a string starting with '/'",
    ):
        load_config(config_path)


def test_load_config_raises_if_json_file_escapes_the_config_directory(tmp_path):
    outside_file = tmp_path.parent / "outside.json"
    outside_file.write_text('[{"id": 1}]', encoding="utf-8")

    config_dir = tmp_path / "mocks"
    config_dir.mkdir()

    config_file = config_dir / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /leak
    response:
      data_source:
        type: json
        file: ../../outside.json
        mode: all
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="JSON file must stay inside the configuration directory",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_body_from_escapes_the_config_directory(tmp_path):
    outside_file = tmp_path.parent / "outside_body.json"
    outside_file.write_text('{"ok": true}', encoding="utf-8")

    config_dir = tmp_path / "mocks"
    config_dir.mkdir()

    config_file = config_dir / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /leak
    response:
      body_from: ../../outside_body.json
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="JSON file must stay inside the configuration directory",
    ):
        load_config(str(config_file))


def test_load_config_raises_if_mutable_data_source_has_no_resource_name(tmp_path):
    write_json_data(tmp_path)

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
        mutable: true
        key_field: id
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.resource_name' in route #1 is required when mutable is true",
    ):
        load_config(config_path)


def test_load_config_raises_if_mutable_data_source_has_no_key_field(tmp_path):
    write_json_data(tmp_path)

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
        mutable: true
        resource_name: users
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.key_field' in route #1 is required when mutable is true",
    ):
        load_config(config_path)


def test_load_config_raises_if_mutable_route_uses_an_unsupported_method(tmp_path):
    write_json_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: HEAD
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        mutable: true
        key_field: id
        resource_name: users
""",
    )

    with pytest.raises(
        ValueError,
        match="'method' in route #1 must be one of: .* when mutable is true",
    ):
        load_config(config_path)


def test_load_config_raises_if_mutable_delete_has_no_where(tmp_path):
    write_json_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: DELETE
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.where' in route #1 is required for DELETE",
    ):
        load_config(config_path)


def test_load_config_allows_a_mutable_write_route_without_mode(tmp_path):
    write_json_data(tmp_path)

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: POST
    path: /users
    response:
      status_code: 201
      data_source:
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
""",
    )

    config = load_config(config_path)

    assert "mode" not in config["routes"][0]["response"]["data_source"]


def test_load_config_still_requires_mode_on_a_read_route(tmp_path):
    write_json_data(tmp_path)

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
        mutable: true
        key_field: id
        resource_name: users
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.data_source.mode' in route #1 must be 'first' or 'all'",
    ):
        load_config(config_path)


# --------------------------------------------------- version and unknown keys


def test_a_config_declaring_version_1_loads(tmp_path):
    config_path = write_config(
        tmp_path,
        """
version: 1
routes:
  - method: GET
    path: /x
    response:
      body:
        ok: true
""",
    )

    assert load_config(config_path)["version"] == 1


def test_a_config_declaring_an_unsupported_version_is_rejected(tmp_path):
    config_path = write_config(
        tmp_path,
        """
version: 2
routes:
  - method: GET
    path: /x
    response:
      body:
        ok: true
""",
    )

    with pytest.raises(ValueError, match="'version' must be 1"):
        load_config(config_path)


def test_an_unknown_top_level_key_is_rejected(tmp_path):
    config_path = write_config(
        tmp_path,
        """
rotues:
  - method: GET
    path: /x
routes:
  - method: GET
    path: /x
    response:
      body:
        ok: true
""",
    )

    with pytest.raises(ValueError, match="'rotues' is not a known configuration key"):
        load_config(config_path)


def test_an_unknown_response_key_is_rejected(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      stauts_code: 201
      body:
        ok: true
""",
    )

    with pytest.raises(
        ValueError,
        match="'response.stauts_code' in route #1 is not a known configuration key",
    ):
        load_config(config_path)


def test_an_error_in_a_sequence_names_the_entry_that_caused_it(tmp_path):
    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    responses:
      - body:
          ok: true
      - status_code: 99
        body:
          ok: false
""",
    )

    with pytest.raises(
        ValueError,
        match="'responses.1.status_code' in route #1 must be a valid HTTP status code",
    ):
        load_config(config_path)


# ------------------------------------------------- json data source contents


def test_a_json_data_source_whose_root_is_an_object_is_rejected(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text('{"users": [{"id": 1}]}', encoding="utf-8")

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

    with pytest.raises(
        ValueError,
        match="'response.data_source.file' in route #1: JSON data source must "
        "contain a root list",
    ):
        load_config(config_path)


def test_a_json_data_source_holding_a_non_object_row_is_rejected(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text('[{"id": 1}, "Mario"]', encoding="utf-8")

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

    with pytest.raises(ValueError, match="item #2 must be an object"):
        load_config(config_path)


def test_a_body_from_file_may_hold_any_json_value(tmp_path):
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()
    (responses_dir / "users.json").write_text(
        '{"users": [{"id": 1}]}', encoding="utf-8"
    )

    config_path = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /users
    response:
      body_from: ./responses/users.json
""",
    )

    assert load_config(config_path)["routes"][0]["path"] == "/users"
