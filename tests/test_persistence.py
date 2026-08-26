import json

import pytest
from fastapi.testclient import TestClient

from mockyfast.app import create_app
from mockyfast.config import load_config
from mockyfast.persistence import read_state, resolve_state_path, write_state

SEED = '[{"id": 1, "name": "Mario"}]'

PERSISTED_CONFIG = """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
    persist: true
"""

VOLATILE_CONFIG = """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
"""


def write_project(tmp_path, config_body=PERSISTED_CONFIG):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "users.json").write_text(SEED, encoding="utf-8")

    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(config_body, encoding="utf-8")

    return str(config_file)


def state_file(tmp_path):
    return tmp_path / ".mockyfast-state" / "users.json"


# ------------------------------------------------------------------ units


def test_persist_true_derives_a_state_path(tmp_path):
    config = tmp_path / "mockyfast.yaml"

    resolved = resolve_state_path(str(config), True, "users")

    assert resolved == tmp_path / ".mockyfast-state" / "users.json"


def test_an_explicit_state_path_is_used_as_given(tmp_path):
    config = tmp_path / "mockyfast.yaml"

    resolved = resolve_state_path(str(config), "./stato/utenti.json", "users")

    assert resolved == tmp_path / "stato" / "utenti.json"


def test_a_state_path_cannot_escape_the_config_directory(tmp_path):
    config = tmp_path / "mockyfast.yaml"

    with pytest.raises(ValueError, match="must stay inside the configuration"):
        resolve_state_path(str(config), "../fuori.json", "users")


def test_reading_a_missing_state_file_gives_nothing(tmp_path):
    assert read_state(tmp_path / "nope.json") is None


def test_reading_a_broken_state_file_gives_nothing(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{non json", encoding="utf-8")

    assert read_state(broken) is None


def test_reading_a_non_list_state_file_gives_nothing(tmp_path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"a": 1}', encoding="utf-8")

    assert read_state(wrong) is None


def test_writing_creates_the_parent_directory(tmp_path):
    target = tmp_path / "deep" / "nested" / "state.json"

    write_state(target, [{"id": 1}])

    assert json.loads(target.read_text(encoding="utf-8")) == [{"id": 1}]


def test_writing_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "state.json"

    write_state(target, [{"id": 1}])

    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


# ------------------------------------------------------------- served app


def test_writes_survive_a_restart(tmp_path):
    config = write_project(tmp_path)

    first = TestClient(create_app(config))
    first.post("/users", json={"id": 2, "name": "Luigi"})
    first.patch("/users/1", json={"name": "Mario Updated"})

    second = TestClient(create_app(config))

    assert second.get("/users").json() == [
        {"id": 1, "name": "Mario Updated"},
        {"id": 2, "name": "Luigi"},
    ]


def test_deletes_survive_a_restart(tmp_path):
    config = write_project(tmp_path)

    TestClient(create_app(config)).delete("/users/1")

    assert TestClient(create_app(config)).get("/users").json() == []


def test_the_seed_file_is_never_written_to(tmp_path):
    config = write_project(tmp_path)

    client = TestClient(create_app(config))
    client.post("/users", json={"id": 2, "name": "Luigi"})

    assert (tmp_path / "data" / "users.json").read_text(encoding="utf-8") == SEED


def test_the_state_file_is_written_at_startup(tmp_path):
    config = write_project(tmp_path)

    TestClient(create_app(config))

    assert json.loads(state_file(tmp_path).read_text(encoding="utf-8")) == [
        {"id": 1, "name": "Mario"}
    ]


def test_removing_the_state_file_returns_to_the_seed(tmp_path):
    config = write_project(tmp_path)

    client = TestClient(create_app(config))
    client.post("/users", json={"id": 2, "name": "Luigi"})

    state_file(tmp_path).unlink()

    assert TestClient(create_app(config)).get("/users").json() == [
        {"id": 1, "name": "Mario"}
    ]


def test_an_explicit_persist_path_is_honoured(tmp_path):
    config = write_project(
        tmp_path,
        """
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
    persist: ./stato/utenti.json
""",
    )

    TestClient(create_app(config)).post("/users", json={"id": 2, "name": "Luigi"})

    saved = json.loads((tmp_path / "stato" / "utenti.json").read_text(encoding="utf-8"))

    assert [row["name"] for row in saved] == ["Mario", "Luigi"]


def test_without_persist_nothing_survives_a_restart(tmp_path):
    config = write_project(tmp_path, VOLATILE_CONFIG)

    TestClient(create_app(config)).post("/users", json={"id": 2, "name": "Luigi"})

    assert TestClient(create_app(config)).get("/users").json() == [
        {"id": 1, "name": "Mario"}
    ]
    assert not (tmp_path / ".mockyfast-state").exists()


# --------------------------------------------------------------- validate


def test_persist_must_be_a_boolean_or_a_path(tmp_path):
    config = write_project(
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
        resource_name: users
        persist: 12
""",
    )

    with pytest.raises(ValueError, match="'response.data_source.persist'"):
        load_config(config)


def test_persist_requires_mutable(tmp_path):
    config = write_project(
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
        persist: true
""",
    )

    with pytest.raises(ValueError, match="needs 'mutable: true'"):
        load_config(config)
