import sqlite3
from pathlib import Path

from agent_orchestrator.lifecycle.agents import DemoAgents
from agent_orchestrator.lifecycle.audit import Journal
from agent_orchestrator.lifecycle.runner import RunManager
from test_lifecycle import approve


def test_live_source_is_read_only_with_injected_offline_reasoning(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    original = "def existing():\n    return 42\n"
    (source / "existing.py").write_text(original)
    manager = RunManager(tmp_path / "runs", agents=DemoAgents())
    view = manager.start("Add validation", mode="live", source=source)
    view = approve(manager, view)
    view = approve(manager, view)
    assert view["status"] == "completed"
    assert (source / "existing.py").read_text() == original
    assert len(list(source.iterdir())) == 1


def test_provider_failure_exhausts_two_attempts_and_stops(tmp_path):
    class Unavailable(DemoAgents):
        count = 0

        def run(self, role, state):
            self.count += 1
            raise TimeoutError("private response")

    agents = Unavailable()
    manager = RunManager(tmp_path, agents=agents)
    view = manager.start("Validate URLs")
    assert agents.count == 2
    assert view["status"] == "review_needed"
    assert view["metrics"]["retry"] == 1
    assert "private" not in view["state"]["failure"]


def test_rejection_restores_baseline(tmp_path):
    manager = RunManager(tmp_path)
    view = approve(manager, manager.start("Validate URLs"))
    view = manager.resume(view["run_id"], {"action": "reject", "actor": "reviewer", "note": "Needs a different design"})
    assert view["status"] == "rejected"
    assert not list((Path(view["artifacts"]) / "workspace").rglob("*.py"))


def test_workspace_tampering_invalidates_release(tmp_path):
    manager = RunManager(tmp_path)
    view = approve(manager, manager.start("Validate URLs"))
    (Path(view["artifacts"]) / "workspace/src/demo_destination.py").write_text("# changed since validation\n")
    view = approve(manager, view)
    assert view["status"] == "review_needed"
    assert view["state"]["failure"] == "Workspace changed after validation"


def test_revision_budget_is_bounded(tmp_path):
    manager = RunManager(tmp_path)
    view = manager.start("Validate URLs")
    for i in range(3):
        view = manager.resume(view["run_id"], {"action": "revise", "actor": "reviewer",
            "note": "Change request", "requirement": f"Updated requirement {i}"})
    assert view["status"] == "review_needed"
    assert view["state"]["revision"] == 3


def test_audit_detects_modified_event(tmp_path):
    journal = Journal(tmp_path / "audit.sqlite")
    journal.add("start", 1)
    with sqlite3.connect(journal.path) as db:
        db.execute("UPDATE events SET payload = ? WHERE seq=1", ('{"event":"tampered"}',))
    # A malformed or changed payload is not a valid chain.
    assert not journal.verify()
