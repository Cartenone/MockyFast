import re

from fastapi.testclient import TestClient

from mockyfast.app import create_app
from mockyfast.templating import TemplateContext, render_template

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def context(**kwargs):
    return TemplateContext(**kwargs)


def write_config(tmp_path, body):
    config_file = tmp_path / "mockyfast.yaml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


# ------------------------------------------------------------ generators


def test_uuid_token_produces_a_uuid():
    assert UUID_PATTERN.match(render_template("{{uuid}}", context()))


def test_uuid_tokens_are_independent():
    rendered = render_template(["{{uuid}}", "{{uuid}}"], context())

    assert rendered[0] != rendered[1]


def test_now_returns_an_iso_timestamp():
    rendered = render_template("{{now}}", context())

    assert rendered.endswith("+00:00")


def test_now_accepts_a_strftime_format():
    rendered = render_template("{{now:%Y}}", context())

    assert len(rendered) == 4
    assert rendered.isdigit()


def test_now_format_may_contain_colons():
    rendered = render_template("{{now:%H:%M}}", context())

    assert re.match(r"^\d{2}:\d{2}$", rendered)


def test_timestamp_is_an_integer():
    assert isinstance(render_template("{{timestamp}}", context()), int)


def test_randint_stays_within_its_bounds():
    for _ in range(20):
        value = render_template("{{randint:5:7}}", context())
        assert isinstance(value, int)
        assert 5 <= value <= 7


def test_randfloat_stays_within_its_bounds():
    for _ in range(20):
        value = render_template("{{randfloat:1.5:2.5}}", context())
        assert isinstance(value, float)
        assert 1.5 <= value <= 2.5


def test_choice_picks_one_of_the_options():
    for _ in range(20):
        assert render_template("{{choice:a|b|c}}", context()) in {"a", "b", "c"}


def test_a_generator_with_bad_arguments_is_left_alone():
    assert render_template("{{randint:nope}}", context()) == "{{randint:nope}}"


# --------------------------------------------------------------- lookups


def test_path_scope_reads_a_path_param():
    ctx = context(path_params={"user_id": "42"})

    assert render_template("{{path.user_id}}", ctx) == "42"


def test_bare_braces_still_read_a_path_param():
    ctx = context(path_params={"user_id": "42"})

    assert render_template("User {user_id}", ctx) == "User 42"


def test_query_scope_reads_a_query_param():
    ctx = context(query_params={"page": "3"})

    assert render_template("{{query.page}}", ctx) == "3"


def test_header_lookup_ignores_case():
    ctx = context(headers={"X-Client": "mobile"})

    assert render_template("{{header.x-client}}", ctx) == "mobile"


def test_body_scope_walks_a_dotted_path():
    ctx = context(body={"customer": {"email": "mario@x.it"}})

    assert render_template("{{body.customer.email}}", ctx) == "mario@x.it"


def test_body_scope_indexes_into_lists():
    ctx = context(body={"items": ["primo", "secondo"]})

    assert render_template("{{body.items.1}}", ctx) == "secondo"


def test_missing_lookup_is_left_alone():
    assert render_template("{{body.nope}}", context()) == "{{body.nope}}"
    assert render_template("{{query.nope}}", context()) == "{{query.nope}}"


def test_unknown_token_is_left_alone():
    assert render_template("{{banana}}", context()) == "{{banana}}"


def test_unknown_scope_is_left_alone():
    assert render_template("{{cookie.session}}", context()) == "{{cookie.session}}"


# ---------------------------------------------------------------- shapes


def test_a_lone_token_keeps_its_native_type():
    ctx = context(body={"count": 7, "flag": True, "nested": {"a": 1}})

    assert render_template("{{body.count}}", ctx) == 7
    assert render_template("{{body.flag}}", ctx) is True
    assert render_template("{{body.nested}}", ctx) == {"a": 1}


def test_a_token_inside_text_becomes_a_string():
    ctx = context(body={"count": 7})

    assert render_template("ne ho {{body.count}}", ctx) == "ne ho 7"


def test_several_tokens_in_one_string():
    ctx = context(path_params={"id": "9"}, query_params={"page": "2"})

    assert render_template("{id} p{{query.page}}", ctx) == "9 p2"


def test_templates_reach_nested_structures():
    ctx = context(path_params={"id": "9"})

    rendered = render_template(
        {"outer": [{"inner": "{id}"}, "{{path.id}}"]},
        ctx,
    )

    assert rendered == {"outer": [{"inner": "9"}, "9"]}


def test_dict_keys_are_templated_too():
    ctx = context(path_params={"field": "email"})

    assert render_template({"{{path.field}}": "x"}, ctx) == {"email": "x"}


def test_non_string_values_pass_through():
    assert render_template({"n": 1, "b": True, "z": None}, context()) == {
        "n": 1,
        "b": True,
        "z": None,
    }


def test_a_string_without_tokens_is_untouched():
    assert render_template("nessun segnaposto", context()) == "nessun segnaposto"


def test_stray_braces_survive():
    assert render_template("{ e } da soli", context()) == "{ e } da soli"


# ------------------------------------------------------------- served app


def test_templates_render_in_a_served_response(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: POST
    path: /orders/{order_id}
    response:
      status_code: 201
      body:
        id: "{{uuid}}"
        order: "{order_id}"
        page: "{{query.page}}"
        client: "{{header.x-client}}"
        email: "{{body.customer.email}}"
        quantity: "{{randint:2:2}}"
        message: "Ordine {order_id} per {{body.customer.email}}"
""",
    )

    client = TestClient(create_app(config))

    response = client.post(
        "/orders/A17?page=3",
        headers={"X-Client": "mobile"},
        json={"customer": {"email": "mario@x.it"}},
    )
    payload = response.json()

    assert response.status_code == 201
    assert UUID_PATTERN.match(payload["id"])
    assert payload["order"] == "A17"
    assert payload["page"] == "3"
    assert payload["client"] == "mobile"
    assert payload["email"] == "mario@x.it"
    assert payload["quantity"] == 2
    assert payload["message"] == "Ordine A17 per mario@x.it"


def test_templates_render_in_a_body_from_file(tmp_path):
    (tmp_path / "body.json").write_text(
        '{"id": "{{path.user_id}}", "at": "{{now:%Y}}"}',
        encoding="utf-8",
    )

    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /users/{user_id}
    response:
      body_from: ./body.json
""",
    )

    payload = TestClient(create_app(config)).get("/users/7").json()

    assert payload["id"] == "7"
    assert payload["at"].isdigit()


def test_a_request_without_a_json_body_still_renders(tmp_path):
    config = write_config(
        tmp_path,
        """
routes:
  - method: GET
    path: /ping
    response:
      body:
        id: "{{uuid}}"
        echo: "{{body.anything}}"
""",
    )

    payload = TestClient(create_app(config)).get("/ping").json()

    assert UUID_PATTERN.match(payload["id"])
    assert payload["echo"] == "{{body.anything}}"
