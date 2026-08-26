import pytest
from typer.testing import CliRunner

from mockyfast.cli import app
from mockyfast.config import load_config
from mockyfast.explain import explain_request, match_path, split_target

runner = CliRunner()

CONFIG = """
routes:
  - method: GET
    path: /users
    response:
      body:
        all: true

  - method: GET
    path: /users/{user_id}
    response:
      body:
        id: "{user_id}"

  - method: GET
    path: /users/me
    response:
      body:
        me: true

  - method: POST
    path: /login
    request:
      json:
        username: admin
        password: secret
    response:
      body:
        token: ok

  - method: POST
    path: /login
    response:
      status_code: 401
      body:
        error: no

  - method: GET
    path: /orders
    request:
      headers:
        Authorization: { matches: '^Bearer .+' }
      query:
        status: shipped
    response:
      body:
        orders: []
"""


@pytest.fixture
def config(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(CONFIG, encoding="utf-8")
    return load_config(str(config_file))


@pytest.fixture
def config_path(tmp_path):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(CONFIG, encoding="utf-8")
    return str(config_file)


def winner(verdicts):
    return next((v for v in verdicts if v.matched and not v.shadowed), None)


# ------------------------------------------------------------------ units


@pytest.mark.parametrize(
    "target, path, query",
    [
        ("/users", "/users", {}),
        ("/users?role=admin", "/users", {"role": "admin"}),
        ("/users?a=1&b=2", "/users", {"a": "1", "b": "2"}),
        ("/", "/", {}),
    ],
)
def test_split_target(target, path, query):
    assert split_target(target) == (path, query)


def test_match_path_binds_parameters():
    assert match_path("/users/{user_id}", "/users/7") == (True, {"user_id": "7"})


def test_match_path_rejects_a_different_depth():
    assert match_path("/users/{id}", "/users/7/orders")[0] is False


def test_match_path_rejects_a_different_literal():
    assert match_path("/users/{id}", "/orders/7")[0] is False


# ------------------------------------------------------------- resolution


def test_a_dynamic_route_shadows_a_later_static_one(config):
    verdicts = explain_request(config, "GET", "/users/me")

    assert winner(verdicts).index == 2
    assert verdicts[2].shadowed is True
    assert "answers first" in verdicts[2].reason


def test_the_matching_route_reports_its_path_params(config):
    assert winner(explain_request(config, "GET", "/users/7")).path_params == {
        "user_id": "7"
    }


def test_a_wrong_method_is_reported(config):
    verdicts = explain_request(config, "DELETE", "/users/7")

    assert winner(verdicts) is None
    assert verdicts[0].reason == "method is GET"


def test_the_failing_body_field_is_named(config):
    verdicts = explain_request(
        config,
        "POST",
        "/login",
        body={"username": "admin", "password": "wrong"},
    )

    assert verdicts[3].reason == "body field 'password' does not match"
    assert winner(verdicts).index == 5


def test_a_matching_body_reaches_the_first_route(config):
    verdicts = explain_request(
        config,
        "POST",
        "/login",
        body={"username": "admin", "password": "secret"},
    )

    assert winner(verdicts).index == 4


def test_a_route_matching_on_a_body_needs_one(config):
    verdicts = explain_request(config, "POST", "/login")

    assert "none was given" in verdicts[3].reason


def test_the_failing_query_param_is_named(config):
    verdicts = explain_request(
        config,
        "GET",
        "/orders?status=pending",
        headers={"Authorization": "Bearer abc"},
    )

    assert verdicts[5].reason == "query param 'status' does not match"


def test_the_failing_header_is_named(config):
    verdicts = explain_request(config, "GET", "/orders?status=shipped")

    assert verdicts[5].reason == "header 'Authorization' does not match"


def test_everything_matching_wins(config):
    verdicts = explain_request(
        config,
        "GET",
        "/orders?status=shipped",
        headers={"Authorization": "Bearer abc"},
    )

    assert winner(verdicts).index == 6


# ------------------------------------------------------------------- cli


def test_explain_names_the_answering_route(config_path):
    result = runner.invoke(app, ["explain", config_path, "GET", "/users/me"])

    assert result.exit_code == 0
    assert "Answered by route #2" in result.output
    assert "user_id=me" in result.output
    assert "an earlier route answers first" in result.output


def test_explain_exits_non_zero_when_nothing_matches(config_path):
    result = runner.invoke(app, ["explain", config_path, "DELETE", "/users/1"])

    assert result.exit_code == 1
    assert "would return 404" in result.output


def test_explain_accepts_headers(config_path):
    result = runner.invoke(
        app,
        [
            "explain",
            config_path,
            "GET",
            "/orders?status=shipped",
            "-H",
            "Authorization: Bearer abc",
        ],
    )

    assert result.exit_code == 0
    assert "Answered by route #6" in result.output


def test_explain_rejects_a_malformed_header(config_path):
    result = runner.invoke(
        app, ["explain", config_path, "GET", "/users", "-H", "nocolon"]
    )

    assert result.exit_code != 0


def test_explain_rejects_a_malformed_body(config_path):
    result = runner.invoke(
        app, ["explain", config_path, "POST", "/login", "--body", "{nope"]
    )

    assert result.exit_code == 1
    assert "--body must be valid JSON" in result.output
