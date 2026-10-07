# Local operations and debugging

Start from the [README](../../url-shortener/README.md). Use the service environment,
not the orchestrator environment. Never read unrelated credentials.

## Diagnose safely

Collect Python/SQLite versions, OS, service version, sanitized configuration (omit
private paths/hostnames), HTTP status/error code and reproduction steps using
`https://example.com`. Run `python -m pip check` and `python -m pytest -q`.
Do not share database files, raw destination URLs/query strings, request bodies,
SQL parameter logs or visitor information. CLI access logging is intentionally off.

- Startup: confirm `SHORTENER_DB_PATH` is the expected file and the parent is writable;
  stop server and run `python -m shortener init-db`. Check port conflict separately.
- Migration: inspect source revision chain under `src/shortener/migrations/versions/`.
  Read `SELECT version_num FROM alembic_version` with a local SQLite viewer if needed.
  Do not stamp/rewrite migration history to suppress errors. Health requires packaged head.
- Database locked/503: close DB viewers/writers and duplicate service processes;
  retry after short transactions finish. Timeout is bounded, not an infinite retry.
  Verify local disk, directory permissions and available space. Do not delete journals.
- Redirect: use HTTPX with `follow_redirects=False`; 404 is unknown, 410 is expired.
  Check alias capitalization. The service does not verify destination availability.
- Expiration: inspect stats UTC timestamp and host clock; equality is expired.
  Use injected-clock tests rather than changing system time. Stats remain readable.
- Analytics: GET increments; HEAD (405), stats, missing and expired links do not.
  Check for repeated browser/bot requests. A failed commit returns 503, no redirect.
  A disconnect after commit may still be counted; counts are not unique visitors.

## Backup and restore

1. Stop every service process and DB writer. Confirm they have exited.
2. Copy the SQLite file to a separate backup path using the OS file manager or
   Python `shutil.copy2`. Keep the source intact. Verify the copy can be opened and
   run SQLite `PRAGMA integrity_check` against the copy before relying on it.
3. This service uses rollback journal mode. Do not copy during writes. If WAL was
   enabled externally, use SQLite's backup API after stopping writers, or preserve
   the database and its `-wal`/`-shm` companions as a consistent set; never discard
   a WAL file because it may contain committed data. Resolve journal recovery first.
4. To restore, stop all processes, preserve the current DB as another backup, then
   copy the chosen verified backup to the configured path. Confirm revision and
   compatibility with the running code before serving. Ensure file permissions.

## Schema upgrades and rollback

Review new migrations, back up first, stop writers, run `init-db`, check health and
exercise a disposable test link. For future versions, test upgrades on a copy of
realistic prior data. Never rewrite an applied migration.

There is intentionally no automatic downgrade CLI. A migration downgrade can drop
columns/rows; code rollback alone may be incompatible with upgraded storage.
Review downgrade SQL and data-loss risks, or restore a compatible verified backup
with the corresponding code version. Database rollback is not automatically safe.

## DESTRUCTIVE local reset — only with explicit user intent

A reset loses every stored link and click count. Prefer a new `SHORTENER_DB_PATH`
for experiments. Only if the user explicitly requests a reset: stop all processes,
confirm the exact configured file, make and verify a backup, deliberately remove
that file using the OS, then run `python -m shortener init-db`. Do not delete
journals from an active/recovering database. Agents must never perform this sequence
automatically or as a fix for migration errors.

## UI troubleshooting

Open `/` on the same service; no frontend server is needed. If the page is unstyled
or controls do not work, verify `/api/ui/app.css` and `/api/ui/app.js` return 200,
JavaScript is enabled, and the installed package includes `shortener/web/` files.
Restart after Python route changes; reload after editing assets. Check browser
console errors without sharing private request bodies or destinations. Clipboard
access can be denied outside secure/loopback origins; manually copy the displayed
link. Stats do not auto-refresh, and the Active/Expired badge uses the browser clock.
