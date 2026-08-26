![mockyfast cover](./assets/cover.png)

# MockyFast

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**MockyFast** is a Python CLI tool for mocking HTTP APIs locally using YAML, JSON, and CSV-backed datasets.

It helps you simulate external services during local development without relying on hosted mock platforms or remote dashboards.

## Why?

Because sometimes you just need a fast, local, and controllable way to simulate APIs while developing.

No external mock platforms, no unnecessary setup — just local files, a local server, and a workflow you control.

---

## Features

- initialize a sample config file
- validate mock configuration before running
- serve mock HTTP endpoints locally
- support inline JSON responses
- support external JSON response files
- support data-driven mocks backed by:
  - CSV files
  - JSON files
- support stateful mocks with in-memory CRUD (`mutable`)
- support response shaping for data sources:
  - `wrap`
  - `not_found_status`
  - `not_found_body`
- support CSV type coercion and schema mapping
- support path parameters
- support request matching by:
  - query params
  - headers
  - JSON body
- support delayed responses with `delay_ms`
- automated tests with `pytest`

---

## Installation

### From source

```bash
git clone https://github.com/Cartenone/MockyFast.git
cd MockyFast
pip install .
```

### Development install

```bash
pip install -e ".[dev]"
```

---

## Commands

### Main command

```bash
mockyfast init
mockyfast validate mockyfast.yaml
mockyfast serve mockyfast.yaml --port 8000
```

### Short alias

```bash
mkf init
mkf validate mockyfast.yaml
mkf serve mockyfast.yaml --port 8000
```

---

## Quick start

Create a sample config:

```bash
mkf init
```

Validate it:

```bash
mkf validate mockyfast.yaml
```

Start the mock server:

```bash
mkf serve mockyfast.yaml --port 8000
```

Then call it:

```bash
curl http://127.0.0.1:8000/health
```

---

## Example configuration

### Basic route

```yaml
routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
```

---

## Using external JSON files

### `mockyfast.yaml`

```yaml
routes:
  - method: GET
    path: /users
    response:
      status_code: 200
      body_from: ./responses/users.json
```

### `responses/users.json`

```json
{
  "users": [
    { "id": 1, "name": "Mario" },
    { "id": 2, "name": "Luigi" }
  ]
}
```

---

## Data-driven mocks

MockyFast can build responses from local CSV or JSON files, making mocks more dynamic and reusable.

A data source is declared under `response.data_source`:

| Key | Required | Description |
|---|---|---|
| `type` | yes | `csv` or `json` |
| `file` | yes | Path relative to the config file |
| `mode` | for reads | `all` returns a list, `first` returns a single object |
| `where` | no | Filter rows by a path or query parameter |
| `wrap` | no | Wrap the result under a key |
| `not_found_status` | no | Status used when `mode: first` finds nothing (default `404`) |
| `not_found_body` | no | Body used when `mode: first` finds nothing |
| `coerce_types` | no | CSV only — infer primitive types |
| `schema` | no | CSV only — explicit type mapping |
| `mutable` | no | Serve the file from a writable in-memory store |
| `key_field` | with `mutable` | Primary key of the resource |
| `resource_name` | with `mutable` | Store identity shared across routes |

### CSV data source

```yaml
routes:
  - method: GET
    path: /users
    response:
      data_source:
        type: csv
        file: ./data/users.csv
        mode: all
        wrap: items

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
        not_found_status: 404
        not_found_body:
          error: user_not_found
```

### `mocks/data/users.csv`

```csv
id,name,active,balance
1,Mario,true,12.5
2,Luigi,false,7
```

### Example calls

```bash
curl http://127.0.0.1:8000/users
curl http://127.0.0.1:8000/users/1
curl http://127.0.0.1:8000/users/999
```

### Example response for `GET /users`

```json
{
  "items": [
    {
      "id": "1",
      "name": "Mario",
      "active": "true",
      "balance": "12.5"
    },
    {
      "id": "2",
      "name": "Luigi",
      "active": "false",
      "balance": "7"
    }
  ]
}
```

### JSON data source

A JSON data source works the same way, but the file must contain a **root list of objects** and the filter key is `field` instead of `column`.

```yaml
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
```

### `mocks/data/users.json`

```json
[
  { "id": 1, "name": "Mario", "role": "admin" },
  { "id": 2, "name": "Luigi", "role": "user" },
  { "id": 3, "name": "Anna", "role": "user" }
]
```

JSON values keep their original types, so `coerce_types` and `schema` are not needed (and not supported) for JSON sources.

### Filtering by query param

`where` can read a query parameter instead of a path parameter:

```yaml
where:
  field: role
  equals_query_param: role
```

```bash
curl "http://127.0.0.1:8000/users?role=admin"
```

Exactly one of `equals_path_param` or `equals_query_param` must be set.

### Type coercion

You can automatically coerce CSV values into Python/JSON primitive types.

```yaml
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
```

With `coerce_types: true`, values such as:

- `true` → `true`
- `false` → `false`
- `12` → `12`
- `12.5` → `12.5`

are returned as properly typed JSON values.

### Schema mapping

For more control, you can define an explicit schema:

```yaml
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
```

Supported schema types:

- `str`
- `int`
- `float`
- `bool`

When `schema` is present, it takes precedence over `coerce_types`.

---

## Stateful mocks

Set `mutable: true` to turn a data source into a writable in-memory resource. The file is read **once at startup** to seed the store, and every request after that reads and writes the in-memory copy.

**The data file on disk is never modified.** Restarting the server resets the resource to its seeded state.

Two keys are required alongside `mutable`:

- `key_field` — the primary key of the resource
- `resource_name` — the store identity. Every route that should share the same data must use the same `resource_name`, because `/users` and `/users/{user_id}` are different paths and would otherwise be separate stores.

### Full CRUD example

```yaml
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
        where:
          field: id
          equals_path_param: user_id
```

### Example session

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H 'content-type: application/json' \
  -d '{"id": 4, "name": "Giulia"}'

curl http://127.0.0.1:8000/users/4

curl -X PUT http://127.0.0.1:8000/users/4 \
  -H 'content-type: application/json' \
  -d '{"name": "Giulia Updated"}'

curl -X DELETE http://127.0.0.1:8000/users/4
```

### What each method does

| Method | `mode` | `where` | Behaviour |
|---|---|---|---|
| `GET` | required | optional | Reads from the store, honouring `wrap` and `not_found_*` |
| `POST` | ignored | not used | Creates a resource from the request body |
| `PUT` | ignored | required | Merges the request body into the matched resource |
| `PATCH` | ignored | required | Same as `PUT` |
| `DELETE` | ignored | required | Removes the matched resource, returns `{"deleted": true}` |

### Write rules

- The request body must be a JSON **object** — anything else returns `400`.
- `POST` requires `key_field` in the body (`400` if missing) and rejects an existing key with `409`.
- `PUT` and `PATCH` merge the body into the stored resource; keys not present in the body are preserved.
- `PUT` and `PATCH` cannot change `key_field` — attempting to do so returns `400`.
- When `PUT`, `PATCH`, or `DELETE` match nothing, the configured `not_found_status` / `not_found_body` are used (default `404`).

---

## Path params

You can use path parameters in the route path and reference them in the response body.

```yaml
routes:
  - method: GET
    path: /users/{user_id}
    response:
      status_code: 200
      body:
        id: "{user_id}"
        name: "User {user_id}"
```

Example:

```bash
curl http://127.0.0.1:8000/users/123
```

Response:

```json
{
  "id": "123",
  "name": "User 123"
}
```

Substitution applies to string **values**, not to object keys.

---

## Request matching

`mockyfast` can return different responses for the same path depending on the request.

Routes are evaluated in declaration order, and the first one whose matchers all pass wins. Put the most specific route first.

### Match by query params

```yaml
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
```

### Match by headers

```yaml
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
```

### Match by JSON body

```yaml
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
```

Matching is partial for `query` and `headers` (extra values in the request are ignored) and for object keys in `json`. Lists inside `json` must match exactly, including length.

---

## Delayed responses

You can simulate slow APIs using `delay_ms`.

```yaml
routes:
  - method: GET
    path: /slow
    response:
      status_code: 200
      delay_ms: 3000
      body:
        ok: true
```

The delay applies to every response the route produces, including not-found and CRUD responses.

This is useful when you want to simulate:

- slow services
- network latency
- client-side timeouts

---

## Behaviour notes

- **Route order matters.** `/users/me` declared after `/users/{user_id}` is never reached. Declare static paths first.
- **Non-mutable data files are re-read on every request.** Editing a CSV or JSON data source is picked up without restarting the server. `mutable` sources are the exception: they are read once at startup.
- **Referenced files must stay inside the config directory.** `body_from` and `data_source.file` cannot escape the folder containing the YAML file.
- **State is per-process.** The in-memory store is not shared between server restarts or between multiple processes.

---

## Example use case

Imagine your application depends on an external service.

Instead of calling the real service during local development, you can point your app to `http://127.0.0.1:8000` and let `mockyfast` simulate the API.

That makes it easier to:

- develop locally
- reproduce edge cases
- test success and error responses
- work without depending on external environments

---

## Project structure example

```text
mocks/
├─ mockyfast.yaml
├─ data/
│  ├─ users.csv
│  └─ users.json
└─ responses/
   └─ users.json
```

Then run:

```bash
mkf serve ./mocks/mockyfast.yaml --port 8000
```

---

## Validation

Before starting the server, you can validate your configuration:

```bash
mkf validate mockyfast.yaml
```

This helps catch issues like:

- missing `routes`
- invalid route structure
- unknown HTTP methods, or paths not starting with `/`
- missing JSON files
- missing CSV files
- files referenced outside the configuration directory
- invalid `status_code`
- invalid `delay_ms`
- invalid request matching config
- invalid CSV schema configuration
- incomplete `mutable` configuration (`key_field`, `resource_name`, `where`)

---

## Development

Run the test suite:

```bash
pytest
```

With coverage:

```bash
pytest --cov=mockyfast --cov-report=term-missing
```

Lint:

```bash
ruff check .
```

---

## Roadmap

Planned improvements:

- better error messages and validation feedback
- HTTP client / probe mode
- capture real API responses into reusable mock files
- more advanced matching rules
- extended fault injection beyond `delay_ms`
- persisting mutable state across restarts

Future exploration:

- OpenAPI-based mock generation
- record & replay mode
- GraphQL support
- WebSocket mocking
- gRPC support
- SOAP/XML support

---

## Author

Created by Cartenone.

---

## License

MIT
