import time
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from mockyfast.app import create_app
from mockyfast.config import load_config
from mockyfast.faults import resolve_delay_ms, should_fault


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


def build_client(tmp_path, body):
    return TestClient(create_app(write_config(tmp_path, body)))


# ------------------------------------------------------------------ units


def test_a_fixed_delay_is_returned_as_is():
    assert resolve_delay_ms({"delay_ms": 250}) == 250


def test_a_missing_delay_is_zero():
    assert resolve_delay_ms({}) == 0


def test_a_range_delay_stays_within_bounds():
    for _ in range(50):
        assert 100 <= resolve_delay_ms({"delay_ms": {"min": 100, "max": 200}}) <= 200


def test_a_reversed_range_is_still_usable():
    for _ in range(20):
        assert 100 <= resolve_delay_ms({"delay_ms": {"min": 200, "max": 100}}) <= 200


def test_a_range_without_max_is_a_fixed_delay():
    assert resolve_delay_ms({"delay_ms": {"min": 40}}) == 40


def test_probability_one_always_faults():
    assert all(should_fault({"probability": 1}) for _ in range(20))
    assert all(should_fault({}) for _ in range(20))


def test_probability_zero_never_faults():
    assert not any(should_fault({"probability": 0}) for _ in range(20))


def test_a_non_numeric_probability_never_faults():
    assert should_fault({"probability": "spesso"}) is False


# ----------------------------------------------------------------- faults


def test_a_certain_fault_replaces_the_response(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /broken
    response:
      body:
        ok: true
      fault:
        status_code: 503
        body:
          error: overloaded
""",
    )

    response = client.get("/broken")

    assert response.status_code == 503
    assert response.json() == {"error": "overloaded"}


def test_a_fault_defaults_to_a_500(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /broken
    response:
      body:
        ok: true
      fault: {}
""",
    )

    assert client.get("/broken").status_code == 500


def test_a_probability_of_zero_leaves_the_response_alone(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /fine
    response:
      body:
        ok: true
      fault:
        probability: 0
        status_code: 500
""",
    )

    assert client.get("/fine").json() == {"ok": True}


def test_a_partial_probability_produces_both_outcomes(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /flaky
    response:
      body:
        ok: true
      fault:
        probability: 0.5
        status_code: 503
""",
    )

    seen = Counter(client.get("/flaky").status_code for _ in range(300))

    assert seen[200] > 20
    assert seen[503] > 20


def test_a_fault_can_carry_its_own_delay(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /timeout
    response:
      body:
        ok: true
      fault:
        status_code: 504
        delay_ms: 300
""",
    )

    started_at = time.perf_counter()
    response = client.get("/timeout")
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert response.status_code == 504
    assert elapsed_ms >= 250


def test_a_delay_range_is_honoured(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /jitter
    response:
      delay_ms:
        min: 200
        max: 260
      body:
        ok: true
""",
    )

    started_at = time.perf_counter()
    client.get("/jitter")
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert elapsed_ms >= 180


# -------------------------------------------------------------- sequences


SEQUENCE_CONFIG = """
routes:
  - method: GET
    path: /job/{job_id}
    responses:
      - status_code: 202
        body:
          status: accepted
      - status_code: 202
        body:
          status: running
      - status_code: 200
        body:
          status: done
"""


def test_a_sequence_advances_on_every_call(tmp_path):
    client = build_client(tmp_path, SEQUENCE_CONFIG)

    seen = [client.get("/job/1").json()["status"] for _ in range(3)]

    assert seen == ["accepted", "running", "done"]


def test_the_last_entry_keeps_answering(tmp_path):
    client = build_client(tmp_path, SEQUENCE_CONFIG)

    for _ in range(3):
        client.get("/job/1")

    assert client.get("/job/1").json()["status"] == "done"
    assert client.get("/job/1").status_code == 200


def test_a_sequence_carries_its_own_status_codes(tmp_path):
    client = build_client(tmp_path, SEQUENCE_CONFIG)

    assert client.get("/job/1").status_code == 202
    assert client.get("/job/1").status_code == 202
    assert client.get("/job/1").status_code == 200


def test_a_sequence_entry_can_use_templates(tmp_path):
    client = build_client(
        tmp_path,
        """
routes:
  - method: GET
    path: /job/{job_id}
    responses:
      - body:
          id: "{job_id}"
""",
    )

    assert client.get("/job/7").json() == {"id": "7"}


# --------------------------------------------------------------- validate


def test_a_route_cannot_define_both_forms(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      body: {}
    responses:
      - body: {}
""",
    )

    with pytest.raises(ValueError, match="cannot define both 'response' and 'responses'"):
        load_config(config)


def test_responses_must_not_be_empty(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    responses: []
""",
    )

    with pytest.raises(ValueError, match="'responses' in route #1 must be a non-empty list"):
        load_config(config)


def test_every_sequence_entry_is_validated(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    responses:
      - body: {}
      - status_code: 999
        body: {}
""",
    )

    with pytest.raises(ValueError, match="must be a valid HTTP status code"):
        load_config(config)


@pytest.mark.parametrize(
    "fault, message",
    [
        ("probability: 2", "must be between 0 and 1"),
        ("probability: 'spesso'", "must be a number"),
        ("status_code: 999", "must be a valid HTTP status code"),
        ("delay_ms: -5", "cannot be negative"),
    ],
)
def test_invalid_fault_is_rejected(tmp_path, fault, message):
    config = write_config(
        tmp_path,
        f"""
routes:
  - method: GET
    path: /x
    response:
      body: {{}}
      fault:
        {fault}
""",
    )

    with pytest.raises(ValueError, match=message):
        load_config(config)


def test_a_delay_range_bound_must_be_a_non_negative_integer(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /x
    response:
      delay_ms:
        min: -1
      body: {}
""",
    )

    with pytest.raises(ValueError, match="'response.delay_ms.min' in route #1"):
        load_config(config)


# ------------------------------------------------- endpoint signature leak


def test_route_internals_are_not_request_parameters(tmp_path):
    """The handler must not expose its closure state as query parameters."""
    client = build_client(
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

    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/x"]["get"].get("parameters", []) == []


def test_a_client_cannot_redirect_the_config_path(tmp_path):
    inside = tmp_path / "mocks"
    inside.mkdir()
    (inside / "body.json").write_text('{"origin": "inside"}', encoding="utf-8")

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "body.json").write_text('{"origin": "outside"}', encoding="utf-8")

    config_file = inside / "mockyfast.yaml"
    config_file.write_text(
        """
routes:
  - method: GET
    path: /data
    response:
      body_from: ./body.json
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(str(config_file)), raise_server_exceptions=False)

    hijacked = client.get(
        "/data", params={"_config_path": str(outside / "mockyfast.yaml")}
    )

    assert hijacked.json() == {"origin": "inside"}
