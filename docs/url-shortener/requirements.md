# Service requirements and traceability

These requirements implement the user's Python/SQLite scope, superseding the earlier
Java/PostgreSQL proposal. The interview assignment additionally requires governed,
stateful SDLC orchestration and scenario execution. This increment supplies only the
service baseline and scenario descriptions; it does not satisfy those broader goals.
No material conflict exists with the selected service behavior.

Paths below are relative to `url-shortener/`; tests are actual functions in
`tests/test_service.py` (parametrized functions exercise multiple cases).

| ID | Testable acceptance criteria | Code | Tests |
| --- | --- | --- | --- |
| US-001 | Valid absolute HTTP(S) creates 201; repeat destinations allowed; configured origin ignores Host | `schemas.CreateURL`, `service.create_link`, `api.create_app` | `test_create_redirect_stats`, `test_bad_urls` |
| US-002 | GET returns 302 and destination; unknown 404; HEAD 405 without increment | `service.redirect`, `api.follow` (nested in factory) | `test_create_redirect_stats` |
| US-003 | Aliases follow documented case/character/length/reserved rules; duplicate 409, enforced by DB | `schemas.Alias`, `RESERVED`, `models.Link`, `service.create_link` | `test_bad_alias`, `test_alias_conflict`, `test_concurrent_alias_and_clicks` |
| US-004 | Eight-character random codes; retry collision at most five times; exhaustion 503 | `service.generate_code`, `MAX_ATTEMPTS`, `create_link` | `test_collisions` |
| US-005 | Aware future expiration normalized to UTC; equality means expired 410; omission never expires | `schemas.CreateURL`, `models.UTCInstant`, `service.redirect` | `test_invalid_expiration`, `test_expiration_boundary`, `test_nonexpiring_restart_and_repeat_init`, `test_database_timestamps_are_explicit_utc` |
| US-006 | Atomic count per successful GET; no missing/expired/HEAD count; stats readable after expiry; write failure blocks redirect | `service.redirect`, `get_stats` | `test_create_redirect_stats`, `test_expiration_boundary`, `test_concurrent_alias_and_clicks`, `test_locked_database_and_recovery` |
| US-007 | Errors share error/code/message envelope; validation 422, no raw URL or DB detail | `errors.ServiceError`, API exception handlers | `test_bad_urls`, `test_locked_database_and_recovery`, `test_alias_conflict` |
| US-008 | Health checks file/schema/query readiness; docs and OpenAPI accessible | `database.check_ready`, `api.create_app` | `test_create_redirect_stats`, `test_locked_database_and_recovery`, `test_missing_revision_and_schema` |
| US-009 | File DB persists across apps; explicit Alembic init repeatable; start never creates schema | `database.initialize`, `check_ready`, CLI | `test_migration_and_config`, `test_nonexpiring_restart_and_repeat_init`, `test_cli_init_from_other_directory` |
| US-010 | Predictable path/override; bounded lock wait; tests isolated from default DB | `config.Settings`, `database.make_engine` | `test_migration_and_config`, `test_locked_database_and_recovery`; all fixtures pass temporary paths |
| US-012 | Same-service responsive UI creates/copies links, accepts local-time expiration, and looks up stats without counting clicks; local assets, no new dependencies | `web/index.html`, `web/app.js`, `web/app.css`, `api.create_app` | `test_ui_assets_and_api_coexist`; browser checks in `testing.md` |
| US-011 | Fresh local Python setup, no credentials/services, runnable docs and future-agent guidance | `pyproject.toml`, `requirements.lock`, README, AGENTS | Clean-environment install and CLI smoke documented in `testing.md` |

Assumptions: one local machine, short write transactions, editable checkout install,
HTTP(S) validation without reachability checking, public stats, no link editing or
removal. Query strings may contain secrets and are stored as part of the destination;
protect the SQLite file. URLs are never fetched by the service. No IP/user-agent
columns exist. Counts represent committed server redirects, not confirmed browser visits.

Exclusions: a separate frontend build/server, auth, queues, caching, deployment infrastructure, live agentic
tests and production readiness. Public hosting requires separate abuse, access,
privacy, transport and concurrency design. No unresolved questions block this
baseline. Windows/macOS execution remains unverified in this Linux environment.

See [architecture](architecture.md), [testing](testing.md) and
[future scenarios](../../demo/url-shortener-scenarios.md).

The follow-up user request adds the bundled UI, superseding the original exclusion
of a frontend. Existing API and stored-data contracts are unchanged.
