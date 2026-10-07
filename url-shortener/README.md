# Local Python URL shortener

Small FastAPI service with persistent SQLite storage, custom aliases, UTC expiration,
and aggregate click counts. Python 3.11+ (verified on 3.12); SQLite 3.35+ is needed
for UPDATE RETURNING. No API keys, external services, or orchestrator setup required.
This is learning/interview code for a single machine, not a high-traffic deployment.

## Fresh-machine setup

Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/).
On Windows enable the installer option to add Python to PATH.
Open a terminal in the resulting repository folder, then use one block below.
Internet is needed for this first dependency installation only.

macOS/Linux:

```sh
cd url-shortener
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m shortener init-db
python -m shortener serve
```

Windows PowerShell:

```powershell
cd url-shortener
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m shortener init-db
python -m shortener serve
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of
`python` for every command; activation is only a convenience and requires no
system policy changes. Verify `python --version` is at least 3.11.

Open the [URL shortener UI](http://127.0.0.1:8000/) to create links and view statistics.
You can also use [Swagger UI](http://127.0.0.1:8000/docs) or
[health](http://127.0.0.1:8000/health). OpenAPI: `/openapi.json`; ReDoc: `/redoc`.
Stop with Ctrl+C. Restart with `python -m shortener serve` in the same environment.
Do not delete the database; links survive restarts. Repeating `init-db` is safe.
Starting the server does not create or upgrade schema.

Direct dependencies are pinned in `pyproject.toml`. For the fully pinned tested
transitive dependency set, replace the install command with:

```sh
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation -e ".[dev]"
```

The lock includes build tooling. Keep it synchronized when changing dependencies;
see [testing](../docs/url-shortener/testing.md). No Make, uv, or shell script is needed.

## Use the UI

Visit `http://127.0.0.1:8000/` after starting the service. Paste a destination,
optionally choose a custom alias and expiration, and click **Create short link**.
Use **Copy** to copy the result, or select it manually if clipboard access is unavailable.
**View this link’s statistics** loads its click count, destination and timestamps.
To look up a previously created link, enter its code/alias in the statistics panel.
There is no listing of all links; keep the codes you want to inspect.

Expiration input and displayed dates use your browser's local timezone; the UI
sends an explicit UTC instant to the existing API. The Active/Expired badge is
computed at lookup time using the browser clock; the server remains authoritative
for redirects. Repeat the lookup to refresh counts/status. Clicking the short link
opens its destination and increments clicks; creating/copying/looking up does not.

The responsive UI is bundled HTML/CSS/JavaScript, served by the same FastAPI
process. No Node.js, frontend installation, CDN or network access is required.
JavaScript is required. No link history is saved in browser storage. API docs are
still available separately. This UI does not add authentication or private analytics.

## Try the API

With the service running, paste this in a second activated terminal (both platforms):

```sh
python -c "import httpx; r=httpx.post('http://127.0.0.1:8000/api/urls', json={'destination':'https://example.com/guide','alias':'interview'}); print(r.status_code, r.json())"
python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/interview', follow_redirects=False); print(r.status_code, r.headers.get('location'))"
python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/urls/interview/stats'); print(r.status_code, r.json())"
```

Creation returns 201, for example (creation time varies):

```json
{"code":"interview","short_url":"http://127.0.0.1:8000/interview","destination":"https://example.com/guide","created_at":"2030-01-01T00:00:00Z","expires_at":null,"clicks":0}
```

Redirect prints `302 https://example.com/guide`. Stats returns 200 with the same
fields and `clicks: 1`. These commands do not fetch the destination. Repeating
creation with that alias returns 409; omit `alias` to generate a new eight-character
code, even for an already-shortened destination.

In `/docs`, POST `/api/urls` also accepts `expires_at`, for example
`"2099-01-01T00:00:00+05:30"`. It must be timezone-aware and strictly after creation.
It is normalized to UTC; omission or null means never expires. At `now >= expires_at`
a redirect returns 410. Stats remain accessible after expiration.

Aliases are case-sensitive, 3–32 ASCII letters, digits, `_` or `-`. Reserved names:
`api`, `health`, `docs`, `redoc`, `openapi.json` (the last also fails the character rule).
Destinations must be absolute HTTP/HTTPS URLs, up to 2048 characters, without
embedded credentials. Pydantic normalizes URLs, including a slash on bare origins.
Unknown JSON fields are rejected. The service never fetches/previews destinations.

All application errors use `{"error":{"code":"...","message":"..."}}`:

| Situation | Status |
| --- | --- |
| Successful GET redirect | 302, with `Cache-Control: no-store` |
| Unknown code or unknown stats code | 404 |
| Existing custom alias | 409 |
| Expired GET redirect | 410 |
| Invalid input, reserved alias, past/naive expiration | 422 |
| HEAD on a short code | 405; no clicks counted |
| Database busy/unavailable or generated-code retries exhausted | 503 |

Each successful GET redirect counts, including repeated visits and bots. Missing,
expired and HEAD requests do not count. Stats reads do not count. Only aggregate
counts are stored, never IP addresses or user agents. If the click update cannot
commit, no redirect is issued (503). A committed redirect can still fail to reach
the client, so counts measure server-issued redirects, not confirmed page views.

## Configuration and database

No `.env` is required or loaded. Set environment variables before running CLI commands:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SHORTENER_DB_PATH` | `url-shortener/data/shortener.db` | SQLite file; relative overrides resolve from service root, not working directory |
| `SHORTENER_BASE_URL` | `http://127.0.0.1:8000` | Trusted public HTTP(S) origin, no path, query or credentials |
| `SHORTENER_LOCK_TIMEOUT` | `5` | SQLite lock wait seconds, greater than 0 and at most 30 |

The supported installation is editable from this checkout. The default service
root is derived from `src/shortener/config.py`, independent of terminal directory.
`init-db` creates parent directories and applies Alembic migrations. No populated
DB is distributed; database/journal/WAL files are ignored. SQLite uses default
rollback-journal mode; this service does not enable WAL. SQLite 3.35+ ships with
normal recent Python builds; check `python -c "import sqlite3; print(sqlite3.sqlite_version)"`.

Port example, macOS/Linux:

```sh
export SHORTENER_BASE_URL=http://127.0.0.1:8001
python -m shortener serve --port 8001
```

PowerShell:

```powershell
$env:SHORTENER_BASE_URL = "http://127.0.0.1:8001"
python -m shortener serve --port 8001
```

Set `SHORTENER_DB_PATH` the same way to an explicit absolute file path.
Changing the base URL does not change the listening address; `--host` and `--port`
control that separately. Host headers never determine generated links.

`GET /health` returns 200 only if the file exists, Alembic is at the packaged head,
and the expected link columns can be queried. It returns 503 on failed checks.
It is a read-readiness check, not a disk-capacity or write-permission guarantee.
At startup those checks must pass or the server refuses to start with init guidance.

## Tests and troubleshooting

From `url-shortener/` with its environment active:

```sh
python -m pytest -q
python -m pip check
```

Tests use only temporary file databases, no internet or LLMs. See
[testing](../docs/url-shortener/testing.md) for executed checks and coverage.

- Python missing: install Python, reopen the terminal; try `python3` on Unix or `py -3` on Windows.
- Port busy: stop the previous process, or use the port/base-URL example above.
- Installation fails: confirm Python version, active environment, internet/proxy access,
  and pip availability (`python -m pip --version`). Do not install into the orchestrator environment.
- Database permissions: use a writable local directory; SQLite needs write access to
  both the file and its parent directory for journal files.
- Missing migrations: verify the configured path, stop the service, run `init-db`, restart.
  Do not manually stamp a revision to hide missing schema.
- Database locked: stop extra writers/DB browsers, wait for transactions to finish,
  retry; do not delete journal files. See the [runbook](../docs/url-shortener/runbook.md).

Localhost links work only on the machine running this service. Binding a network
interface and changing the public origin is a separate hosting decision requiring
review. There is no authentication, rate limiting, abuse/phishing prevention, or
private analytics. Codes can be enumerated; analytics disclose destinations.
SQLite serializes writers; redirects themselves write. Network filesystems and
high-traffic distributed deployment are outside scope. Swagger/ReDoc use CDN assets,
so their visual UI may need internet; the API, OpenAPI JSON and tests work offline.

[Requirements](../docs/url-shortener/requirements.md) ·
[Architecture](../docs/url-shortener/architecture.md) ·
[Decisions](../docs/url-shortener/decisions.md) ·
[Agent instructions](AGENTS.md) · [Demo](../demo/url-shortener-scenarios.md)
