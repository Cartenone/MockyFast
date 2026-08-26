import json

import pytest
from fastapi.testclient import TestClient

from mockyfast.app import create_app
from mockyfast.config import collect_warnings, load_config, load_config_source
from mockyfast.resources import build_config_from_data, detect_key_field, expand_resources

USERS_JSON = '[{"id": 1, "name": "Mario"}, {"id": 2, "name": "Luigi"}]'
PRODUCTS_CSV = "sku,title\nA1,Tastiera\nB2,Mouse\n"


def write_data(tmp_path, with_csv=False):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "users.json").write_text(USERS_JSON, encoding="utf-8")

    if with_csv:
        (data_dir / "products.csv").write_text(PRODUCTS_CSV, encoding="utf-8")

    return data_dir


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


RESOURCE_CONFIG = """
resources:
  - name: users
    path: /users
    source:
      type: json
      file: ./data/users.json
    key_field: id
"""


# --------------------------------------------------------------- expansion


def test_resource_expands_to_the_full_crud_route_set(tmp_path):
    write_data(tmp_path)

    config = load_config(write_config(tmp_path, RESOURCE_CONFIG))
    generated = [(route["method"], route["path"]) for route in config["routes"]]

    assert generated == [
        ("GET", "/users"),
        ("GET", "/users/{id}"),
        ("POST", "/users"),
        ("PUT", "/users/{id}"),
        ("PATCH", "/users/{id}"),
        ("DELETE", "/users/{id}"),
    ]


def test_expanded_routes_share_one_resource_name(tmp_path):
    write_data(tmp_path)

    config = load_config(write_config(tmp_path, RESOURCE_CONFIG))

    for route in config["routes"]:
        data_source = route["response"]["data_source"]
        assert data_source["resource_name"] == "users"
        assert data_source["mutable"] is True
        assert data_source["key_field"] == "id"


def test_resource_methods_can_be_restricted(tmp_path):
    write_data(tmp_path)

    config = load_config(
        write_config(
            tmp_path,
            """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
    methods: [list, get]
""",
        )
    )

    assert [(r["method"], r["path"]) for r in config["routes"]] == [
        ("GET", "/users"),
        ("GET", "/users/{id}"),
    ]


def test_resource_path_defaults_to_the_name(tmp_path):
    write_data(tmp_path)

    config = load_config(
        write_config(
            tmp_path,
            """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
        )
    )

    assert config["routes"][0]["path"] == "/users"


def test_declared_routes_keep_priority_over_generated_ones(tmp_path):
    write_data(tmp_path)

    config = load_config(
        write_config(
            tmp_path,
            """
routes:
  - method: GET
    path: /users/me
    response:
      body:
        who: me

resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
""",
        )
    )

    assert config["routes"][0]["path"] == "/users/me"


def test_csv_resource_uses_column_in_where(tmp_path):
    write_data(tmp_path, with_csv=True)

    config = load_config(
        write_config(
            tmp_path,
            """
resources:
  - name: products
    source:
      type: csv
      file: ./data/products.csv
    key_field: sku
""",
        )
    )

    detail_route = config["routes"][1]

    assert detail_route["path"] == "/products/{sku}"
    assert detail_route["response"]["data_source"]["where"] == {
        "column": "sku",
        "equals_path_param": "sku",
    }


def test_resource_applies_wrap_only_to_the_list_route(tmp_path):
    write_data(tmp_path)

    config = load_config(
        write_config(
            tmp_path,
            RESOURCE_CONFIG.rstrip() + "\n    wrap: items\n",
        )
    )

    assert config["routes"][0]["response"]["data_source"]["wrap"] == "items"
    assert "wrap" not in config["routes"][1]["response"]["data_source"]


def test_create_route_gets_a_201_status(tmp_path):
    write_data(tmp_path)

    config = load_config(write_config(tmp_path, RESOURCE_CONFIG))
    create_route = next(r for r in config["routes"] if r["method"] == "POST")

    assert create_route["response"]["status_code"] == 201


# --------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "body, message",
    [
        ("resources: {}", "'resources' must be a list"),
        ("resources:\n  - source: {type: json, file: ./data/users.json}", "'name' in resource #1"),
        ("resources:\n  - name: users", "'source' in resource #1 must be an object"),
        (
            "resources:\n  - name: users\n    source: {type: xml, file: ./data/users.json}",
            "'source.type' in resource #1",
        ),
        (
            "resources:\n  - name: users\n    source: {type: json, file: ./data/users.json}\n"
            "    methods: [list, explode]",
            "'methods' in resource #1 must only contain",
        ),
        (
            "resources:\n  - name: users\n    path: users\n"
            "    source: {type: json, file: ./data/users.json}",
            "'path' in resource #1 must be a string starting with '/'",
        ),
    ],
)
def test_invalid_resource_is_rejected(tmp_path, body, message):
    write_data(tmp_path)

    with pytest.raises(ValueError, match=message):
        load_config(write_config(tmp_path, body))


def test_config_without_routes_or_resources_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Missing 'routes' or 'resources' key"):
        load_config(write_config(tmp_path, "name: example\n"))


def test_expand_resources_is_a_no_op_without_resources():
    config = {"routes": [{"method": "GET", "path": "/x", "response": {}}]}

    assert expand_resources(config) == config


# --------------------------------------------------------------- served app


def test_resource_config_serves_full_crud(tmp_path):
    write_data(tmp_path)

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))

    assert client.get("/users").json() == json.loads(USERS_JSON)

    assert client.post("/users", json={"id": 3, "name": "Anna"}).status_code == 201
    assert client.get("/users/3").json() == {"id": 3, "name": "Anna"}
    assert client.patch("/users/3", json={"name": "Anna B"}).json()["name"] == "Anna B"
    assert client.delete("/users/3").status_code == 200
    assert client.get("/users/3").status_code == 404


def test_resource_not_found_body_reaches_the_detail_route(tmp_path):
    write_data(tmp_path)

    client = TestClient(
        create_app(
            write_config(
                tmp_path,
                RESOURCE_CONFIG.rstrip() + "\n    not_found_body:\n      error: nope\n",
            )
        )
    )

    response = client.get("/users/999")

    assert response.status_code == 404
    assert response.json() == {"error": "nope"}


# --------------------------------------------------------------- zero config


def test_data_folder_becomes_a_config(tmp_path):
    data_dir = write_data(tmp_path, with_csv=True)

    config, base_path = build_config_from_data(data_dir)

    assert base_path == data_dir.resolve()
    assert [resource["name"] for resource in config["resources"]] == [
        "products",
        "users",
    ]


def test_single_data_file_becomes_a_config(tmp_path):
    data_dir = write_data(tmp_path)

    config, base_path = build_config_from_data(data_dir / "users.json")

    assert base_path == data_dir.resolve()
    assert len(config["resources"]) == 1
    assert config["resources"][0]["name"] == "users"


def test_key_field_falls_back_to_the_first_column(tmp_path):
    data_dir = write_data(tmp_path, with_csv=True)

    assert detect_key_field(data_dir / "products.csv", "csv") == "sku"
    assert detect_key_field(data_dir / "users.json", "json") == "id"


def test_serving_a_data_folder_needs_no_yaml(tmp_path):
    data_dir = write_data(tmp_path, with_csv=True)

    client = TestClient(create_app(str(data_dir)))

    assert client.get("/users").json() == json.loads(USERS_JSON)
    assert client.get("/products/A1").json() == {"sku": "A1", "title": "Tastiera"}

    created = client.post("/users", json={"id": 9, "name": "Nuovo"})
    assert created.status_code == 201
    assert client.get("/users/9").json() == {"id": 9, "name": "Nuovo"}


def test_empty_data_folder_is_rejected(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(ValueError, match="No .json or .csv data file found"):
        load_config_source(str(empty_dir))


# --------------------------------------------------------------- index route


def test_index_route_lists_the_served_routes(tmp_path):
    write_data(tmp_path)

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))
    payload = client.get("/").json()

    assert len(payload["routes"]) == 6
    assert payload["routes"][0] == {
        "method": "GET",
        "path": "/users",
        # The file name only: the index must not publish the directory layout.
        "source": "users.json",
        "mutable": True,
        "resource": "users",
    }


def test_index_route_renders_html_for_a_browser(tmp_path):
    write_data(tmp_path)

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))
    response = client.get("/", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/users/{id}" in response.text


def test_index_route_can_be_disabled(tmp_path):
    write_data(tmp_path)

    client = TestClient(
        create_app(write_config(tmp_path, RESOURCE_CONFIG), with_index=False),
        raise_server_exceptions=False,
    )

    assert client.get("/").status_code == 404


def test_declared_root_route_wins_over_the_index(tmp_path):
    client = TestClient(
        create_app(
            write_config(
                tmp_path,
                """
routes:
  - method: GET
    path: /
    response:
      body:
        mine: true
""",
            )
        )
    )

    assert client.get("/").json() == {"mine": True}


# --------------------------------------------------------------- warnings


def test_shadowed_route_is_reported_as_a_warning(tmp_path):
    config = load_config(
        write_config(
            tmp_path,
            """
routes:
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
        )
    )

    warnings = collect_warnings(config)

    assert len(warnings) == 1
    assert "/users/me is unreachable" in warnings[0]


def test_specific_route_declared_first_raises_no_warning(tmp_path):
    config = load_config(
        write_config(
            tmp_path,
            """
routes:
  - method: GET
    path: /users/me
    response:
      body:
        static: true

  - method: GET
    path: /users/{user_id}
    response:
      body:
        dynamic: true
""",
        )
    )

    assert collect_warnings(config) == []


def test_duplicate_paths_for_request_matching_raise_no_warning(tmp_path):
    config = load_config(
        write_config(
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

  - method: GET
    path: /orders
    response:
      body:
        items: []
""",
        )
    )

    assert collect_warnings(config) == []


def test_different_methods_do_not_shadow_each_other(tmp_path):
    write_data(tmp_path)

    config = load_config(
        write_config(
            tmp_path,
            """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      body:
        dynamic: true

  - method: POST
    path: /users/me
    response:
      body:
        static: true
""",
        )
    )

    assert collect_warnings(config) == []


# ------------------------------------------------------- audit regressions


def test_duplicate_resource_names_are_rejected(tmp_path):
    write_data(tmp_path)

    with pytest.raises(ValueError, match="reuses the name 'users'"):
        load_config(
            write_config(
                tmp_path,
                """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json

  - name: users
    path: /people
    source:
      type: json
      file: ./data/users.json
""",
            )
        )


def test_data_files_colliding_on_a_name_are_rejected(tmp_path):
    data_dir = write_data(tmp_path)
    (data_dir / "users.csv").write_text("id,name\n1,Mario\n", encoding="utf-8")

    with pytest.raises(ValueError, match="would both become the 'users' resource"):
        build_config_from_data(data_dir)


def test_seed_reads_each_data_file_once(tmp_path, monkeypatch):
    write_data(tmp_path)

    import mockyfast.app as app_module

    reads = []
    original = app_module.load_json_rows

    def counting(config_path, relative_path):
        reads.append(relative_path)
        return original(config_path, relative_path)

    monkeypatch.setattr(app_module, "load_json_rows", counting)

    # Six routes share one store, so the file must still be read only once.
    create_app(write_config(tmp_path, RESOURCE_CONFIG))

    assert len(reads) == 1


def test_put_replaces_the_resource(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(
        '[{"id": 1, "name": "Mario", "role": "admin"}]', encoding="utf-8"
    )

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))

    response = client.put("/users/1", json={"name": "Solo nome"})

    assert response.status_code == 200
    # 'role' is gone: PUT replaces, and the key field survives.
    assert response.json() == {"id": 1, "name": "Solo nome"}


def test_patch_merges_into_the_resource(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(
        '[{"id": 1, "name": "Mario", "role": "admin"}]', encoding="utf-8"
    )

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))

    response = client.patch("/users/1", json={"name": "Mario B"})

    assert response.json() == {"id": 1, "name": "Mario B", "role": "admin"}


def test_cors_headers_let_a_browser_app_call_the_mock(tmp_path):
    write_data(tmp_path)

    client = TestClient(create_app(write_config(tmp_path, RESOURCE_CONFIG)))

    preflight = client.options(
        "/users",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"

    simple = client.get("/users", headers={"Origin": "http://localhost:3000"})
    assert simple.headers["access-control-allow-origin"] == "*"


def test_cors_can_be_disabled(tmp_path):
    write_data(tmp_path)

    client = TestClient(
        create_app(write_config(tmp_path, RESOURCE_CONFIG), with_cors=False),
        raise_server_exceptions=False,
    )

    simple = client.get("/users", headers={"Origin": "http://localhost:3000"})

    assert "access-control-allow-origin" not in simple.headers
