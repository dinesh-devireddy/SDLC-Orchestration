"""Control room for durable runs; no provider call occurs on page load."""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from agent_orchestrator.lifecycle.audit import Journal
from agent_orchestrator.lifecycle.runner import RunManager

st.set_page_config(page_title="SDLC Lifecycle", page_icon="◎", layout="wide")
st.caption("AGENTIC SDLC · GOVERNED WORKFLOW")
st.title("Engineering lifecycle")
st.write("Review proposals, approve isolated changes, and inspect validation and recovery evidence.")
with st.expander("How the workflow works"):
    st.code("Requirement → clarification? → Plan → Impact → Proposal → Policy → Human approval\n"
        "  → Apply in workspace → [Tests ‖ Security ‖ Documentation] → Join\n"
        "  → Final human review → Complete\n"
        "Validation failure → Rollback → bounded repair → new approval\n"
        "Changed requirement → Rollback → invalidate outputs → Replan")

manager = RunManager()
with st.expander("Start a run", expanded=True):
    # Routing selectors are outside forms so changes rerender immediately.
    mode = st.selectbox("Reasoning mode", ["demo", "live"], key="mode",
                        format_func=lambda value: {"demo": "Demo — no API costs", "live": "Live — use my codebase"}[value])
    scenario, source, test_python, consent = "greenfield", "", "", False
    if mode == "demo":
        st.info("Scripted reasoning with real workflow controls and tests. No API key needed. Custom requirements are supported in Live mode.")
        scenario = st.selectbox("Offline scenario", ["greenfield", "brownfield", "ambiguous", "repair", "failure", "retry"], key="scenario")
        descriptions = {
            "greenfield": "Create a URL validation helper from an empty fixture.",
            "brownfield": "Fix an existing URL validation helper.",
            "ambiguous": "Pause for clarification before planning URL validation.",
            "repair": "Fail validation once, roll back, then propose a repair.",
            "failure": "Exhaust the repair budget and hand off for human review.",
            "retry": "Recover from a temporary planning failure with a bounded retry.",
        }
        requirement = descriptions[scenario]
        st.caption(requirement)
    else:
        st.info("Agents analyze a snapshot of your selected codebase. API charges apply; changes require approval.")
    with st.form("start_lifecycle_" + mode):
        if mode == "live":
            requirement = st.text_area("Requirement", placeholder="Describe the change, expected behavior, and constraints.")
            source = st.text_input("Source directory", str(Path(__file__).resolve().parent.parent / "url-shortener"))
            test_python = st.text_input("Trusted test Python executable (optional)", help="Use the service virtual environment Python after installing its test dependencies. Empty uses the orchestrator environment.")
            consent = st.checkbox("Send the source snapshot to my configured LLM provider (API charges may apply).")
        start = st.form_submit_button("Start demo" if mode == "demo" else "Analyze requirement", type="primary")
    if start:
        if mode == "live" and not consent:
            st.error("Enable live-mode consent or select demo.")
        else:
            try:
                if mode == "live":
                    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
                with st.spinner("Running to the next human checkpoint…"):
                    view = manager.start(requirement, mode=mode, scenario=scenario,
                                         source=Path(source) if mode == "live" else None,
                                         test_python=Path(test_python) if test_python.strip() else None)
                st.session_state.lifecycle_run = view["run_id"]
            except Exception as error:
                st.error(f"Could not start ({type(error).__name__}). Check configuration, source size, and file permissions.")

runs = manager.list_runs()
if not runs:
    st.caption("No lifecycle runs yet.")
    st.stop()
ids = [run["run_id"] for run in runs]
selected = st.session_state.get("lifecycle_run", ids[-1])
run_id = st.selectbox("Saved run", ids, index=ids.index(selected) if selected in ids else len(ids) - 1)
st.session_state.lifecycle_run = run_id
if st.button("Refresh run"):
    st.rerun()
view = manager.view(run_id)
st.subheader(view["status"].replace("_", " ").title())
state = view["state"]
st.caption(f"Mode: {state.get('mode')} · Revision: {state.get('revision')} · Run: {run_id}")
columns = st.columns(4)
for column, label, key in zip(columns, ["Retries", "Rollbacks", "Replans", "Elapsed (s)"],
                             ["retry", "rollback", "replan", "elapsed_seconds"]):
    column.metric(label, view["metrics"][key])

review, evidence, shared = st.tabs(["Review artifacts", "Audit and metrics", "Shared state"])
with review:
    for label, key in [("Requirement analysis", "analysis"), ("Plan and dependencies", "plan"),
                       ("Architecture / impact", "impact"), ("Policy checks", "policy"),
                       ("Tests", "test_result"), ("Security", "security_result"), ("Documentation", "documentation")]:
        if state.get(key):
            with st.expander(label):
                st.json(state[key])
    patch = Path(view["artifacts"]) / "proposal.diff"
    if patch.exists() and state.get("proposal"):
        revision = st.selectbox("View proposed changes for revision", [state["revision"]], index=None,
            placeholder="Select the current revision to inspect its patch",
            format_func=lambda value: f"Revision {value} — current proposal",
            key=f"patch_{run_id}_{state['revision']}_{view['pending'][0]['digest'] if view['pending'] else view['status']}")
    else:
        revision = None
    if revision is not None:
        st.markdown(f"**Proposed changes · Revision {revision}**")
        content = patch.read_text(encoding="utf-8")
        st.code(content, language="diff")
        st.download_button("Download patch", content, file_name=f"{run_id}.diff", on_click="ignore")
    if state.get("failure"):
        st.error(state["failure"])
with evidence:
    st.json(view["metrics"])
    st.caption("Local hash-chained journal; useful for review, not externally anchored or audit-certified.")
    st.json(Journal(Path(view["artifacts"]) / "audit.sqlite").events())
    st.write("All-run metrics")
    st.json(manager.metrics())
with shared:
    st.json(state)

if view["pending"]:
    gate = view["pending"][0]
    st.subheader("Human decision")
    st.write(f"Checkpoint: {gate['gate']} · revision {gate['revision']}")
    st.caption(f"Artifact digest: {gate['digest']}")
    if gate["gate"] == "clarification":
        st.write(gate["ambiguities"])
    if gate["gate"] == "patch":
        st.warning(gate["test_execution_notice"])
        st.caption("Test interpreter: " + gate["test_python"])
    actions = ["clarify", "revise", "reject", "stop"] if gate["gate"] == "clarification" else ["approve", "revise", "reject", "stop"]
    labels = {"approve": "Approve — looks correct", "revise": "Revise — change the requirement",
              "clarify": "Clarify — answer the questions", "reject": "Reject — discard this outcome",
              "stop": "Stop — end this run"}
    action = st.selectbox("Decision", actions, format_func=labels.get, key=f"decision_{run_id}_{gate['digest']}")
    if action == "approve":
        st.info("Approve applies the reviewed patch to an isolated workspace. Authorize tests below to validate it." if gate["gate"] == "patch"
                else "Approve completes this reviewed outcome. It does not merge or deploy the changes.")
    elif action == "revise":
        st.info("A new requirement triggers replanning and invalidates earlier outputs and approvals.")
    elif action in {"reject", "stop"}:
        st.warning("This ends the run and restores its isolated workspace to the original snapshot.")
    with st.form(f"human_decision_{run_id}_{gate['digest']}_{action}"):
        actor = st.text_input("Reviewer name", "local-user")
        note = st.text_area("Clarification answer" if action == "clarify" else "Review note (required)")
        revised = st.text_area("New requirement", placeholder="Enter the complete updated requirement.") if action == "revise" else ""
        execute = st.checkbox("I reviewed the patch and authorize running its Python tests locally.") if gate["gate"] == "patch" and action == "approve" else False
        if gate["gate"] == "patch" and action == "approve":
            st.caption("Without test authorization, the run ends in manual review rather than reporting success.")
        submit = st.form_submit_button({"approve": "Approve and continue", "revise": "Replan with new requirement",
            "clarify": "Submit clarification", "reject": "Reject outcome", "stop": "Stop run"}[action], type="primary")
    if submit:
        if not actor.strip() or not note.strip() or (action == "revise" and not revised.strip()):
            st.error("Enter a reviewer name, a note, and a new requirement when revising.")
        else:
            try:
                with st.spinner("Resuming workflow…"):
                    manager.resume(run_id, {"action": action, "actor": actor, "note": note,
                        "requirement": revised, "expected_digest": gate["digest"], "execute_tests": execute})
                st.rerun()
            except Exception as error:
                st.error(f"Decision not applied ({type(error).__name__}). Fill required fields and refresh if the artifact changed.")
if view["status"] not in {"completed", "stopped", "rejected", "review_needed"}:
    if st.button("Request safe stop"):
        manager.stop(run_id)
        st.rerun()
st.caption("Source code is never overwritten or deployed. Run artifacts are saved in " + view["artifacts"])
