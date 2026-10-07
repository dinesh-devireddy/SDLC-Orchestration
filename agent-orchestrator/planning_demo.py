"""Local review UI. Run from this directory: streamlit run app.py.

Streamlit reruns this script on interaction. Only a form submission invokes the
graph; session_state retains the latest result during other UI interactions.
"""

from pathlib import Path
from time import perf_counter

import streamlit as st
from dotenv import load_dotenv

from agent_orchestrator.errors import describe_error
from agent_orchestrator.llm import llm_from_environment
from agent_orchestrator.models import EngineeringState
from agent_orchestrator.workflow import build_workflow

st.set_page_config(page_title="Engineering Flow", page_icon="◎", layout="wide")
st.caption("AGENTIC SDLC · LOCAL WORKSPACE")
st.title("From requirement to reviewable plan")
st.write("Describe a change. Review what it means, what is unclear, and the work it needs.")

with st.sidebar:
    st.subheader("Workflow scope")
    st.write("Two agents · One shared state")
    st.caption("Plans are drafts for human review. This workflow does not implement tasks.")
    st.divider()
    st.write("Connection")
    st.caption("Configure LLM_API_KEY and LLM_MODEL in agent-orchestrator/.env.")
    st.caption("Submitting sends your requirement to the configured LLM provider.")
    st.caption("Results stay in this browser session; download JSON to keep a copy.")

with st.form("requirement_form"):
    requirement = st.text_area(
        "Software requirement",
        value="Add expiration support to shortened URLs.",
        height=120,
        help="Describe the requested behavior and any constraints you already know.",
    )
    submitted = st.form_submit_button("Generate draft plan", type="primary")

progress = st.empty()


def show_progress(completed: list[str], active: str | None = None, failed: bool = False):
    with progress.container():
        for column, node, label in zip(
            st.columns(2),
            ("requirement_agent", "planning_agent"),
            ("01 · Requirement Agent", "02 · Planning Agent"),
        ):
            with column:
                st.markdown(f"**{label}**")
                status = "Complete" if node in completed else "Waiting"
                if node == active:
                    status = "Stopped" if failed else "Running…"
                st.caption(status)


if submitted:
    # Clear earlier results before a new run, including when the new input fails.
    st.session_state.pop("result", None)
    st.session_state.pop("error", None)
    st.session_state.pop("elapsed", None)
    st.session_state.completed = []
    st.session_state.active = None
    if not requirement.strip():
        st.session_state.error = "Enter a requirement before generating a plan."
    else:
        started = perf_counter()
        state = EngineeringState(requirement=requirement)
        try:
            # Resolve .env relative to this file, not the shell's working directory.
            load_dotenv(Path(__file__).parent / ".env", override=False)
            llm = llm_from_environment()
            st.session_state.active = "requirement_agent"
            show_progress([], active=st.session_state.active)
            with st.spinner("Running the workflow…"):
                # Stream completed-node updates from the SAME graph used by the CLI.
                # The UI observes progress; graph edges still own execution order.
                for update in build_workflow(llm).stream(
                    state.model_dump(), stream_mode="updates"
                ):
                    for node, patch in update.items():
                        state = EngineeringState.model_validate({**state.model_dump(), **patch})
                        st.session_state.result = state.model_dump()
                        st.session_state.completed.append(node)
                        st.session_state.active = (
                            "planning_agent" if node == "requirement_agent" else None
                        )
                        show_progress(st.session_state.completed, st.session_state.active)
        except Exception as error:
            # Raw provider errors may contain request data or secrets.
            st.session_state.error = (
                describe_error(error) + " "
                "The run was not retried. Any completed analysis is shown below."
            )
        st.session_state.elapsed = perf_counter() - started

show_progress(
    st.session_state.get("completed", []),
    st.session_state.get("active"),
    failed=bool(st.session_state.get("error")),
)
if st.session_state.get("error"):
    st.error(st.session_state.error)
if "elapsed" in st.session_state:
    st.caption(f"Last run elapsed: {st.session_state.elapsed:.1f} seconds")

if "result" in st.session_state:
    result = EngineeringState.model_validate(st.session_state.result)
    st.divider()
    st.subheader("Review the outcome")
    st.caption(f"Requirement for this result: {result.requirement}")
    analysis_tab, plan_tab, state_tab = st.tabs(["Requirement analysis", "Engineering plan", "Shared state"])
    with analysis_tab:
        if result.analysis:
            st.write(result.analysis.normalized_requirement)
            for label, items in (
                ("Ambiguities", result.analysis.ambiguities),
                ("Tentative assumptions", result.analysis.assumptions),
                ("Acceptance criteria", result.analysis.acceptance_criteria),
            ):
                st.markdown(f"**{label}**")
                if not items:
                    st.caption("None reported by the agent.")
                for index, item in enumerate(items, start=1):
                    st.write(f"{index}. {item}")
    with plan_tab:
        if result.plan:
            st.caption("Proposed order; these tasks have not been executed.")
            tasks = {task.id: task for task in result.plan.tasks}
            for index, task_id in enumerate(result.plan.execution_order, start=1):
                task = tasks[task_id]
                with st.container(border=True):
                    st.write(f"{index}. {task.id} — {task.description}")
                    st.caption("Depends on: " + (", ".join(task.depends_on) or "No dependencies"))
            st.markdown("**Risks**")
            for risk in result.plan.risks:
                st.write(risk)
            if not result.plan.risks:
                st.caption("None reported by the agent.")
        else:
            st.info("No plan was completed for this run.")
    with state_tab:
        st.json(result.model_dump())
    st.download_button(
        "Download state as JSON",
        result.model_dump_json(indent=2),
        file_name="engineering-state.json",
        mime="application/json",
        on_click="ignore",
    )
else:
    st.info("Your analysis and plan will appear here after a run.")
