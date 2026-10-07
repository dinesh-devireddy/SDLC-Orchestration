# Decisions

These record implementation choices, not external approvals.

| Context | Choice | Rationale and tradeoff |
| --- | --- | --- |
| Interviewer setup must be small | FastAPI/Pydantic, synchronous SQLAlchemy, Uvicorn | Validation/OpenAPI and readable transactions; blocking DB access runs in FastAPI's sync worker threads, no async DB complexity |
| No database server allowed | Built-in SQLite file at service-root `data/shortener.db`, environment override | Persistent and portable; one writer at a time, unsuitable for distributed high traffic |
| Schema changes must be reviewable | Explicit Alembic `init-db`; startup validates head and columns | Repeatable initialization without silent schema changes; requires a separate operator step |
| Codes need uniqueness | Eight cryptographically random alphanumeric characters; PK constraint; five attempts | Simple ~48-bit space and bounded work; enumeration is still possible, not an access control mechanism |
| Custom aliases can race | Insert then handle constraint violation with rollback | Database arbitrates concurrent requests; no unsafe precheck-only logic |
| Redirect should be temporary | 302 with no-store; HEAD 405 | Counts repeated GET requests reaching server and avoids redirect caching where honored; no guarantee browsers/proxies comply |
| SQLite lacks aware datetime storage | Fixed-width UTC ISO text with microseconds; expires at equality | Readable and lexically ordered; serializer and migration must stay aligned |
| Analytics must avoid lost updates | Atomic conditional increment and commit before redirect | No lost increments; write outages block redirect with 503; a client disconnect after commit can still count |
| Readiness should be useful | File, migration head and expected-column read query | Detects missing/outdated schema; cannot guarantee future writes or free disk space |
| Minimize secret exposure | Generic validation/DB errors; CLI disables access logs; no destination fetching | Less detailed client diagnostics; operators use sanitized repros/tests rather than raw SQL logs |

See [requirements](requirements.md) for scope and [runbook](runbook.md) for operational tradeoffs.

## Follow-up: browser UI

The user requested a UI after the API baseline. Bundle plain HTML/CSS/JavaScript
inside the existing Python package and serve it from FastAPI. This preserves the
single-environment setup, works offline, and adds no schema/dependency changes.
Assets use the already-reserved `/api/` namespace. Tradeoffs: no full-link listing,
no durable browser history, manual stats refresh, and browser-clock-based status
labels. Existing public-analytics and hosting limitations still apply.
