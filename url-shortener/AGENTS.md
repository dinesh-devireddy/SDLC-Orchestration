# Scope: url-shortener only

This is the offline, local service baseline. Do not modify the sibling orchestrator,
read unrelated credentials, call LLM APIs, or use production resources.
Implementation authorization does not grant deployment authorization.

## Entry points and commands

Work in `url-shortener/`, with its own `.venv` activated. Python 3.11+.

- Install: `python -m pip install -e ".[dev]"`
- Reproduce dependencies: `python -m pip install -r requirements.lock`, then
  `python -m pip install --no-build-isolation -e ".[dev]"`
- Build wheel if needed: `python -m pip wheel --no-deps --no-build-isolation . -w dist`
- Test: `python -m pytest -q`
- Dependency check: `python -m pip check`
- Initialize/migrate: `python -m shortener init-db`
- Run: `python -m shortener serve`; stop with Ctrl+C.

Set `SHORTENER_DB_PATH` to a disposable temporary path for experiments, never a
user's database. Never delete/reset a database automatically.

`src/shortener/__main__.py` is the CLI; `api.create_app` creates the app and request
sessions; `schemas.py` defines input/output; `service.py` owns business behavior;
`models.py` defines storage and UTC serialization; `database.py` manages engines,
readiness and migrations; `config.py` resolves settings; `errors.py` defines safe
business errors. `web/index.html`, `web/app.css` and `web/app.js` provide the
same-origin UI at `/`; assets use `/api/ui/` to avoid claiming new aliases.
Keep UI assets dependency-free, use textContent for untrusted data, and retain the
page CSP. Update package-data when adding bundled files. `tests/test_service.py` exercises the public contract and storage.

## Changes

Keep synchronous SQLAlchemy and short transactions. Use injected clocks/code
factories in deterministic tests. Use temporary file DBs and real migrations,
never ORM create_all. Keep errors sanitized and destination query strings out of
logs. Preserve rollback on every error and atomic click updates.

For endpoints, add schemas and routes in their existing modules; put business
rules in service.py. Test status, response shape, failure handling and analytics.
Update README, requirement traceability, architecture, decisions and testing notes
when their claims change. Do not add abstraction layers without a concrete need.

For schema changes, add a new file under `src/shortener/migrations/versions/` with
unique `revision`, prior `down_revision`, and upgrade/downgrade functions. Never
rewrite applied migrations. Test fresh migration and upgrade of a populated prior
schema on temporary files, including data preservation. Review downgrade safety;
a downgrade that drops data is not an automatic rollback solution.

API contracts, stored-data changes, security behavior, dependency updates and
all destructive operations need human review before merge/release. Prepare code,
tests, impact notes and concrete review material within authorized implementation
scope; do not invent approval or silently deploy. Destructive operations require
explicit user intent. Never modify a user's data as a debugging shortcut.
