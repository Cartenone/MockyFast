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

**Getting started**

- serve a folder of JSON/CSV files as a REST API with no configuration at all
- declare a whole CRUD resource in a few lines with `resources:`
- generate a config from existing data with `init --from-data`
- browse the served routes at `/`
- restart automatically on config changes with `serve --reload`

**Responses**

- inline bodies, external JSON files, and CSV/JSON-backed data sources
- templates: `{{uuid}}`, `{{now}}`, `{{randint:1:9}}`, and echoes of the request
- path parameters
- CSV type coercion and schema mapping
- response shaping: `wrap`, `not_found_status`, `not_found_body`
- answer differently on successive calls with `responses:`

**Behaviour**

- stateful in-memory CRUD with `mutable`, optionally saved across restarts
- filtering, sorting and paging on list routes
- request matching by query params, headers and JSON body, with operators
  (`matches`, `contains`, `one_of`, `gte`, `absent`, …)
- latency with `delay_ms`, fixed or as a range
- failure simulation with `fault`

**Tooling**

- `validate` checks the config before the server starts, and warns about
  unreachable routes
- `explain` shows which route answers a request, and why the others do not
- `schema` publishes a JSON Schema, for autocompletion and live validation in
  your editor
- permissive CORS by default, so a browser app can call the mock
- automated tests with `pytest`

---

## Contents

- [Installation](#installation) · [Commands](#commands) · [Quick start](#quick-start)
- **Responses**: [inline](#example-configuration) ·
  [external files](#using-external-json-files) ·
  [data-driven](#data-driven-mocks) ·
  [templates](#response-templates) ·
  [sequences](#response-sequences)
- **Resources**: [shorthand](#resources-a-whole-crud-api-in-a-few-lines) ·
  [stateful CRUD](#stateful-mocks) ·
  [filter/sort/page](#filtering-sorting-and-paging) ·
  [persistence](#keeping-state-across-restarts)
- **Behaviour**: [request matching](#request-matching) ·
  [latency and faults](#latency-and-faults) ·
  [notes](#behaviour-notes)
- **Tooling**: [validation](#validation) ·
  [editor support](#editor-support) ·
  [explain](#explaining-a-request) ·
  [development](#development)

---

## Installation

### From source

```bash
git clone https://github.com/Cartenone/MockyFast.git
cd MockyFast
pip install .
```

### Editor support

`mkf schema` prints a JSON Schema generated from the same models `mkf validate`
runs, so your editor and the CLI cannot disagree about what a configuration may
contain:

```bash
mkf schema > mockyfast.schema.json
```

The generated file is also published in this repository, at
[`mockyfast.schema.json`](./mockyfast.schema.json), so you can point at it
without generating anything.

### One file at a time

Put a modeline at the top of the configuration. The
[YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
for VS Code reads it, as does any editor speaking the YAML language server
protocol:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/Cartenone/MockyFast/main/mockyfast.schema.json

version: 1

routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
```

### Every config in a project

In `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/Cartenone/MockyFast/main/mockyfast.schema.json": [
      "mockyfast.yaml",
      "mocks/**/*.yaml"
    ]
  }
}
```

Either form accepts a local file too: replace the URL with
`./mockyfast.schema.json` and the editor validates against the schema of the
version you have installed.

---

## Development install

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
mockyfast explain mockyfast.yaml GET /users/1
mockyfast schema > mockyfast.schema.json
```

### Short alias

```bash
mkf init
mkf validate mockyfast.yaml
mkf serve mockyfast.yaml --port 8000
```

### Reference

```text
mkf init     [--output FILE] [--from-data PATH]
mkf schema   [--output FILE]
mkf validate CONFIG
mkf serve    CONFIG [--host HOST] [--port PORT] [--reload] [--no-index] [--no-cors]
mkf explain  CONFIG METHOD TARGET [-H/--header 'Name: value']... [--body JSON]
```

| Command | Option | Description |
|---|---|---|
| `init` | `--output <file>` | Where to write the config (default `mockyfast.yaml`) |
| `init` | `--from-data <path>` | Generate the config from a data file or folder |
| `schema` | `-o` / `--output <file>` | Write the JSON Schema to a file instead of standard output |
| `serve` | `--host` | Bind address (default `127.0.0.1`) |
| `serve` | `--port` | Bind port (default `8000`) |
| `serve` | `--reload` | Restart when the config or its data files change |
| `serve` | `--no-index` | Do not serve the generated route index at `/` (on by default) |
| `serve` | `--no-cors` | Do not send permissive CORS headers (on by default) |
| `explain` | `-H` / `--header` | Request header as `'Name: value'`; repeatable |
| `explain` | `--body '{...}'` | JSON request body |

`CONFIG` is a YAML file, a data folder, or a single `.json`/`.csv` data file.
`explain` exits non-zero when no route answers the request.

---

## Quick start

### The shortest path: no configuration

Point MockyFast at a folder of `.json` or `.csv` files and it derives a full
CRUD API from them:

```bash
mkf serve ./data
```

```text
data/
├─ users.json      ->  GET/POST /users, GET/PUT/PATCH/DELETE /users/{id}
└─ products.csv    ->  GET/POST /products, GET/PUT/PATCH/DELETE /products/{sku}
```

The key field is detected automatically: `id` when the data has one, otherwise
the first column. Open <http://127.0.0.1:8000/> to see every route that was
generated.

When you outgrow it, write the equivalent config out and edit it by hand:

```bash
mkf init --from-data ./data
```

### Starting from a config

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

## The `version` key

A configuration can declare the format version it was written against:

```yaml
version: 1

routes:
  - method: GET
    path: /health
    response:
      status_code: 200
      body:
        ok: true
```

It is optional, and `1` is the only version MockyFast reads today. Writing it
down means a later change to the format can be introduced without breaking this
file: a version this build does not know is refused with a message instead of
being misread.

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
| `list_query` | no | Allow filtering, sorting and paging on a `mode: all` route |
| `mutable` | no | Serve the file from a writable in-memory store |
| `persist` | no | Keep writes across restarts (`true`, or a path) |
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

## Resources: a whole CRUD API in a few lines

Declaring the five routes of a REST resource by hand means repeating the same
`data_source` block five times. A `resources:` entry describes the resource
once and expands into the equivalent routes before validation runs:

```yaml
resources:
  - name: users
    path: /users
    source:
      type: json
      file: ./data/users.json
    key_field: id
    wrap: items
    not_found_body:
      error: user_not_found
```

That produces six routes:

```text
GET     /users
GET     /users/{id}
POST    /users
PUT     /users/{id}
PATCH   /users/{id}
DELETE  /users/{id}
```

| Key | Required | Default | Description |
|---|---|---|---|
| `name` | yes | — | Resource name, also the store identity |
| `path` | no | `/<name>` | Base path of the collection |
| `source` | yes | — | `type` (`csv`/`json`) and `file` |
| `key_field` | no | `id` | Primary key, also the path parameter name |
| `methods` | no | all | Any of `list`, `get`, `create`, `update`, `delete` |
| `wrap` | no | — | Applied to the list route only |
| `not_found_status` | no | `404` | Applied to the single-resource routes |
| `not_found_body` | no | — | Applied to the single-resource routes |
| `delay_ms` | no | — | Applied to every generated route |
| `list_query` | no | `true` | Filtering, sorting and paging on the list route |
| `persist` | no | — | Keep writes across restarts (`true`, or a path) |

Resources are always stateful: they expand into `mutable` data sources sharing
one store, so a `POST` is visible to every other route of the resource.

Read-only resources are just a restricted method list:

```yaml
resources:
  - name: countries
    source:
      type: csv
      file: ./data/countries.csv
    methods: [list, get]
```

### Mixing with explicit routes

`routes:` and `resources:` can live in the same file. Declared routes are
registered first, so a hand-written `/users/me` still wins over the generated
`/users/{id}`:

```yaml
routes:
  - method: GET
    path: /users/me
    response:
      body:
        id: 1
        name: Mario

resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
```

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
| `PUT` | ignored | required | **Replaces** the resource with the request body |
| `PATCH` | ignored | required | **Merges** the request body into the resource |
| `DELETE` | ignored | required | Removes the matched resource, returns `{"deleted": true}` |

### Write rules

- The request body must be a JSON **object** — anything else returns `400`.
- `POST` requires `key_field` in the body (`400` if missing) and rejects an existing key with `409`.
- `PUT` replaces the resource: fields absent from the body are dropped. `PATCH` merges, preserving them. The key field survives both.
- `PUT` and `PATCH` cannot change `key_field` — attempting to do so returns `400`.
- When `PUT`, `PATCH`, or `DELETE` match nothing, the configured `not_found_status` / `not_found_body` are used (default `404`).

---

## Filtering, sorting and paging

A `mode: all` route with `list_query: true` reads a handful of query
parameters. The `resources:` shorthand turns this on for the list route, so it
works out of the box in zero-config mode; an explicit route has to ask for it.

| Parameter | Meaning |
|---|---|
| `?field=value` | Keep rows whose `field` equals `value` |
| `_sort=field` | Sort ascending; `_sort=a,b` sorts by several fields |
| `_order=desc` | Reverse the sort |
| `_limit=10` | Page size |
| `_page=2` | Page number, 1-based, used together with `_limit` |
| `_offset=20` | Skip rows, as an alternative to `_page` |

```bash
curl "http://127.0.0.1:8000/users?role=user&_sort=age&_limit=10&_page=2"
```

Every response carries `X-Total-Count` with the number of rows **before**
paging, so a client can render a pager. Numbers sort before text, so a column
holding both still comes back in a stable order. An unusable value — a
non-numeric `_limit`, an unknown `_sort` field — is ignored rather than
rejected.

A query parameter already used by `where` is not treated as a field filter.

Opt out on a resource with `list_query: false`.

---

## Keeping state across restarts

By default a `mutable` resource starts again from its data file on every run.
Add `persist` and writes are saved to a **separate** state file:

```yaml
resources:
  - name: users
    source:
      type: json
      file: ./data/users.json
    persist: true
```

- `persist: true` writes to `.mockyfast-state/<name>.json` next to the config.
- `persist: ./stato/utenti.json` writes wherever you say, as long as it stays
  inside the configuration directory.

The data file remains the **seed** and is never written to, so it stays
versionable and readable as documentation. Delete the state file to start over.
State files are written on every write and swapped into place atomically; add
`.mockyfast-state/` to your `.gitignore`.

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

---

## Response templates

Besides `{path_param}`, response bodies support `{{...}}` placeholders that read
the request or generate a value. They work in `body`, in `body_from` files, in
nested structures, and in object **keys**.

| Placeholder | Result |
|---|---|
| `{{uuid}}` | A random UUID v4 |
| `{{now}}` | Current UTC time, ISO 8601 |
| `{{now:%Y-%m-%d}}` | Current UTC time, `strftime` format |
| `{{timestamp}}` | Current Unix time, as a number |
| `{{randint:1:100}}` | Random integer in range |
| `{{randfloat:0:9.99}}` | Random float in range, 2 decimals |
| `{{choice:gold\|silver}}` | One of the options |
| `{{path.user_id}}` | Path parameter (same as `{user_id}`) |
| `{{query.page}}` | Query parameter |
| `{{header.x-client}}` | Request header, case-insensitive |
| `{{body.customer.email}}` | Request body, dotted path; list indexes work too |

```yaml
routes:
  - method: POST
    path: /orders/{order_id}
    response:
      status_code: 201
      body:
        id: "{{uuid}}"
        order: "{order_id}"
        created_at: "{{now}}"
        quantity: "{{randint:1:5}}"
        confirmation: "Order {order_id} for {{body.customer.email}}"
```

Two rules make the output predictable:

- **A string that is exactly one placeholder keeps the placeholder's type.**
  `"{{randint:1:5}}"` yields the number `3`, not the string `"3"`. Put the
  placeholder inside other text and you get a string.
- **An unknown or unresolvable placeholder is left as written.** A typo shows up
  in the response instead of raising, which is easier to spot while iterating.

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

### Matching operators

A matcher value can be an object of operators instead of a literal:

```yaml
routes:
  - method: POST
    path: /signup
    request:
      headers:
        Authorization: { matches: '^Bearer .{8,}$' }
      query:
        page: { one_of: ['1', '2'] }
      json:
        email: { matches: '@' }
        age: { gte: 18 }
        referral: { absent: true }
    response:
      status_code: 201
      body:
        ok: true
```

| Operator | Meaning |
|---|---|
| `equals` | Exact value (the default for a plain scalar) |
| `matches` | Regular expression, searched anywhere in the value |
| `contains` | Substring, or membership for lists |
| `one_of` | Value is in the given list |
| `present: true` | Key exists, whatever its value |
| `absent: true` | Key must not be present |
| `gt` `gte` `lt` `lte` | Numeric comparison |

Several operators in one object must all pass. An object counts as a matcher
only when **every** key is an operator, so a nested body object such as
`{"user": {"name": "Mario"}}` stays a structural comparison.

`mkf validate` compiles every `matches` regex, so a broken pattern is caught
before the server starts.

### What is compared

Matching is partial for `query` and `headers` (extra values in the request are ignored) and for object keys in `json`. Lists inside `json` must match exactly, including length.

`query` and `headers` compare as text, since that is what HTTP carries: `{ equals: 2 }` matches `?page=2`. Inside `json` the comparison is typed, so `{ equals: 5 }` matches the number `5` and not the string `"5"`.

---

## Latency and faults

`delay_ms` takes a fixed number of milliseconds, or a range for latency that
varies from call to call:

```yaml
routes:
  - method: GET
    path: /slow
    response:
      delay_ms: 3000
      body:
        ok: true

  - method: GET
    path: /jittery
    response:
      delay_ms:
        min: 50
        max: 800
      body:
        ok: true
```

The delay applies to every response the route produces, including not-found and
CRUD responses.

`fault` replaces the normal response some of the time, which is how you exercise
a client's retry and timeout handling:

```yaml
routes:
  - method: GET
    path: /flaky
    response:
      body:
        ok: true
      fault:
        probability: 0.2
        status_code: 503
        body:
          error: overloaded
```

| Key | Default | Meaning |
|---|---|---|
| `probability` | `1` | Chance the fault fires, from `0` to `1` |
| `status_code` | `500` | Status of the fault response |
| `body` | `{"detail": "Injected fault"}` | Body of the fault response |
| `delay_ms` | route delay | Time the fault takes; use it to simulate a timeout |

Declaring `fault: {}` is enough to fail every call with the defaults.

---

## Response sequences

Use `responses:` instead of `response:` to answer differently on successive
calls, which is what a polling client needs to be tested against:

```yaml
routes:
  - method: GET
    path: /jobs/{job_id}
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
```

```bash
curl http://127.0.0.1:8000/jobs/7   # 202 accepted
curl http://127.0.0.1:8000/jobs/7   # 202 running
curl http://127.0.0.1:8000/jobs/7   # 200 done
curl http://127.0.0.1:8000/jobs/7   # 200 done, the last entry repeats
```

Each entry is a full response object: `status_code`, `body`, `body_from`,
`delay_ms`, `fault` and templates all work inside one. The position is counted
**per route**, not per path parameter, and resets when the server restarts.

---

## Explaining a request

When a request does not reach the route you expected, `mkf explain` walks the
same decisions the server makes:

```bash
mkf explain mockyfast.yaml GET /users/me
```

```text
GET /users/me

   route #1  GET /users  -  path does not match
-> route #2  GET /users/{user_id}  -  matches
 ~ route #3  GET /users/me  -  would match, but an earlier route answers first

Answered by route #2: inline body
Path parameters: user_id=me
```

`->` marks the winner, `~` marks a route that would match but is unreachable.
Headers and a body can be supplied so matchers are evaluated too:

```bash
mkf explain mockyfast.yaml POST /login --body '{"username":"admin","password":"wrong"}'
mkf explain mockyfast.yaml GET '/orders?status=shipped' -H 'Authorization: Bearer abc'
```

The command exits non-zero when no route answers, so it can be used as a check.

---

## Behaviour notes

- **Route order matters.** `/users/me` declared after `/users/{user_id}` is never reached. Declare static paths first.
- **Non-mutable data files are re-read on every request.** Editing a CSV or JSON data source is picked up without restarting the server. `mutable` sources are the exception: they are read once at startup.
- **Referenced files must stay inside the config directory.** `body_from` and `data_source.file` cannot escape the folder containing the YAML file.
- **State is per-process.** The in-memory store is not shared between server restarts or between multiple processes.
- **CORS is permissive by default** (`Access-Control-Allow-Origin: *`, without credentials), because a mock server exists to be called from a dev server on another port. Turn it off with `serve --no-cors`.
- **Resource names must be unique.** The name identifies the shared store, so two resources claiming one name is an error rather than a silent merge. In zero-config mode this means `users.json` and `users.csv` cannot sit in the same folder.
- **The route index reports file names, not paths**, so it does not publish your directory layout.
- **`--reload` needs `watchfiles`**, which ships as a dependency. Without it uvicorn falls back to a reloader that only watches `*.py`, so config changes would go unnoticed; `serve --reload` refuses to start rather than pretend.
- **The index at `/` is generated only when no route claims that path.** Declare your own `GET /` and it takes over.

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
├─ data/                     seed data, versioned
│  ├─ users.csv
│  └─ users.json
├─ responses/                whole bodies for body_from
│  └─ users.json
└─ .mockyfast-state/         written by `persist`, gitignored
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

- missing `routes` or `resources`
- invalid route structure
- unknown HTTP methods, or paths not starting with `/`
- missing JSON or CSV files
- files referenced outside the configuration directory
- invalid `status_code`, `delay_ms` or `delay_ms` range
- invalid request matching config, including regular expressions that do not
  compile and operator arguments of the wrong type
- invalid CSV schema configuration
- incomplete `mutable` configuration (`key_field`, `resource_name`, `where`)
- invalid `resources:` entries, and duplicate resource names
- a route defining both `response` and `responses`, or an empty `responses`
- invalid `fault` settings
- `persist` without `mutable`
- unknown keys, which are almost always typos
- a key written but left empty, where a value is required
- an unsupported `version`

It also reports warnings that do not make a config invalid, such as a route
made unreachable by an earlier, more general one.

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

- OpenAPI import, to generate mocks from an existing spec
- an admin API to reset state and inspect received requests
- richer body matching (JSONPath)
- faker-style generators for names, emails and addresses
- capture real API responses into reusable mock files

Future exploration:

- record & replay proxy mode
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
