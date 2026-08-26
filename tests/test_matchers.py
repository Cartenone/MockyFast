import pytest
from fastapi.testclient import TestClient

from mockyfast.app import create_app, headers_matches, json_matches, query_matches
from mockyfast.config import load_config
from mockyfast.matchers import is_matcher


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


# ------------------------------------------------------ matcher detection


def test_an_object_of_operators_is_a_matcher():
    assert is_matcher({"matches": "^a"})
    assert is_matcher({"gte": 1, "lte": 5})


def test_a_plain_object_is_not_a_matcher():
    assert not is_matcher({"name": "Mario"})
    assert not is_matcher({})
    assert not is_matcher({"matches": "^a", "name": "Mario"})
    assert not is_matcher("matches")


# --------------------------------------------------------- query matching


@pytest.mark.parametrize(
    "expected, actual, result",
    [
        ({"status": "shipped"}, {"status": "shipped"}, True),
        ({"status": "shipped"}, {"status": "pending"}, False),
        ({"status": "shipped"}, {}, False),
        ({"page": {"one_of": ["1", "2"]}}, {"page": "2"}, True),
        ({"page": {"one_of": ["1", "2"]}}, {"page": "9"}, False),
        ({"q": {"contains": "mar"}}, {"q": "mario"}, True),
        ({"q": {"contains": "mar"}}, {"q": "luigi"}, False),
        ({"q": {"matches": "^ma"}}, {"q": "mario"}, True),
        ({"n": {"gte": 5}}, {"n": "7"}, True),
        ({"n": {"gte": 5}}, {"n": "3"}, False),
        ({"n": {"gte": 5}}, {"n": "abc"}, False),
        ({"debug": {"present": True}}, {"debug": ""}, True),
        ({"debug": {"present": True}}, {}, False),
        ({"debug": {"absent": True}}, {}, True),
        ({"debug": {"absent": True}}, {"debug": "1"}, False),
        ({"n": {"gt": 1, "lt": 10}}, {"n": "5"}, True),
        ({"n": {"gt": 1, "lt": 10}}, {"n": "50"}, False),
    ],
)
def test_query_matching(expected, actual, result):
    assert query_matches(expected, actual) is result


def test_query_numbers_compare_as_strings_by_default():
    assert query_matches({"page": 2}, {"page": "2"}) is True


# -------------------------------------------------------- header matching


def test_header_matching_ignores_case_on_both_sides():
    assert headers_matches({"authorization": "Bearer x"}, {"Authorization": "Bearer x"})


def test_header_matcher_uses_a_regex():
    expected = {"Authorization": {"matches": "^Bearer .{4,}$"}}

    assert headers_matches(expected, {"Authorization": "Bearer abcd"}) is True
    assert headers_matches(expected, {"Authorization": "Bearer ab"}) is False
    assert headers_matches(expected, {}) is False


def test_header_absent_matcher():
    expected = {"X-Debug": {"absent": True}}

    assert headers_matches(expected, {}) is True
    assert headers_matches(expected, {"X-Debug": "1"}) is False


# ---------------------------------------------------------- json matching


def test_json_matcher_applies_to_a_leaf():
    expected = {"email": {"matches": "@"}}

    assert json_matches(expected, {"email": "m@x.it"}) is True
    assert json_matches(expected, {"email": "nope"}) is False


def test_json_matcher_reaches_nested_objects():
    expected = {"user": {"age": {"gte": 18}}}

    assert json_matches(expected, {"user": {"age": 30}}) is True
    assert json_matches(expected, {"user": {"age": 12}}) is False


def test_json_nested_object_stays_a_structural_comparison():
    assert json_matches({"user": {"name": "Mario"}}, {"user": {"name": "Mario"}})
    assert not json_matches({"user": {"name": "Mario"}}, {"user": {"name": "Luigi"}})


def test_json_absent_matcher_wants_the_key_gone():
    expected = {"referral": {"absent": True}}

    assert json_matches(expected, {"email": "m@x.it"}) is True
    assert json_matches(expected, {"referral": "x"}) is False


def test_json_comparison_does_not_stringify():
    assert json_matches({"n": {"equals": 5}}, {"n": 5}) is True
    assert json_matches({"n": {"equals": 5}}, {"n": "5"}) is False


def test_json_contains_works_on_lists():
    assert json_matches({"tags": {"contains": "a"}}, {"tags": ["a", "b"]}) is True
    assert json_matches({"tags": {"contains": "z"}}, {"tags": ["a", "b"]}) is False


def test_json_lists_still_need_the_same_length():
    assert not json_matches({"a": [1, 2]}, {"a": [1, 2, 3]})


# --------------------------------------------------------------- validate


def test_invalid_regex_is_rejected_at_validation(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    request:
      headers:
        Authorization: { matches: '[unclosed' }
    response:
      body: {}
""",
    )

    with pytest.raises(ValueError, match="invalid regular expression"):
        load_config(config)


def test_one_of_must_be_a_list(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    request:
      query:
        page: { one_of: '1' }
    response:
      body: {}
""",
    )

    with pytest.raises(ValueError, match="'one_of' in route #1 must be a list"):
        load_config(config)


def test_comparison_operators_must_be_numbers(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    request:
      query:
        n: { gte: 'molti' }
    response:
      body: {}
""",
    )

    with pytest.raises(ValueError, match="'gte' in route #1 must be a number"):
        load_config(config)


# ------------------------------------------------------------- served app


def test_matchers_pick_between_routes_on_one_path(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /profile
    request:
      headers:
        Authorization: { matches: '^Bearer .{8,}$' }
    response:
      body:
        ok: true

  - method: GET
    path: /profile
    response:
      status_code: 401
      body:
        error: unauthorized
""",
    )

    client = TestClient(create_app(config))

    good = client.get("/profile", headers={"Authorization": "Bearer abcdefgh"})
    short = client.get("/profile", headers={"Authorization": "Bearer ab"})
    missing = client.get("/profile")

    assert good.status_code == 200
    assert short.status_code == 401
    assert missing.status_code == 401


def test_body_matchers_gate_a_post(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: POST
    path: /signup
    request:
      json:
        age: { gte: 18 }
        referral: { absent: true }
    response:
      status_code: 201
      body:
        ok: true

  - method: POST
    path: /signup
    response:
      status_code: 422
      body:
        error: invalid
""",
    )

    client = TestClient(create_app(config))

    assert client.post("/signup", json={"age": 30}).status_code == 201
    assert client.post("/signup", json={"age": 12}).status_code == 422
    assert client.post("/signup", json={"age": 30, "referral": "x"}).status_code == 422
