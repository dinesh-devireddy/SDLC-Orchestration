"""Explicit SDLC control flow. Reasoning, governance, and action tools stay separate."""

from pathlib import Path
import time

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import ValidationError

from ..errors import describe_error
from .agents import SCHEMAS
from .models import HumanDecision, LifecycleState
from .tools import apply_proposal, digest, patch_text, policy_check, restore_workspace, run_tests, static_scan, workspace_matches

MAX_ATTEMPTS = 2
MAX_REPAIRS = 1
MAX_REVISIONS = 3


def transient(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return error.code in {"rate_limit_exceeded", "slow_down"}
    return isinstance(error, (TimeoutError, APIConnectionError, APITimeoutError, InternalServerError, ValidationError))


def approval_digest(state: dict) -> str:
    return digest({key: state.get(key) for key in (
        "requirement", "revision", "snapshot_hash", "plan", "impact", "proposal", "policy", "test_python",
    )})


def release_digest(state: dict) -> str:
    return digest({"patch": approval_digest(state), "test": state.get("test_result"),
                   "security": state.get("security_result"), "docs": state.get("documentation")})


def build_lifecycle(agents, run_dir: Path, journal, checkpointer):
    workspace, stop_file = run_dir / "workspace", run_dir / "STOP"

    def log(state, event, **details):
        journal.add(event, state["revision"], **details)

    def reason(role, state):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if stop_file.exists():
                raise RuntimeError("Stop requested")
            started = time.monotonic()
            log(state, "stage_started", stage=role, attempt=attempt)
            try:
                output = SCHEMAS[role].model_validate(agents.run(role, state)).model_dump()
                log(state, "stage_finished", stage=role, attempt=attempt,
                    duration=round(time.monotonic() - started, 3), output_hash=digest(output))
                return output
            except Exception as error:
                log(state, "stage_error", stage=role, attempt=attempt, error_type=type(error).__name__,
                    duration=round(time.monotonic() - started, 3))
                if not transient(error) or attempt == MAX_ATTEMPTS:
                    log(state, "failure", stage=role, error_type=type(error).__name__)
                    raise
                log(state, "retry", stage=role, attempt=attempt)
                # A bounded delay; no hidden SDK retries or endless graph loops.
                time.sleep(0.1 * attempt)

    def reasoning_node(role, field):
        def node(state):
            if stop_file.exists():
                return {"route": "stop"}
            try:
                value = reason(role, state)
                return {field: value, "route": "next", "failure": None, "status": "running"}
            except Exception as error:
                return {"failure": describe_error(error), "route": "stop" if stop_file.exists() else "fallback"}
        return node

    def requirement_route(state):
        if state["route"] != "next":
            return state["route"]
        return "clarification" if state["analysis"]["ambiguities"] else "planning"

    def gate(kind):
        def node(state):
            if stop_file.exists():
                return {"route": "stop"}
            if kind == "release" and not workspace_matches(workspace, state["snapshot"], state["proposal"]):
                return {"failure": "Workspace changed after validation", "route": "fallback"}
            token = release_digest(state) if kind == "release" else approval_digest(state)
            payload = {"gate": kind, "revision": state["revision"], "digest": token,
                       "ambiguities": (state.get("analysis") or {}).get("ambiguities", []),
                       "policy": state.get("policy"),
                       "patch_file": str(run_dir / "proposal.diff"),
                       "test_python": state["test_python"],
                       "test_execution_notice": "Tests execute repository Python on this machine. The workspace is not an OS security sandbox. Approve only code you trust."}
            # interrupt persists state and returns control to the human. On resume
            # this node restarts; keep side effects AFTER interrupt, not before it.
            raw = interrupt(payload)
            try:
                decision = HumanDecision.model_validate(raw)
                if decision.action == "approve" and decision.expected_digest != token:
                    raise ValueError("Approval is stale or not bound to the current artifact")
                if kind == "clarification" and decision.action == "approve":
                    raise ValueError("Clarification requires a human answer, not blanket approval")
                if decision.action in {"clarify", "revise"} and state["revision"] >= MAX_REVISIONS:
                    raise ValueError("Requirement revision budget exhausted")
                if decision.action == "revise" and not decision.requirement.strip():
                    raise ValueError("A revised requirement is required")
            except (ValueError, ValidationError):
                return {"failure": "Invalid/stale decision or revision budget exhausted", "route": "fallback"}
            log(state, "human_decision", gate=kind, decision=decision.model_dump(), artifact_hash=token)
            if decision.action in {"clarify", "revise"}:
                requirement = decision.requirement.strip() if decision.action == "revise" else (
                    state["requirement"] + "\nHuman clarification: " + decision.note)
                return {"decision": decision.model_dump(), "requirement": requirement,
                        "revision": state["revision"] + 1, "route": "replan"}
            if decision.action in {"stop", "reject"}:
                return {"decision": decision.model_dump(), "route": decision.action}
            return {"decision": decision.model_dump(), "route": "next",
                    "approved_digest": approval_digest(state),
                    "execute_tests": decision.execute_tests if kind == "patch" else state.get("execute_tests", False)}
        return node

    def policy(state):
        try:
            result = policy_check(state["proposal"], state["snapshot"], {t["id"] for t in state["plan"]["tasks"]})
            patch = patch_text(state["snapshot"], state["proposal"])
            (run_dir / "proposal.diff").write_text(patch, encoding="utf-8")
            history = run_dir / "proposals"
            history.mkdir(exist_ok=True)
            (history / (digest(state["proposal"]) + ".diff")).write_text(patch, encoding="utf-8")
            log(state, "policy_checked", result=result, proposal_hash=digest(state["proposal"]))
            return {"policy": result, "route": "next" if result["passed"] else "fallback",
                    "failure": None if result["passed"] else "Proposal blocked by deterministic write policy"}
        except Exception:
            return {"failure": "Proposal could not be validated", "route": "fallback"}

    def apply(state):
        if stop_file.exists():
            return {"route": "stop"}
        if state.get("approved_digest") != approval_digest(state):
            return {"failure": "Artifact changed after approval", "route": "fallback"}
        try:
            if not policy_check(state["proposal"], state["snapshot"], {t["id"] for t in state["plan"]["tasks"]})["passed"]:
                raise ValueError("Policy changed")
            apply_proposal(workspace, state["snapshot"], state["proposal"])
            log(state, "patch_applied", artifact_hash=approval_digest(state))
            return {"route": "next"}
        except Exception:
            return {"failure": "Patch application failed", "route": "fallback"}

    def tests(state):
        try:
            review = reason("test", state)
            result = run_tests(workspace, stop_file, python=state["test_python"]) if state.get("execute_tests") and not stop_file.exists() else {
                "passed": False, "skipped": True, "reason": "Execution not approved or stop requested"}
            result["review"] = review
            result["passed"] = result["passed"] and not review["missing_cases"]
            log(state, "test_result", result=result, duration=result.get("elapsed_seconds", 0))
        except Exception as error:
            result = {"passed": False, "error": describe_error(error), "unavailable": True}
        return {"test_result": result}

    def security(state):
        try:
            review = reason("security", state)
            scan = static_scan(workspace)
            result = {"passed": scan["passed"] and not review["blocking_findings"], "review": review, "scan": scan}
            log(state, "security_result", result=result)
        except Exception as error:
            result = {"passed": False, "error": describe_error(error), "unavailable": True}
        return {"security_result": result}

    def documentation(state):
        try:
            return {"documentation": reason("documentation", state)}
        except Exception as error:
            return {"documentation": {"error": describe_error(error)}}

    def synchronize(state):
        # This node runs only after ALL three branches finish. Each branch writes
        # its own field, avoiding conflicting concurrent writes to shared state.
        if stop_file.exists():
            return {"route": "stop"}
        if not workspace_matches(workspace, state["snapshot"], state["proposal"]):
            return {"failure": "Tests modified the approved source snapshot", "route": "fallback"}
        results = [state.get("test_result") or {}, state.get("security_result") or {}]
        if "error" in (state.get("documentation") or {}) or any(r.get("skipped") or r.get("unavailable") for r in results):
            return {"failure": "Validation unavailable or execution not approved; human review required", "route": "fallback"}
        if all(r.get("passed") for r in results):
            log(state, "validation_join", passed=True)
            return {"route": "next"}
        log(state, "failure", reason="Validation failed")
        feedback = ["Previous validation failed. Fix the implementation against acceptance criteria.",
                    str(state.get("test_result")), str(state.get("security_result"))]
        return {"feedback": feedback, "failure": "Validation failed",
                "route": "repair" if state["repair_count"] < MAX_REPAIRS else "fallback"}

    def rollback(state, reason):
        restore_workspace(workspace, state["snapshot"])
        log(state, "rollback", reason=reason)

    def repair(state):
        rollback(state, "repair")
        log(state, "retry", stage="implementation_repair", attempt=state["repair_count"] + 1)
        return {"repair_count": state["repair_count"] + 1, "proposal": None,
                "approved_digest": None, "test_result": None, "security_result": None,
                "documentation": None, "failure": None, "execute_tests": False}

    def replan(state):
        rollback(state, "requirement_revision")
        log(state, "replan", requirement_hash=digest(state["requirement"]))
        return {"analysis": None, "plan": None, "impact": None, "proposal": None,
                "policy": None, "approved_digest": None, "test_result": None,
                "security_result": None, "documentation": None, "repair_count": 0,
                "execute_tests": False, "failure": None, "feedback": []}

    def finish(status):
        def node(state):
            final_status = "stopped" if stop_file.exists() else status
            if final_status == "completed" and not workspace_matches(workspace, state["snapshot"], state["proposal"]):
                final_status = "review_needed"
            if final_status != "completed":
                rollback(state, final_status)
            log(state, final_status if final_status != "review_needed" else "fallback", reason=state.get("failure"))
            result = {**state, "status": final_status}
            (run_dir / "outcome.md").write_text(
                f"# Engineering outcome\n\nStatus: {final_status}\nMode: {state['mode']}\n"
                f"Revision: {state['revision']}\n\nRequirement: {state['requirement']}\n\n"
                f"{(state.get('documentation') or {}).get('summary', 'Manual review is required.')}\n\n"
                "See checkpoint state, proposal.diff, and audit events for validation evidence. "
                "No changes were merged, deployed, or applied to the source repository.\n",
                encoding="utf-8")
            return {"status": result["status"]}
        return node

    graph = StateGraph(LifecycleState)
    for role, field in [("requirement", "analysis"), ("planning", "plan"), ("impact", "impact"), ("implementation", "proposal")]:
        graph.add_node(role, reasoning_node(role, field))
    nodes = {"clarification": gate("clarification"), "policy": policy,
             "approval": gate("patch"), "apply": apply, "tests": tests, "security": security,
             "documentation": documentation, "synchronize": synchronize,
             "release_review": gate("release"), "repair": repair, "replan": replan,
             "fallback": finish("review_needed"), "stop": finish("stopped"),
             "reject": finish("rejected"), "complete": finish("completed")}
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.add_edge(START, "requirement")
    graph.add_conditional_edges("requirement", requirement_route,
                                {name: name for name in ("planning", "clarification", "fallback", "stop")})
    for source, target in [("planning", "impact"), ("impact", "implementation"),
                           ("implementation", "policy"), ("policy", "approval"),
                           ("approval", "apply"), ("release_review", "complete"),
                           ("clarification", "planning"), ("synchronize", "release_review")]:
        graph.add_conditional_edges(source, lambda state: state["route"],
                                    {"next": target, "fallback": "fallback", "stop": "stop",
                                     "reject": "reject", "replan": "replan", "repair": "repair"})
    graph.add_conditional_edges("apply", lambda state: ["tests", "security", "documentation"] if state["route"] == "next" else state["route"],
                                {name: name for name in ("tests", "security", "documentation", "stop", "fallback")})
    graph.add_edge(["tests", "security", "documentation"], "synchronize")
    graph.add_edge("repair", "implementation")
    graph.add_edge("replan", "requirement")
    for name in ("fallback", "stop", "reject", "complete"):
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)
