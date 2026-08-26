# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

- Two resources sharing a name silently served one another's data, because the
  name identifies the store. Duplicate names are now rejected, including the
  zero-config case where `users.json` and `users.csv` both wanted `/users`.
- A resource's data file was read once per generated route, so a six-route
  resource opened it six times at startup. It is now read once.

### Changed

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
