# Short demo video (about 4–5 minutes, excluding API waits)

## Before recording

Follow the root README and open the service on `http://127.0.0.1:8000/` and
orchestrator on `http://127.0.0.1:8501/` in separate tabs. Configure Live mode
privately. Confirm the service tests pass. Do one Live rehearsal if your API budget
allows; model output, clarification questions, latency, and success are not guaranteed.
This guide was prepared without making paid API calls.

Use fresh aliases for each rehearsal, such as `video-demo-02`; existing aliases
persist in SQLite. Do not delete the database to repeat a recording. Keep the API
key, terminal environment, and private source off-screen. Select only the service
folder as the source, not the entire monorepo.

## 1. Introduce the two components (15 seconds)

Say: “This project has a working URL shortener and an agentic engineering workflow.
The workflow analyzes a requirement, proposes a change, asks for approval, and
validates it in a separate workspace.”

## 2. Show the URL shortener (60 seconds)

Use this data in the service UI:

| Field | Value |
| --- | --- |
| Destination URL | `https://example.com/` |
| Custom alias | `video-demo-01` |
| Expires on | Leave blank |

1. Click **Create short link**.
2. Click **View this link’s statistics**: expect 0 clicks for this fresh alias.
3. Open the generated short link once; it opens example.com in another tab.
4. Return and look up `video-demo-01`: expect 1 click, provided there were no other visits.
5. Try creating the same alias again: expect a conflict message, not an overwrite.

Say: “Links are stored in local SQLite. Custom aliases and expiration are supported.
A successful redirect increments the click count. Duplicate aliases are rejected.”

Optional expiration demonstration: create `video-expiry-01` pointing to
`https://example.com/`, with expiration about two minutes in the future using your
local time. Open its short link after that time: expect an expired response (410).
Skip this step for a shorter recording. Statistics remain available after expiry.

## 3. Submit a real brownfield requirement (45 seconds)

Select **Live — use my codebase**. Set the service source directory and trusted
service Python interpreter as described in the README. Paste:

```text
Improve the existing FastAPI URL shortener so successful statistics responses
cannot be cached. Inspect the existing code and tests before proposing changes.

Acceptance criteria:
1. GET /api/urls/{code}/stats for an existing code returns HTTP 200 and the
   response header Cache-Control: no-store.
2. The JSON response fields and values remain unchanged. Reading statistics
   must not increment clicks.
3. Unknown codes keep the existing 404 status and error body. No new caching
   behavior is required for errors or other endpoints.
4. Add a regression test covering the header, unchanged click count across
   repeated statistics reads, and existing unknown-code behavior.
5. Add a short note about this behavior to the service README.

Keep the change small and follow existing conventions. Do not add dependencies,
change database schema or migrations, modify governance files or conftest.py,
or alter redirect and expiration behavior. Run the existing pytest suite using
the configured test interpreter after human approval.
```

Enable provider consent and click **Analyze requirement** once.

Say: “This is a small enhancement to an existing codebase. The model reasons about
the requirement and affected code. LangGraph controls the execution order, shared
state, and approval checkpoints.”

Pause the recording during API waits, or label any time cuts. This workflow makes
multiple model calls; it is not limited to the two calls of the original prototype.

If it asks for clarification, choose **Clarify**, answer the actual question, and
submit. For this scenario the intended scope is successful statistics responses
only, no schema changes, and no change to existing error behavior.

## 4. Review and approve (60 seconds)

Expand **Requirement analysis**, **Plan and dependencies**, **Architecture / impact**,
and **Policy checks**. Select the current revision to reveal **Proposed changes**.
Confirm the patch matches the requirement; do not approve merely to finish the video.

Say: “The plan records dependencies, and impact analysis identifies affected files.
The agent can propose changes, but execution waits for my approval.”

If acceptable, select **Approve — looks correct**, enter your name and this note:

```text
Reviewed the statistics header change and regression tests. The patch stays
within the requested scope and does not change the schema or dependencies.
```

Check **I reviewed the patch and authorize running its Python tests locally.**
Click **Approve and continue**. Cut or pause during execution.

## 5. Show the outcome (45 seconds)

Review **Tests**, **Security**, and **Documentation**, then **Audit and metrics**.
Check actual results rather than narrating success in advance.

Say: “Tests, security review, and documentation run in parallel. The workflow waits
for all three before final review. The audit records decisions and timings, and
metrics report retries and rollbacks when they occur.”

If validation passed and the final outcome is acceptable, approve with:

```text
Reviewed passing validation and documentation. Accept this as a reviewable
local change; deployment and source integration remain separate.
```

Show the completed status and download the patch.

Say: “The result is a reviewed patch with validation evidence. The original service
and its database were not modified. Applying or deploying this patch is a separate step.”

## If the live run does not succeed

- Provider/configuration error: show the stop honestly; fix it before another paid run.
- Clarification: answer the displayed question; this is expected workflow behavior.
- Failed validation: show rollback and the replacement proposal if offered. Review
  and approve again only if it is acceptable. Retries and repair are bounded.
- Manual review outcome: show the evidence and explain the handoff; do not call it success.
- If you need a reliable offline recovery segment, start **Demo → repair**. Explicitly
  say its reasoning is scripted; the workflow, rollback, and pytest execution are real.

Optional replanning segment (extra API calls): at a human checkpoint, choose **Revise**
and paste the complete original requirement with an added acceptance criterion:
“Also cover an expired link: statistics remain readable and use Cache-Control: no-store.”
Explain that the change invalidates earlier outputs and approvals. Expect a fresh
proposal requiring review. Do this only if time and API budget permit.
