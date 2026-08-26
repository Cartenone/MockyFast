# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
