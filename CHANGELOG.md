# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `mkf schema` prints a JSON Schema of the configuration format, generated from
  the same models `mkf validate` runs. `mockyfast.schema.json` is published in
  the repository, so an editor can be pointed at it with a
  `# yaml-language-server: $schema=` modeline or a `yaml.schemas` entry in
  `.vscode/settings.json` and offer completion and live validation.
- An optional `version: 1` at the top of a configuration, so the format can
  change later without breaking files written today. A version this build does
  not know is refused rather than misread.
- Every YAML example in the README, and the ten the first published README
  documented, are now loaded by the test suite, so a documented configuration
  cannot stop being a working one.

- `mkf explain CONFIG METHOD PATH` reports which route answers a request and why
  each other one does not, naming the failing query parameter, header or body
  field. Accepts `-H` headers and a `--body`, and exits non-zero when nothing
  matches.
- `responses:` answers differently on successive calls, for testing polling
  clients. The last entry repeats once the sequence runs out.
- `fault` replaces a response with a failure, with an optional `probability`,
  `status_code`, `body` and its own `delay_ms` for simulating timeouts.
- `delay_ms` accepts a `{min, max}` range for latency that varies per call.

- Response templates: `{{uuid}}`, `{{now}}` (with an optional `strftime`
  format), `{{timestamp}}`, `{{randint:a:b}}`, `{{randfloat:a:b}}`,
  `{{choice:a|b}}`, and scoped lookups `{{path.x}}`, `{{query.x}}`,
  `{{header.x}}`, `{{body.a.b.0}}`. A string that is exactly one placeholder
  keeps the placeholder's type; an unresolvable one is left as written.
  Placeholders now also render in object keys, which `{param}` never did.
- Filtering, sorting and paging on `mode: all` routes via `list_query`:
  `?field=value`, `_sort`, `_order`, `_limit`, `_page`, `_offset`, plus an
  `X-Total-Count` header carrying the pre-paging total. On by default for the
  list route of a `resources:` entry, opt-in for an explicit route.
- `persist` keeps a mutable resource's writes across restarts in a separate
  state file, leaving the data file as an untouched seed.
- Matching operators for `request.query`, `request.headers` and `request.json`:
  `equals`, `matches`, `contains`, `one_of`, `present`, `absent`, `gt`, `gte`,
  `lt`, `lte`. `mkf validate` compiles every `matches` pattern.

- Zero-config mode: `mkf serve ./data` derives a full CRUD API from a folder of
  `.json`/`.csv` files, or from a single data file, with no YAML at all. The key
  field is detected from the data (`id` when present, else the first column).
- `resources:` shorthand that expands one declaration into the five CRUD routes.
  The bundled example config went from 91 lines to 10 for the same six routes.
- `mkf init --from-data <path>` writes the config a data folder would produce,
  so zero-config mode is a starting point rather than a dead end.
- `mkf serve --reload` restarts when the config or its data files change.
- A generated route index at `/`, as JSON or as an HTML page for browsers.
  Disable it with `serve --no-index`, or declare your own `GET /`.
- `mkf serve` prints the route table on startup.
- `mkf validate` reports warnings for routes made unreachable by an earlier,
  more general route.
- `watchfiles` is now a dependency: without it uvicorn's fallback reloader only
  watches `*.py`, so `--reload` would run but never notice a config change.
  `serve --reload` now refuses to start rather than silently do nothing.

- Permissive CORS headers by default, so a browser app on another port can call
  the mock. Disable with `serve --no-cors`.

### Fixed

- `mkf validate` accepted a JSON data source whose file was not a root list of
  objects, and the route then answered `500` to every request. The file is now
  read the way the server reads it, so the problem is reported before the
  server starts, naming the route. `body_from` is unaffected: a whole response
  body may be any JSON value.
- In zero-config mode the same file crashed key-field detection with a
  `KeyError` that reached the user as `Invalid configuration: 0`.

- A client could redirect where `body_from` and `data_source.file` resolve from
  by passing `?_config_path=...`. The route group and config path were handed to
  the endpoint as parameter defaults, and FastAPI turns anything in an endpoint
  signature into a request parameter, so both were exposed as query parameters
  and appeared in the generated OpenAPI schema. The path confinement added
  earlier was relative to that value, so it could be sidestepped. Handlers are
  now built by a factory and capture their state lexically.

- Two resources sharing a name silently served one another's data, because the
  name identifies the store. Duplicate names are now rejected, including the
  zero-config case where `users.json` and `users.csv` both wanted `/users`.
- A resource's data file was read once per generated route, so a six-route
  resource opened it six times at startup. It is now read once.

### Changed

- Configuration validation is now a set of Pydantic models rather than 450 lines
  of hand-written checks, which is what makes a publishable JSON Schema
  possible. Messages keep their wording, and gain a key path that points at the
  entry at fault: an error inside a `responses:` sequence now reads
  `'responses.1.status_code' in route #1` instead of naming the route only.
- A missing key and a key of the wrong type no longer share a message. A
  resource without a `source` reported `'source' in resource #1 must be an
  object`, which described something that was not there; it now reports
  `'source' in resource #1 is required`.
- An unknown key is rejected instead of ignored. `stauts_code: 201` used to
  leave the route answering `200` with no warning, and now fails `validate`
  naming the key.
- A key written but left empty is rejected wherever a value is required.
  `mutable:`, `wrap:` or `request:` with nothing after them used to pass
  validation and then be treated as absent.

- `PUT` now replaces a mutable resource and `PATCH` merges into it, instead of
  both merging. The key field survives either way.
- The route index reports data file names rather than their paths, so it does
  not publish the directory layout of the machine running it.
- `routes:` is no longer required when `resources:` is present. The error for a
  config with neither now reads "Missing 'routes' or 'resources' key".

## [0.2.0]

### Added

- `PATCH` support on mutable data sources (same merge semantics as `PUT`).
- Config validation for `response.status_code` (must be an integer between 100 and 599).
- Config validation for `method` (must be a known HTTP method) and `path` (must start with `/`).
- Config validation for mutable data sources: `resource_name` is now required, and
  `PUT` / `PATCH` / `DELETE` routes must declare a `where`.
- `409 Conflict` when a `POST` would create a resource whose `key_field` already exists.
- `400 Bad Request` when a write body is malformed JSON, is not a JSON object, is missing
  `key_field` on create, or tries to change `key_field` on update.
- Files referenced by `body_from` and `data_source.file` are confined to the configuration
  directory.
- CI workflow running lint and tests on Python 3.10–3.13.
- `ruff` lint configuration and `pytest-cov` dev dependency.
- Regression tests for mutable resources and the new validation rules (64 → 95 tests).

### Changed

- `mode` is no longer required on mutable write routes, where it carried no meaning.
- `PUT` / `PATCH` / `DELETE` now honour the configured `not_found_status` and
  `not_found_body` instead of a hardcoded `404`.
- Write routes resolve the target resource through the `where` field rather than always
  through `key_field`, so a resource can be addressed by a non-primary field.
- The mutable request handling was extracted from the route closure into dedicated
  functions with a single response exit point.

### Fixed

- `delay_ms` was ignored on mutable routes and on not-found responses; it now applies to
  every response a route produces.
- A mutable data source without `resource_name` keyed its store by route path, so
  `/users` and `/users/{user_id}` silently held separate copies of the data.
- A malformed or non-object JSON write body returned `500` and could corrupt the store,
  making later writes fail with `500`.
- `status_code` values that were not valid integers passed validation and produced a `500`
  at request time.
- `PUT` could rewrite the primary key of a resource.
- `PATCH` on a mutable route returned `200` with unmodified data instead of updating.
- Duplicate import in `mockyfast.config`.

## [0.1.0]

Initial release: YAML-configured mock server with inline bodies, external JSON bodies,
CSV and JSON data sources, request matching, path params, and `delay_ms`.
