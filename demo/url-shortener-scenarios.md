# URL shortener baseline and future agent exercises

These are walkthrough specifications, not completed live agentic demonstrations.
The orchestrator and its dependencies have not been changed.

## Baseline: create, visit, inspect, restart

Use the service [fresh setup](../url-shortener/README.md), choosing a new disposable
`SHORTENER_DB_PATH` if running repeatedly. Run its three copy-paste HTTPX commands:
create alias `interview` (201), GET it without following redirects (302), inspect
stats (200, clicks=1). Stop/restart the server and inspect stats again: clicks=1.
Repeat the redirect: clicks=2. Repeat creation: 409. Run `python -m pytest -q`.
Requirements: US-001, US-002, US-003, US-006, US-009, US-011.
Review: do not point the exercise at an existing user's database or public server.

The same baseline can be exercised at `/`: create `interview`, copy the result,
select **View this link’s statistics**, then use the code lookup after restart.
Copying and looking up a code should keep its count unchanged (US-012).

## Future feature — NOT implemented: disable a link

User requirement: “Allow me to disable a short link without deleting its history.”
Before implementation resolve who may disable links, authentication expectations,
whether re-enabling is allowed, and what status disabled redirects should return.
Tentative acceptance criteria for human review: an authorized action disables a
link; disabled links do not redirect or count clicks; existing stats persist;
unknown codes retain 404; non-disabled behavior is unchanged. A new requirement ID
must be assigned after those decisions, with impacts to US-002/005/006/007/009.

Likely files: `src/shortener/{api,schemas,service,models}.py`, a new migration,
`tests/test_service.py`, README and the requirement/architecture/decision documents.
Decompose into contract/security decision, migration, rules/routes, tests and docs;
implementation depends on the reviewed contract and data design. Verification:
`python -m pytest -q`, `python -m pip check`, plus new populated-schema upgrade and
authorization tests. Human review: API/security/storage implications, authorization,
data preservation and downgrade risk. No deployment permission is implied.

## Regression investigation — no bug planted: missing click counts

User report: “Repeated visits sometimes don't increase analytics under concurrency.”
Relevant IDs: US-002, US-006, US-010. First clarify whether these were GETs reaching
the server, browser cache visits, HEAD probes, expired links, or 503 responses.
Collect sanitized statuses and counts, never full private destinations or visitor data.

Inspect `service.redirect`, `api.create_app`/nested `follow`, `database.make_engine`
and `tests/test_service.py`. Reproduce with a temporary DB; inspect atomic UPDATE,
commit/error flow and no-store response header. Do not assume the current code is
broken or inject a bug. Acceptance: N successful concurrent GET responses yield N
increments; missing/expired/HEAD and rolled-back locked requests yield zero;
no lost updates; existing redirects and persistence still pass.

Verification from `url-shortener/`:

```sh
python -m pytest -q tests/test_service.py -k "concurrent or locked or expiration or create_redirect"
python -m pytest -q
```

Human review: any change to count semantics, retry behavior, API failures, storage
or log content. Return evidence and an explanation even if no change is warranted.
A debugging result does not authorize data reset or public deployment.
