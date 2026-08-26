import json

import pytest
from fastapi.testclient import TestClient

from mockyfast.app import create_app
from mockyfast.config import load_config
from mockyfast.listing import apply_list_query, sort_key

USERS = [
    {"id": 1, "name": "Mario", "role": "admin", "age": 40},
    {"id": 2, "name": "Luigi", "role": "user", "age": 35},
    {"id": 3, "name": "Anna", "role": "user", "age": 28},
    {"id": 4, "name": "Bruno", "role": "user", "age": 51},
    {"id": 5, "name": "Carla", "role": "admin", "age": 33},
]

RESOURCE_CONFIG = """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
"""


def build_client(tmp_path, config_body=RESOURCE_CONFIG):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "users.json").write_text(json.dumps(USERS), encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(config_body, encoding="utf-8")

    return TestClient(create_app(str(config_file)))


def names(response):
    return [row["name"] for row in response.json()]


# ------------------------------------------------------------------ units


def test_numbers_sort_before_text():
    assert sort_key(2) < sort_key("a")
    assert sort_key(2) < sort_key(10)


def test_none_sorts_with_text():
    assert sort_key(None) > sort_key(0)


def test_apply_list_query_reports_the_total_before_paging():
    rows, total = apply_list_query(USERS, {"_limit": "2"}, set())

    assert len(rows) == 2
    assert total == 5


def test_a_param_consumed_by_where_is_not_a_field_filter():
    rows, _ = apply_list_query(USERS, {"role": "admin"}, {"role"})

    assert len(rows) == 5


# --------------------------------------------------------------- filtering


def test_field_filter_narrows_the_list(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"role": "user"})

    assert names(response) == ["Luigi", "Anna", "Bruno"]
    assert response.headers["x-total-count"] == "3"


def test_several_field_filters_combine(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"role": "user", "age": "35"})

    assert names(response) == ["Luigi"]


def test_a_filter_matching_nothing_gives_an_empty_list(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"role": "nessuno"})

    assert response.json() == []
    assert response.headers["x-total-count"] == "0"


def test_an_unknown_field_filters_everything_out(tmp_path):
    client = build_client(tmp_path)

    assert client.get("/users", params={"nope": "x"}).json() == []


# ----------------------------------------------------------------- sorting


def test_sorting_is_ascending_by_default(tmp_path):
    client = build_client(tmp_path)

    assert names(client.get("/users", params={"_sort": "age"})) == [
        "Anna",
        "Carla",
        "Luigi",
        "Mario",
        "Bruno",
    ]


def test_sorting_can_be_reversed(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"_sort": "age", "_order": "desc"})

    assert names(response)[0] == "Bruno"


def test_sorting_accepts_several_fields(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"_sort": "role,age"})

    assert names(response) == ["Carla", "Mario", "Anna", "Luigi", "Bruno"]


def test_sorting_by_an_unknown_field_keeps_the_order(tmp_path):
    client = build_client(tmp_path)

    assert names(client.get("/users", params={"_sort": "nope"})) == [
        row["name"] for row in USERS
    ]


# -------------------------------------------------------------- pagination


def test_limit_takes_the_first_rows(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/users", params={"_limit": "2"})

    assert names(response) == ["Mario", "Luigi"]
    assert response.headers["x-total-count"] == "5"


def test_page_is_one_based(tmp_path):
    client = build_client(tmp_path)

    assert names(client.get("/users", params={"_limit": "2", "_page": "2"})) == [
        "Anna",
        "Bruno",
    ]


def test_offset_skips_rows(tmp_path):
    client = build_client(tmp_path)

    assert names(client.get("/users", params={"_limit": "2", "_offset": "3"})) == [
        "Bruno",
        "Carla",
    ]


def test_offset_without_limit_runs_to_the_end(tmp_path):
    client = build_client(tmp_path)

    assert names(client.get("/users", params={"_offset": "3"})) == ["Bruno", "Carla"]


@pytest.mark.parametrize("value", ["abc", "-1", ""])
def test_an_unusable_limit_is_ignored(tmp_path, value):
    client = build_client(tmp_path)

    assert len(client.get("/users", params={"_limit": value}).json()) == 5


def test_filter_sort_and_page_combine(tmp_path):
    client = build_client(tmp_path)

    response = client.get(
        "/users", params={"role": "user", "_sort": "age", "_limit": "2"}
    )

    assert names(response) == ["Anna", "Luigi"]
    assert response.headers["x-total-count"] == "3"


# ------------------------------------------------------------------ wiring


def test_a_created_row_is_immediately_filterable(tmp_path):
    client = build_client(tmp_path)

    client.post("/users", json={"id": 6, "name": "Dino", "role": "admin", "age": 22})

    response = client.get("/users", params={"role": "admin", "_sort": "age"})

    assert names(response) == ["Dino", "Carla", "Mario"]


def test_wrap_still_applies_around_the_page(tmp_path):
    client = build_client(tmp_path, RESOURCE_CONFIG.rstrip() + "\n    wrap: items\n")

    payload = client.get("/users", params={"_limit": "2"}).json()

    assert list(payload) == ["items"]
    assert len(payload["items"]) == 2


def test_an_explicit_route_does_not_get_list_query_for_free(tmp_path):
    config = """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
"""

    client = build_client(tmp_path, config)
    response = client.get("/users", params={"role": "admin", "_limit": "1"})

    assert len(response.json()) == 5
    assert "x-total-count" not in response.headers


def test_an_explicit_route_can_opt_in(tmp_path):
    config = """
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: json
        file: ./data/users.json
        mode: all
        list_query: true
"""

    client = build_client(tmp_path, config)

    assert len(client.get("/users", params={"_limit": "1"}).json()) == 1


def test_a_resource_can_opt_out(tmp_path):
    client = build_client(
        tmp_path, RESOURCE_CONFIG.rstrip() + "\n    list_query: false\n"
    )

    assert len(client.get("/users", params={"_limit": "1"}).json()) == 5


def test_list_query_must_be_a_boolean(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(json.dumps(USERS), encoding="utf-8")

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
        list_query: "si"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="'response.data_source.list_query'"):
        load_config(str(config_file))
