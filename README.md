# Agentic URL Shortener

A local **Python/FastAPI/SQLite URL shortener** and a **LangGraph SDLC orchestrator**
that turns requirements into reviewable patches, validation evidence, and human decisions.
No Docker, Node.js, or database server required.

## Setup and run

Install **Python 3.11+** (with SQLite 3.35+). Download/clone this repository.
Use two terminals, each starting in the repository root. Internet is required to
install dependencies; only orchestrator **Live** mode requires an LLM API key.

### Terminal 1 — URL shortener

```sh
cd url-shortener
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m shortener init-db
python -m shortener serve
```

Open [URL shortener](http://127.0.0.1:8000/).
SQLite is created automatically by `init-db` at `url-shortener/data/shortener.db`;
keep this file to preserve links. Repeating `init-db` is safe.

### Terminal 2 — Agent orchestrator

```sh
cd agent-orchestrator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ui]"
python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open [Agent orchestrator](http://127.0.0.1:8501/). **Demo** works without credentials.
The two projects need separate virtual environments because their dependencies differ.

**Windows PowerShell:** in each block replace `python3 -m venv .venv` with
`py -3 -m venv .venv`, and activation with `.\.venv\Scripts\Activate.ps1`.
If activation is blocked, use `.\.venv\Scripts\python.exe` instead of `python`
for all subsequent commands; no execution-policy change is required.

### Enable Live mode (optional; API charges apply)

Stop the orchestrator with Ctrl+C. Copy `agent-orchestrator/.env.example` to
`agent-orchestrator/.env` and edit it privately:

```dotenv
LLM_API_KEY=your-api-key
LLM_MODEL=your-accessible-model-id
LLM_BASE_URL=https://api.openai.com/v1
LLM_STRUCTURED_OUTPUT_METHOD=json_schema
LLM_TIMEOUT_SECONDS=60
```

Use an accessible model supporting structured outputs. Restart the orchestrator
with the same Streamlit command. Never commit or show `.env` in your recording.
In the UI select **Live**, enter a requirement and use:

- **Source directory:** absolute path to this repository's `url-shortener` folder.
- **Trusted test Python executable:** absolute path to `url-shortener/.venv/bin/python`
  (Windows: `url-shortener\.venv\Scripts\python.exe`). To print it, run
  `python -c "import sys; print(sys.executable)"` in the activated service terminal
  before starting its server, or in another terminal with that environment activated.
- Check provider consent, then click **Analyze requirement**.

Inspect the revision's patch before choosing **Approve — looks correct**.
Enter a review note and explicitly authorize tests. Review validation results and
approve again at final review. Changes stay in an isolated workspace: **nothing
is automatically merged, deployed, or applied to the running service**.
Approved tests execute local Python; the workspace is not an OS security sandbox.

## Restart, test, and troubleshoot

Stop servers with Ctrl+C. Later, activate each existing environment and run its
server command again; no reinstall is needed. From either project directory with
its environment active, run `python -m pytest -q` to test without LLM charges.

- Live provider error: check key, model access, endpoint, and provider quota/billing.
  Avoid repeatedly submitting a failed run; use Demo while resolving configuration.
- Failed service tests in Live: verify the trusted interpreter is the service's
  environment and its test dependencies are installed.
- Port busy: stop the existing server before starting another.
- Keep `.env`, `.runs/`, virtual environments, and populated databases out of the
  shared submission. Saved orchestrator runs contain source and review notes.

## Guides

- [Short recording script, test data, and Live prompt](demo/video-walkthrough.md)
- [Detailed service setup and API behavior](url-shortener/README.md)
- [Workflow, assignment coverage, guardrails, and limitations](docs/agentic-lifecycle.md)
- [Original two-node learning walkthrough](docs/milestone-1.md)

This is a local interview prototype. Demo mode uses scripted reasoning; Live
uses the configured model. Neither mode claims production security or compliance.
