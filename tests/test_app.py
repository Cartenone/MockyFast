import time

from fastapi.testclient import TestClient

from mockyfast.app import create_app


def test_create_app_serves_configured_route(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
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

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_create_app_returns_custom_status_code(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /not-found
    response:
      status_code: 404
      body:
        error: not_found
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


def test_create_app_loads_body_from_json_file(tmp_path):
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()

    json_file = responses_dir / "users.json"
    json_file.write_text(
        """
{
  "users": [
    { "id": 1, "name": "Mario" },
    { "id": 2, "name": "Luigi" }
  ]
}
""",
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users
    response:
      status_code: 200
      body_from: ./responses/users.json
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users")

    assert response.status_code == 200
    assert response.json() == {
        "users": [
            {"id": 1, "name": "Mario"},
            {"id": 2, "name": "Luigi"},
        ]
    }

def test_create_app_supports_path_params_in_body(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      status_code: 200
      body:
        id: "{user_id}"
        name: "User {user_id}"
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/123")

    assert response.status_code == 200
    assert response.json() == {
        "id": "123",
        "name": "User 123",
    }


def test_create_app_supports_path_params_in_body_from_json(tmp_path):
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()

    json_file = responses_dir / "user.json"
    json_file.write_text(
        """
{
  "id": "{user_id}",
  "message": "User {user_id} loaded"
}
""",
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      status_code: 200
      body_from: ./responses/user.json
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/42")

    assert response.status_code == 200
    assert response.json() == {
        "id": "42",
        "message": "User 42 loaded",
    }
def test_create_app_matches_route_by_query_params(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
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
        items:
          - id: 1
            status: shipped

  - method: GET
    path: /orders
    response:
      status_code: 200
      body:
        items: []
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/orders?status=shipped")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": 1, "status": "shipped"},
        ]
    }


def test_create_app_uses_fallback_route_when_query_does_not_match(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
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
        items:
          - id: 1
            status: shipped

  - method: GET
    path: /orders
    response:
      status_code: 200
      body:
        items: []
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/orders")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_app_returns_404_when_no_route_matches(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
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
        items:
          - id: 1
            status: shipped
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/orders")

    assert response.status_code == 404
    assert response.json() == {"detail": "No matching mock route found"}

def test_create_app_matches_route_by_headers(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /profile
    request:
      headers:
        Authorization: Bearer secret-token
    response:
      status_code: 200
      body:
        user: mario

  - method: GET
    path: /profile
    response:
      status_code: 401
      body:
        error: unauthorized
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/profile", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert response.json() == {"user": "mario"}


def test_create_app_uses_fallback_route_when_headers_do_not_match(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /profile
    request:
      headers:
        Authorization: Bearer secret-token
    response:
      status_code: 200
      body:
        user: mario

  - method: GET
    path: /profile
    response:
      status_code: 401
      body:
        error: unauthorized
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/profile")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_create_app_matches_headers_case_insensitively(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /profile
    request:
      headers:
        authorization: Bearer secret-token
    response:
      status_code: 200
      body:
        user: mario
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/profile", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert response.json() == {"user": "mario"}
def test_create_app_matches_route_by_json_body(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: POST
    path: /login
    request:
      json:
        username: admin
        password: secret
    response:
      status_code: 200
      body:
        token: fake-jwt-token

  - method: POST
    path: /login
    response:
      status_code: 401
      body:
        error: invalid_credentials
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.post(
        "/login",
        json={
            "username": "admin",
            "password": "secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"token": "fake-jwt-token"}


def test_create_app_uses_fallback_route_when_json_body_does_not_match(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: POST
    path: /login
    request:
      json:
        username: admin
        password: secret
    response:
      status_code: 200
      body:
        token: fake-jwt-token

  - method: POST
    path: /login
    response:
      status_code: 401
      body:
        error: invalid_credentials
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.post(
        "/login",
        json={
            "username": "admin",
            "password": "wrong",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_credentials"}


def test_create_app_returns_404_when_json_is_required_but_request_has_no_json(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: POST
    path: /login
    request:
      json:
        username: admin
    response:
      status_code: 200
      body:
        token: fake-jwt-token
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.post("/login", content="not-json")

    assert response.status_code == 404
    assert response.json() == {"detail": "No matching mock route found"}


def test_create_app_json_match_is_partial_for_dicts(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: POST
    path: /login
    request:
      json:
        username: admin
    response:
      status_code: 200
      body:
        token: fake-jwt-token
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.post(
        "/login",
        json={
            "username": "admin",
            "password": "secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"token": "fake-jwt-token"}

def test_create_app_applies_response_delay(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /slow
    response:
      status_code: 200
      delay_ms: 100
      body:
        ok: true
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    start = time.perf_counter()
    response = client.get("/slow")
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert elapsed >= 0.09

def test_create_app_returns_single_record_from_csv_by_path_param(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name,email\n1,Mario,mario@example.com\n2,Luigi,luigi@example.com\n",
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

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/2")

    assert response.status_code == 200
    assert response.json() == {
        "id": "2",
        "name": "Luigi",
        "email": "luigi@example.com",
    }


def test_create_app_returns_404_when_csv_first_mode_finds_nothing(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name\n1,Mario\n",
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

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


def test_create_app_returns_all_records_from_csv_by_query_param(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name,role\n1,Mario,admin\n2,Luigi,user\n3,Anna,user\n",
        encoding="utf-8",
    )

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
        where:
          column: role
          equals_query_param: role
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users?role=user")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "2", "name": "Luigi", "role": "user"},
        {"id": "3", "name": "Anna", "role": "user"},
    ]


def test_create_app_returns_all_csv_rows_without_filter(tmp_path):
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
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "1", "name": "Mario"},
        {"id": "2", "name": "Luigi"},
    ]

def test_create_app_wraps_all_mode_csv_response(tmp_path):
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

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": "1", "name": "Mario"},
            {"id": "2", "name": "Luigi"},
        ]
    }


def test_create_app_uses_custom_not_found_status_and_body_for_csv_first_mode(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name\n1,Mario\n",
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
        not_found_status: 422
        not_found_body:
          error: user_missing
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/999")

    assert response.status_code == 422
    assert response.json() == {"error": "user_missing"}

def test_create_app_coerces_csv_types_automatically(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name,active,balance\n1,Mario,true,12.5\n2,Luigi,false,7\n",
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
        coerce_types: true
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Mario",
        "active": True,
        "balance": 12.5,
    }


def test_create_app_applies_schema_mapping_to_csv_rows(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,name,active,balance\n1,Mario,true,12.5\n",
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
        schema:
          id: int
          active: bool
          balance: float
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Mario",
        "active": True,
        "balance": 12.5,
    }


def test_create_app_uses_schema_over_automatic_coercion(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text(
        "id,code\n1,001\n",
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
        coerce_types: true
        schema:
          code: str
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json() == {
        "id": "1",
        "code": "001",
    }

def test_create_app_returns_single_record_from_json_by_path_param(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        """
[
  { "id": 1, "name": "Mario", "role": "admin" },
  { "id": 2, "name": "Luigi", "role": "user" }
]
""",
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

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/2")

    assert response.status_code == 200
    assert response.json() == {
        "id": 2,
        "name": "Luigi",
        "role": "user",
    }


def test_create_app_returns_all_records_from_json_by_query_param(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        """
[
  { "id": 1, "name": "Mario", "role": "admin" },
  { "id": 2, "name": "Luigi", "role": "user" },
  { "id": 3, "name": "Anna", "role": "user" }
]
""",
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
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
        where:
          field: role
          equals_query_param: role
        wrap: items
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users?role=user")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": 2, "name": "Luigi", "role": "user"},
            {"id": 3, "name": "Anna", "role": "user"},
        ]
    }


def test_create_app_returns_custom_not_found_for_json_data_source(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        """
[
  { "id": 1, "name": "Mario" }
]
""",
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
        not_found_status: 404
        not_found_body:
          error: user_not_found
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    response = client.get("/users/999")

    assert response.status_code == 404
    assert response.json() == {"error": "user_not_found"}

def test_create_app_can_create_update_and_delete_mutable_json_resource(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        """
[
  { "id": 1, "name": "Mario" }
]
""",
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
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
        mutable: true
        key_field: id
        resource_name: users
        wrap: items

  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        mutable: true
        key_field: id
        resource_name: users
        where:
          field: id
          equals_path_param: user_id

  - method: POST
    path: /users
    response:
      status_code: 201
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        mutable: true
        key_field: id
        resource_name: users

  - method: PUT
    path: /users/{user_id}
    response:
      status_code: 200
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        mutable: true
        key_field: id
        resource_name: users
        where:
          field: id
          equals_path_param: user_id

  - method: DELETE
    path: /users/{user_id}
    response:
      status_code: 200
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        mutable: true
        key_field: id
        resource_name: users
        where:
          field: id
          equals_path_param: user_id
""",
        encoding="utf-8",
    )

    app = create_app(str(config_file))
    client = TestClient(app)

    create_response = client.post("/users", json={"id": 2, "name": "Luigi"})
    assert create_response.status_code == 201
    assert create_response.json() == {"id": 2, "name": "Luigi"}

    get_response = client.get("/users/2")
    assert get_response.status_code == 200
    assert get_response.json() == {"id": 2, "name": "Luigi"}

    update_response = client.put("/users/2", json={"name": "Luigi Updated"})
    assert update_response.status_code == 200
    assert update_response.json() == {"id": 2, "name": "Luigi Updated"}

    delete_response = client.delete("/users/2")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    missing_response = client.get("/users/2")
    assert missing_response.status_code == 404

MUTABLE_USERS_CONFIG = """
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
        resource_name: users

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

  - method: GET
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: first
        mutable: true
        key_field: id
        resource_name: users
        not_found_status: 404
        not_found_body:
          error: user_not_found
        where:
          field: id
          equals_path_param: user_id

  - method: PUT
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
        not_found_status: 404
        not_found_body:
          error: user_not_found
        where:
          field: id
          equals_path_param: user_id

  - method: PATCH
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
        where:
          field: id
          equals_path_param: user_id

  - method: DELETE
    path: /users/{user_id}
    response:
      data_source:
        type: json
        file: ./data/users.json
        mutable: true
        key_field: id
        resource_name: users
        not_found_status: 410
        not_found_body:
          error: already_gone
        where:
          field: id
          equals_path_param: user_id
"""


def build_mutable_client(tmp_path, config_body=MUTABLE_USERS_CONFIG):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    json_file = data_dir / "users.json"
    json_file.write_text(
        '[{"id": 1, "name": "Mario", "role": "admin"}]',
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(config_body, encoding="utf-8")

    return TestClient(create_app(str(config_file)), raise_server_exceptions=False)


def test_mutable_routes_share_one_store_across_paths(tmp_path):
    client = build_mutable_client(tmp_path)

    create_response = client.post("/users", json={"id": 2, "name": "Luigi"})
    assert create_response.status_code == 201

    detail_response = client.get("/users/2")

    assert detail_response.status_code == 200
    assert detail_response.json() == {"id": 2, "name": "Luigi"}


def test_mutable_route_applies_delay_ms(tmp_path):
    config_body = """
routes:
  - method: GET
    path: /users
    response:
      delay_ms: 300
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        mutable: true
        key_field: id
        resource_name: users
"""

    client = build_mutable_client(tmp_path, config_body)

    started_at = time.perf_counter()
    response = client.get("/users")
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert response.status_code == 200
    assert elapsed_ms >= 250


def test_data_source_not_found_response_applies_delay_ms(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_file = data_dir / "users.csv"
    csv_file.write_text("id,name\n1,Mario\n", encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      delay_ms: 300
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

    client = TestClient(create_app(str(config_file)))

    started_at = time.perf_counter()
    response = client.get("/users/999")
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert response.status_code == 404
    assert elapsed_ms >= 250


def test_mutable_create_rejects_a_malformed_json_body(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.post(
        "/users",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Request body must be valid JSON."}


def test_mutable_create_rejects_a_non_object_body(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.post("/users", json=[1, 2, 3])

    assert response.status_code == 400
    assert response.json() == {"detail": "Request body must be a JSON object."}
    assert client.get("/users").json() == [
        {"id": 1, "name": "Mario", "role": "admin"}
    ]


def test_mutable_create_requires_the_key_field(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.post("/users", json={"name": "Senza id"})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Request body must contain the key field 'id'."
    }


def test_mutable_create_rejects_a_duplicate_key(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.post("/users", json={"id": 1, "name": "Doppione"})

    assert response.status_code == 409
    assert response.json() == {"detail": "A resource with id=1 already exists."}


def test_mutable_patch_updates_a_resource(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.patch("/users/1", json={"name": "Mario Updated"})

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Mario Updated",
        "role": "admin",
    }


def test_mutable_update_rejects_a_changed_key_field(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.put("/users/1", json={"id": 42, "name": "Rinominato"})

    assert response.status_code == 400
    assert response.json() == {"detail": "The key field 'id' cannot be changed."}
    assert client.get("/users/1").status_code == 200


def test_mutable_update_accepts_the_unchanged_key_field(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.put("/users/1", json={"id": 1, "name": "Mario Updated"})

    assert response.status_code == 200
    assert response.json()["name"] == "Mario Updated"


def test_mutable_update_uses_the_configured_not_found_response(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.put("/users/999", json={"name": "Fantasma"})

    assert response.status_code == 404
    assert response.json() == {"error": "user_not_found"}


def test_mutable_delete_uses_the_configured_not_found_response(tmp_path):
    client = build_mutable_client(tmp_path)

    response = client.delete("/users/999")

    assert response.status_code == 410
    assert response.json() == {"error": "already_gone"}


def test_mutable_delete_removes_the_resource(tmp_path):
    client = build_mutable_client(tmp_path)

    assert client.delete("/users/1").status_code == 200
    assert client.get("/users").json() == []
    assert client.get("/users/1").status_code == 404


def test_mutable_csv_data_source_supports_crud(tmp_path):
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
        mutable: true
        key_field: id
        resource_name: users

  - method: POST
    path: /users
    response:
      status_code: 201
      data_source:
        type: csv
        file: ./data/users.csv
        mutable: true
        key_field: id
        resource_name: users
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(str(config_file)))

    create_response = client.post("/users", json={"id": "2", "name": "Luigi"})
    assert create_response.status_code == 201

    assert client.get("/users").json() == [
        {"id": "1", "name": "Mario"},
        {"id": "2", "name": "Luigi"},
    ]


def test_mutable_route_can_match_on_a_query_param(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    json_file = data_dir / "users.json"
    json_file.write_text(
        '[{"id": 1, "role": "admin"}, {"id": 2, "role": "user"}]',
        encoding="utf-8",
    )

    config_file = tmp_path / "mockyfast.yaml"
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
        mutable: true
        key_field: id
        resource_name: users
        where:
          field: role
          equals_query_param: role
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(str(config_file)))

    response = client.get("/users", params={"role": "admin"})

    assert response.status_code == 200
    assert response.json() == [{"id": 1, "role": "admin"}]


def test_mutable_seed_is_not_affected_by_later_file_changes(tmp_path):
    client = build_mutable_client(tmp_path)

    (tmp_path / "data" / "users.json").write_text(
        '[{"id": 7, "name": "Sostituito"}]',
        encoding="utf-8",
    )

    response = client.get("/users")

    assert response.json() == [{"id": 1, "name": "Mario", "role": "admin"}]
