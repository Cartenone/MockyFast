"""The configuration format, described as Pydantic models.

These models are the single source of truth for what a `mockyfast.yaml` may
contain: `mkf validate` runs them and `mkf schema` publishes the JSON Schema
generated from them, so an editor and the CLI can never disagree about what is
allowed.

Two conventions run through this file.

**Empty keys are mistakes, not omissions.** A field written `key: X | None`
accepts `key:` with no value and treats it as absent. A field written `key: X`
with `default=None` does not: YAML turns the empty value into `None`, that
`None` reaches the validator, and the validator rejects it. Only `body`-shaped
fields, where a JSON `null` is a legitimate value, use the first form.

**Validators name the key they blame.** A check that spans several fields
raises `ConfigError(field, message)`, because Pydantic can only report the
model that raised, not the key inside it. Single-field validators raise a plain
`ValueError` describing the value. `mockyfast.errors` turns either one into the
message the CLI prints.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    WithJsonSchema,
    model_validator,
)

from mockyfast.datasources.csv_source import SUPPORTED_SCHEMA_TYPES
from mockyfast.errors import ConfigError, describe_validation_error
from mockyfast.matchers import COMPARISON_KEYS, iter_matchers

SUPPORTED_CONFIG_VERSION = 1

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Methods a mutable data source knows how to serve.
MUTABLE_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Methods that write to the in-memory store.
MUTABLE_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# Write methods addressing one existing resource, so they need a 'where'.
MUTABLE_TARGETED_METHODS = ("PUT", "PATCH", "DELETE")

RESOURCE_ACTIONS = ("list", "get", "create", "update", "delete")


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _http_method(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError("must be a string")

    method = value.upper()

    if method not in HTTP_METHODS:
        raise ValueError(f"must be one of: {', '.join(sorted(HTTP_METHODS))}")

    return method


def _route_path(value: Any) -> Any:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("must be a string starting with '/'")

    return value


def _status_code(value: Any) -> Any:
    if not is_integer(value):
        raise ValueError("must be an integer")

    if value < 100 or value > 599:
        raise ValueError("must be a valid HTTP status code")

    return value


def _milliseconds(value: Any) -> Any:
    if not is_integer(value) or value < 0:
        raise ValueError("must be a non-negative integer")

    return value


def _delay(value: Any) -> Any:
    # A mapping is left for DelayRange to check, so its bounds keep their own
    # error location.
    if isinstance(value, dict):
        return value

    if not is_integer(value):
        raise ValueError("must be an integer")

    if value < 0:
        raise ValueError("cannot be negative")

    return value


def _probability(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")

    if value < 0 or value > 1:
        raise ValueError("must be between 0 and 1")

    return value


def _source_type(value: Any) -> Any:
    if value not in ("csv", "json"):
        raise ValueError("must be 'csv' or 'json'")

    return value


def _data_source_mode(value: Any) -> Any:
    if value not in ("first", "all"):
        raise ValueError("must be 'first' or 'all'")

    return value


def _schema_type(value: Any) -> Any:
    if value not in SUPPORTED_SCHEMA_TYPES:
        raise ValueError(f"must be one of: {', '.join(sorted(SUPPORTED_SCHEMA_TYPES))}")

    return value


def _persist(value: Any) -> Any:
    if not isinstance(value, (bool, str)):
        raise ValueError("must be a boolean or a path")

    return value


def _json_match(value: Any) -> Any:
    if not isinstance(value, (dict, list)):
        raise ValueError("must be an object or a list")

    return value


def _non_empty_string(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        raise ValueError("must be a non-empty string")

    return value


def _responses(value: Any) -> Any:
    if not isinstance(value, list) or not value:
        raise ValueError("must be a non-empty list")

    return value


def _resource_actions(value: Any) -> Any:
    if not isinstance(value, list) or not value:
        raise ValueError("must be a non-empty list")

    for action in value:
        if action not in RESOURCE_ACTIONS:
            raise ValueError(f"must only contain: {', '.join(RESOURCE_ACTIONS)}")

    return value


def _config_version(value: Any) -> Any:
    if value != SUPPORTED_CONFIG_VERSION:
        raise ValueError(
            f"must be {SUPPORTED_CONFIG_VERSION}; "
            f"this MockyFast reads version {SUPPORTED_CONFIG_VERSION} configurations"
        )

    return value


# The validator has already uppercased the value by the time the Literal is
# checked, so the published schema lists both spellings an editor may meet.
HttpMethod = Annotated[
    Literal[HTTP_METHODS],
    BeforeValidator(_http_method),
    WithJsonSchema(
        {
            "enum": [*HTTP_METHODS, *(method.lower() for method in HTTP_METHODS)],
            "description": "HTTP method the route answers.",
        }
    ),
]

RoutePath = Annotated[
    str,
    Field(pattern="^/", description="Request path, starting with '/'."),
    BeforeValidator(_route_path),
]

StatusCode = Annotated[int, Field(ge=100, le=599), BeforeValidator(_status_code)]

Milliseconds = Annotated[int, Field(ge=0), BeforeValidator(_milliseconds)]

SchemaType = Annotated[
    Literal["str", "int", "float", "bool"], BeforeValidator(_schema_type)
]

Persist = Annotated[bool | str, BeforeValidator(_persist)]

Probability = Annotated[float, Field(ge=0, le=1), BeforeValidator(_probability)]

JsonMatch = Annotated[dict[str, Any] | list[Any], BeforeValidator(_json_match)]

NonEmptyString = Annotated[
    str, Field(min_length=1), BeforeValidator(_non_empty_string)
]

ConfigVersion = Annotated[
    Literal[SUPPORTED_CONFIG_VERSION], BeforeValidator(_config_version)
]


class ConfigModel(BaseModel):
    # An unknown key is almost always a typo, and silently ignoring it is the
    # kind of surprise this tool exists to avoid.
    model_config = ConfigDict(extra="forbid")


class DelayRange(ConfigModel):
    """Latency drawn from a range, so it varies from call to call."""

    min: Milliseconds = Field(default=None, description="Lower bound, in milliseconds.")
    max: Milliseconds = Field(default=None, description="Upper bound, in milliseconds.")


DelayMs = Annotated[int | DelayRange, BeforeValidator(_delay)]


class Fault(ConfigModel):
    """A failure injected in place of the normal response."""

    probability: Probability = Field(
        default=None, description="Chance the fault fires, from 0 to 1."
    )
    status_code: StatusCode = Field(
        default=None, description="Status of the fault response. Defaults to 500."
    )
    body: Any = Field(default=None, description="Body of the fault response.")
    delay_ms: DelayMs = Field(
        default=None,
        description="Time the fault takes; use it to simulate a timeout.",
    )


class Where(ConfigModel):
    """Which row of a data source a request addresses."""

    column: str = Field(default=None, description="CSV column to compare.")
    field: str = Field(default=None, description="JSON field to compare.")
    equals_path_param: str = Field(
        default=None, description="Path parameter holding the expected value."
    )
    equals_query_param: str = Field(
        default=None, description="Query parameter holding the expected value."
    )


class DataSource(ConfigModel):
    """A response built from a CSV or JSON file next to the configuration."""

    type: Annotated[Literal["csv", "json"], BeforeValidator(_source_type)] = Field(
        description="Format of the data file."
    )
    file: str = Field(description="Data file, relative to the configuration file.")
    mode: Annotated[
        Literal["first", "all"], BeforeValidator(_data_source_mode)
    ] = Field(
        default=None,
        description="'all' returns a list, 'first' a single object. "
        "Required except on a write route of a mutable source.",
    )
    where: Where = Field(
        default=None, description="Filter rows by a path or query parameter."
    )
    wrap: str = Field(default=None, description="Wrap the result under this key.")
    not_found_status: StatusCode = Field(
        default=None,
        description="Status used when 'mode: first' finds nothing. Defaults to 404.",
    )
    not_found_body: Any = Field(
        default=None, description="Body used when 'mode: first' finds nothing."
    )
    coerce_types: StrictBool = Field(
        default=None, description="CSV only: infer primitive types from the text."
    )
    schema_: dict[str, SchemaType] = Field(
        default=None,
        alias="schema",
        description="CSV only: explicit column-to-type mapping.",
    )
    list_query: StrictBool = Field(
        default=None,
        description="Allow filtering, sorting and paging on a 'mode: all' route.",
    )
    mutable: StrictBool = Field(
        default=None, description="Serve the file from a writable in-memory store."
    )
    persist: Persist = Field(
        default=None,
        description="Keep writes across restarts: true, or a path for the state file.",
    )
    key_field: str = Field(
        default=None, description="Primary key of a mutable resource."
    )
    resource_name: str = Field(
        default=None, description="Store identity shared by every route of a resource."
    )

    @model_validator(mode="after")
    def _check_data_source(self) -> "DataSource":
        if self.schema_ is not None and self.type != "csv":
            raise ConfigError("schema", "is only supported for 'csv' data sources")

        if self.where is not None:
            key_name = "column" if self.type == "csv" else "field"

            if getattr(self.where, key_name) is None:
                raise ConfigError(f"where.{key_name}", "is required")

            targets = (self.where.equals_path_param, self.where.equals_query_param)

            if (targets[0] is None) == (targets[1] is None):
                raise ConfigError(
                    "where",
                    "must define exactly one of 'equals_path_param' or "
                    "'equals_query_param'",
                )

        if self.persist and not self.mutable:
            raise ConfigError("persist", "needs 'mutable: true'")

        if self.mutable:
            # Without an explicit name the store falls back to the route path, so
            # /users and /users/{user_id} would silently hold separate copies.
            for key in ("key_field", "resource_name"):
                if not getattr(self, key):
                    raise ConfigError(key, "is required when mutable is true")

        return self


class Response(ConfigModel):
    """What a matched route answers."""

    status_code: StatusCode = Field(
        default=None, description="HTTP status of the response. Defaults to 200."
    )
    body: Any = Field(default=None, description="Inline response body.")
    body_from: str = Field(
        default=None,
        description="JSON file holding the whole body, relative to the configuration.",
    )
    data_source: DataSource = Field(
        default=None, description="Build the body from a CSV or JSON file."
    )
    delay_ms: DelayMs = Field(
        default=None,
        description="Latency before answering: a number, or a {min, max} range.",
    )
    fault: Fault = Field(
        default=None, description="Replace the response with a failure."
    )

    @model_validator(mode="after")
    def _check_response(self) -> "Response":
        chosen = [
            key
            for key in ("body", "body_from", "data_source")
            if key in self.model_fields_set
        ]

        if len(chosen) > 1:
            raise ConfigError(
                None, "can only define one of 'body', 'body_from', or 'data_source'"
            )

        return self


class RequestMatch(ConfigModel):
    """Conditions a request must meet for the route to answer."""

    query: dict[str, Any] = Field(
        default=None, description="Expected query parameters, compared as text."
    )
    headers: dict[str, Any] = Field(
        default=None,
        description="Expected headers, compared as text and case-insensitively.",
    )
    json_body: JsonMatch = Field(
        default=None,
        alias="json",
        description="Expected JSON body; object keys match partially, lists exactly.",
    )

    def as_matcher_tree(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "headers": self.headers,
            "json": self.json_body,
        }


class Route(ConfigModel):
    """One (method, path) pair and the response it produces."""

    method: HttpMethod
    path: RoutePath
    request: RequestMatch = Field(
        default=None, description="Conditions the request must meet."
    )
    response: Response = Field(default=None, description="The response to return.")
    responses: Annotated[
        list[Response], Field(min_length=1), BeforeValidator(_responses)
    ] = Field(
        default=None,
        description="Responses returned on successive calls; the last one repeats.",
    )

    @model_validator(mode="after")
    def _check_route(self) -> "Route":
        if self.response is None and self.responses is None:
            raise ConfigError(None, "is missing 'response'")

        if self.response is not None and self.responses is not None:
            raise ConfigError(None, "cannot define both 'response' and 'responses'")

        if self.request is not None:
            _check_matchers(self.request)

        if self.responses is None:
            _check_data_source_method(self.response, "response", self.method)
        else:
            for position, response in enumerate(self.responses):
                _check_data_source_method(
                    response, f"responses.{position}", self.method
                )

        return self


def _check_matchers(request: RequestMatch) -> None:
    """Catch broken matcher operators before the server starts.

    The messages name the operator rather than its position, because a matcher
    can sit anywhere inside a nested body and the operator is what has to change.
    """
    for matcher in iter_matchers(request.as_matcher_tree()):
        if "matches" in matcher:
            try:
                re.compile(str(matcher["matches"]))
            except re.error as exc:
                raise ConfigError(
                    "request",
                    f"has an invalid regular expression {matcher['matches']!r}: {exc}",
                ) from exc

        if "one_of" in matcher and not isinstance(matcher["one_of"], list):
            raise ConfigError("one_of", "must be a list")

        for operator in COMPARISON_KEYS:
            if operator in matcher and not isinstance(matcher[operator], (int, float)):
                raise ConfigError(operator, "must be a number")


def _check_data_source_method(response: Response, prefix: str, method: str) -> None:
    """The data source rules that depend on the route's method."""
    data_source = response.data_source

    if data_source is None:
        return

    # 'mode' shapes a read response, so it carries no meaning on a write route.
    mode_is_optional = bool(data_source.mutable) and method in MUTABLE_WRITE_METHODS

    if data_source.mode is None and not mode_is_optional:
        raise ConfigError(f"{prefix}.data_source.mode", "must be 'first' or 'all'")

    if not data_source.mutable:
        return

    if method not in MUTABLE_METHODS:
        raise ConfigError(
            "method",
            f"must be one of: {', '.join(sorted(MUTABLE_METHODS))} "
            f"when mutable is true",
        )

    if method in MUTABLE_TARGETED_METHODS and data_source.where is None:
        raise ConfigError(
            f"{prefix}.data_source.where",
            f"is required for {method} on a mutable data source",
        )


class ResourceSource(ConfigModel):
    """The data file backing a resource."""

    type: Annotated[Literal["csv", "json"], BeforeValidator(_source_type)] = Field(
        description="Format of the data file."
    )
    file: str = Field(description="Data file, relative to the configuration file.")


class Resource(ConfigModel):
    """A CRUD resource that expands into routes before validation."""

    name: NonEmptyString = Field(
        description="Resource name, also the identity of its store."
    )
    path: RoutePath = Field(
        default=None, description="Base path of the collection. Defaults to /<name>."
    )
    source: ResourceSource = Field(description="The data file backing the resource.")
    key_field: NonEmptyString = Field(
        default=None,
        description="Primary key, also the path parameter name. Defaults to 'id'.",
    )
    methods: Annotated[
        list[Literal[RESOURCE_ACTIONS]],
        Field(min_length=1),
        BeforeValidator(_resource_actions),
    ] = Field(default=None, description="Actions to generate. Defaults to all of them.")
    wrap: str = Field(
        default=None, description="Wrap the list route's result under this key."
    )
    not_found_status: StatusCode = Field(
        default=None,
        description="Status of the single-resource routes when nothing matches.",
    )
    not_found_body: Any = Field(
        default=None,
        description="Body of the single-resource routes when nothing matches.",
    )
    delay_ms: DelayMs = Field(
        default=None, description="Latency applied to every generated route."
    )
    list_query: StrictBool = Field(
        default=None,
        description="Filtering, sorting and paging on the list route. On by default.",
    )
    persist: Persist = Field(
        default=None,
        description="Keep writes across restarts: true, or a path for the state file.",
    )


class MockyFastConfig(ConfigModel):
    """A whole `mockyfast.yaml`."""

    version: ConfigVersion = Field(
        default=None,
        description=(
            "Configuration format version. Optional today; declaring it lets the "
            "format change without breaking this file."
        ),
    )
    routes: list[Route] | None = Field(
        default=None, description="Explicitly declared routes."
    )
    resources: list[Resource] | None = Field(
        default=None, description="CRUD resources, expanded into routes."
    )


def validate_shape(data: dict) -> None:
    """Check a configuration against the models, raising the CLI's message."""
    try:
        MockyFastConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(describe_validation_error(exc, data)) from exc


SCHEMA_URL = (
    "https://raw.githubusercontent.com/Cartenone/MockyFast/main/mockyfast.schema.json"
)


def drop_null_defaults(node: Any) -> Any:
    """Remove the `default: null` a not-set field would otherwise advertise."""
    if isinstance(node, dict):
        return {
            key: drop_null_defaults(value)
            for key, value in node.items()
            if not (key == "default" and value is None)
        }

    if isinstance(node, list):
        return [drop_null_defaults(item) for item in node]

    return node


def config_json_schema() -> dict:
    """The JSON Schema an editor validates `mockyfast.yaml` against."""
    schema = MockyFastConfig.model_json_schema()

    schema["title"] = "MockyFast configuration"
    schema["description"] = (
        "Configuration for the MockyFast mock server. "
        "Generated from the Pydantic models with 'mkf schema'."
    )

    return drop_null_defaults(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": SCHEMA_URL,
            **schema,
        }
    )
