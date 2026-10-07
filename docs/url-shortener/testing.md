# Testing and verification

Run from `url-shortener/` with its own environment activated:

```sh
python -m pytest -q
python -m pip check
```

No network service, paid API, LLM, Docker or external database is required. TestClient
runs the ASGI app in-process. No test follows an external redirect. Tests use real
SQLite files under pytest `tmp_path`; `tests/conftest.py` rejects SQLAlchemy
connections outside each test's directory before SQLite can open/create a file.
The CLI subprocess test explicitly passes a temporary `SHORTENER_DB_PATH`.
The default `data/shortener.db` is neither initialized nor modified by tests.

## Layers and traceability

The small suite combines API and real storage tests instead of mocking the database.

| Layer | What it proves | Tests / requirements |
| --- | --- | --- |
| API contract | Status codes, normalization, safe error envelope, configured origin, docs | `test_create_redirect_stats`, `test_bad_urls`, `test_bad_alias`, `test_alias_conflict`, `test_generated_code_and_error_contract`; US-001/002/003/007/008 |
| Deterministic business behavior | Expiration before/equal/after boundary, timezone conversion, no expiry, retry bounds | `test_invalid_expiration`, `test_expiration_boundary`, `test_nonexpiring_restart_and_repeat_init`, `test_collisions`; US-004/005 |
| Real storage | Fresh Alembic schema, repeat init, UTC text, readiness, restart persistence | `test_migration_and_config`, `test_missing_revision_and_schema`, `test_schema_drift_is_not_ready`, `test_database_timestamps_are_explicit_utc`, `test_nonexpiring_restart_and_repeat_init`; US-005/008/009/010 |
| Concurrency/failure | One winner among 16 competing aliases; 40 atomic redirects; bounded lock failure rolls back and recovers | `test_concurrent_alias_and_clicks`, `test_locked_database_and_recovery`; US-003/006/010 |
| CLI | Initialization from another working directory, explicitly overridden temporary DB | `test_cli_init_from_other_directory`; US-009/011 |

All named tests are in `url-shortener/tests/test_service.py`. See
[requirements](requirements.md) for the complete acceptance matrix.

The fixture injects a mutable clock initialized to `2030-01-01T00:00:00Z`; expiration
checks do not sleep. Collision tests inject a deterministic code factory. Normal
production calls use `utc_now` and `secrets` randomness. Concurrency tests assert
outcomes rather than execution order. A short timeout in the lock test keeps it fast.

Fresh schema is created only with Alembic. Current migration head is `0001`.
Repeated initialization preserves rows/counts. For the next migration, add a test
upgrading a populated previous schema and verify data preservation, as well as a
fresh database test. The current suite does not imply future upgrades are safe.

## Executed on 2026-10-06

Linux, Python 3.12.3:

- Fresh service virtual environment: `python -m pip install -e ".[dev]"` succeeded.
- Final suite: **33 passed**; one dependency deprecation warning from Starlette's
  reference to AnyIO's old BlockingPortal alias. No test failure.
- Separate clean temporary environment: installed `requirements.lock`, then
  `python -m pip install --no-index --no-build-isolation -e ".[dev]"` successfully.
- Re-ran the complete suite in the clean environment: **33 passed**, same single
  dependency warning.
- `python -m pip check`: no broken requirements in the clean environment.
- Built a wheel with `python -m pip wheel --no-index --no-deps --no-build-isolation . -w /tmp/shortener-wheel`;
  inspected the archive to confirm migration env, initial revision and template are included.
- Actual Uvicorn localhost smoke, using that clean environment and a temporary DB:
  ran init twice, created a link (201), redirected (302), read stats (1), gracefully
  stopped and restarted the server, verified persisted count (1), redirected again
  and observed count 2. Health, docs HTML and OpenAPI returned 200. Server stopped
  at completion. No destination was fetched, and no default database was created.

Environment constraints: package downloads initially failed under sandbox DNS rules;
installation succeeded with approved network access. TestClient stalled in its
cross-thread event-loop startup under this sandbox; the suite passed outside that
sandbox. Local socket smoke likewise ran outside the sandbox. Normal tests remain
in-process/offline. Git metadata was unavailable, so no git diff/status verification
was possible. No orchestrator execution or live agentic testing was performed.

Unverified: Windows PowerShell/macOS execution, other Python versions, visual
Swagger CDN availability offline, long-duration load behavior, security audit,
public hosting and database recovery under power loss. Commands are written for
both shell families, but only Linux was executed. This is not a production-readiness
or broad platform-certification claim.

## Dependency maintenance

`pyproject.toml` pins direct/build dependencies; `requirements.lock` pins the tested
transitive set plus setuptools/wheel and conditional Windows colorama. It is a
version lock, not an artifact-hash lock. Review dependency changes, resolve in a
new service-only environment, run the suite and `pip check`, update the lock without
absolute editable paths, and validate on intended target platforms. Do not copy
or modify the orchestrator's environment or dependencies.

For a manual repeat of the localhost smoke, use the README API examples and stop/
restart sequence in the [demo](../../demo/url-shortener-scenarios.md). Use a new
temporary database path to avoid changing a user's stored links.

## UI follow-up verification (2026-10-06)

- Full regression suite: **34 passed**, same dependency deprecation warning.
- Added `test_ui_assets_and_api_coexist`: home/assets, security headers and a
  non-reserved alias continue to work. It proves serving/integration, not JS behavior.
- Browser checked creation, copy-success feedback, stats with zero clicks, duplicate
  alias 409, missing-code 404, and a local-time expiration round trip. No browser
  console errors were reported. Inspected desktop (1280px) and mobile (390px) layouts.
- Browser verification used `/tmp/shortener-ui-preview.db` on loopback port 8765,
  not the default/user database. The UI adds no third-party asset requests.
- Browser coverage is manual, not an automated end-to-end suite. Clipboard-denial,
  unusual timezone/DST input and cross-browser behavior remain unverified.
