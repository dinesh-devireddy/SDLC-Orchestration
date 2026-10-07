"""Offline integration coverage of real graph, checkpoints, tools and controls."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

from agent_orchestrator.lifecycle.agents import DemoAgents
from agent_orchestrator.lifecycle.audit import Journal
from agent_orchestrator.lifecycle.runner import RunManager
from agent_orchestrator.lifecycle.tools import policy_check, read_snapshot


def approve(manager, view, execute=True):
    return manager.resume(view["run_id"], {"action": "approve", "actor": "test-reviewer",
        "note": "Reviewed the fixture patch and authorized its tests",
        "expected_digest": view["pending"][0]["digest"], "execute_tests": execute})


def test_full_flow_persists_pauses_and_uses_real_tests(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate destination URLs")
    assert view["status"] == "awaiting_patch"
    assert list((tmp_path / view["run_id"] / "workspace").rglob("*.py")) == []
    # Construct a fresh manager to prove restart/resume uses SQLite, not memory.
    manager = RunManager(tmp_path)
    view = approve(manager, manager.view(view["run_id"]))
    assert view["status"] == "awaiting_release"
    assert view["state"]["test_result"]["exit_code"] == 0
    assert view["state"]["security_result"]["passed"]
    view = approve(manager, view)
    assert view["status"] == "completed"
    assert view["metrics"]["journal_chain_valid"]
    assert manager.metrics()["success_rate"] == 1
    assert (Path(view["artifacts"]) / "outcome.md").exists()


def test_ambiguity_and_revision_invalidate_prior_outputs(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate URLs", scenario="ambiguous")
    assert view["status"] == "awaiting_clarification"
    view = manager.resume(view["run_id"], {"action": "clarify", "actor": "reviewer",
        "note": "Reject URLs without an explicit scheme"})
    assert view["status"] == "awaiting_patch"
    old_digest = view["pending"][0]["digest"]
    view = manager.resume(view["run_id"], {"action": "revise", "actor": "reviewer",
        "note": "Updated scope", "requirement": "Validate HTTP and HTTPS destinations"})
    assert view["state"]["revision"] == 3
    assert view["state"]["approved_digest"] is None
    assert view["pending"][0]["digest"] != old_digest
    assert view["metrics"]["replan"] == 2
    with pytest.raises(ValueError, match="Stale approval"):
        manager.resume(view["run_id"], {"action": "approve", "actor": "reviewer",
            "note": "Stale click", "expected_digest": old_digest})


def test_failed_validation_rolls_back_and_reapproves_repair(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate URLs", scenario="repair")
    view = approve(manager, view)
    assert view["status"] == "awaiting_patch"
    assert view["state"]["repair_count"] == 1
    assert view["state"]["approved_digest"] is None
    assert not list((Path(view["artifacts"]) / "workspace").rglob("*.py"))
    view = approve(manager, view)
    assert view["status"] == "awaiting_release"
    view = approve(manager, view)
    assert view["status"] == "completed"
    assert view["metrics"]["rollback"] == 1
    assert view["metrics"]["mttr_seconds"] is not None


def test_retry_exhaustion_falls_back_without_fake_success(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate URLs", scenario="failure")
    view = approve(manager, view)
    view = approve(manager, view)
    assert view["status"] == "review_needed"
    assert not view["pending"]
    assert view["metrics"]["rollback"] == 2
    assert not list((Path(view["artifacts"]) / "workspace").rglob("*.py"))


def test_transient_reasoning_retry_is_bounded_and_observable(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate URLs", scenario="retry")
    assert view["status"] == "awaiting_patch"
    assert view["metrics"]["retry"] == 1


def test_no_execution_approval_cannot_report_success(tmp_path):
    manager = RunManager(tmp_path)
    view = approve(manager, manager.start("Validate URLs"), execute=False)
    assert view["status"] == "review_needed"
    assert view["state"]["test_result"]["skipped"]


def test_stop_restores_brownfield_snapshot(tmp_path):
    manager = RunManager(tmp_path)
    view = approve(manager, manager.start("Fix URL validation", scenario="brownfield"))
    assert view["status"] == "awaiting_release"
    view = manager.stop(view["run_id"])
    assert view["status"] == "stopped"
    baseline = view["state"]["snapshot"]
    workspace = Path(view["artifacts"]) / "workspace"
    assert read_snapshot(workspace) == baseline


def test_parallel_branches_synchronize_before_release(tmp_path):
    barrier = threading.Barrier(3, timeout=10)

    class ParallelAgents(DemoAgents):
        def run(self, role, state):
            if role in {"test", "security", "documentation"}:
                barrier.wait()  # A sequential implementation cannot pass this.
            return super().run(role, state)

    manager = RunManager(tmp_path, agents=ParallelAgents())
    view = approve(manager, manager.start("Validate URLs"))
    assert view["status"] == "awaiting_release"
    assert all(view["state"].get(field) for field in ("test_result", "security_result", "documentation"))


@pytest.mark.parametrize("path", ["../escape.py", "/tmp/escape.py", "src/../../escape.py",
                                  ".env", "AGENTS.md", "tests/conftest.py", "src\\escape.py"])
def test_unsafe_paths_are_blocked(path):
    result = policy_check({"rationale": "test", "changes": [{"path": path, "content": ""}],
                           "addressed_tasks": ["T1"]}, {}, {"T1"})
    assert not result["passed"]


def test_snapshot_skips_secrets_and_symlinks(tmp_path):
    (tmp_path / ".env").write_text("DO_NOT_READ=secret")
    (tmp_path / "app.py").write_text("print('safe')\n")
    (tmp_path / "linked.py").symlink_to(tmp_path / ".env")
    assert read_snapshot(tmp_path) == {"app.py": "print('safe')\n"}


def test_parallel_journal_writers_have_valid_chain(tmp_path):
    journal = Journal(tmp_path / "audit.sqlite")
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda i: journal.add("test", 1, number=i), range(12)))
    assert len(journal.events()) == 12
    assert journal.verify()
