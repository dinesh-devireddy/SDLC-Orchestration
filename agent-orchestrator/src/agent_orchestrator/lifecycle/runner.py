"""Run lifecycle, checkpoints, serialized commands, and portable review artifacts."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from dotenv import load_dotenv

from ..llm import llm_from_environment
from .agents import DemoAgents, ReasoningAgents
from .audit import Journal
from .graph import build_lifecycle
from .models import HumanDecision
from .tools import digest, read_snapshot, restore_workspace

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / ".runs"


class RunManager:
    def __init__(self, root: Path = DEFAULT_ROOT, agents=None):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.agents = agents  # Dependency injection for offline integration tests.

    def directory(self, run_id):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid run ID")
        path = self.root / run_id
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Run not found")
        return path

    @contextmanager
    def _locked(self, directory):
        path = directory / "RUNNING"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("This run is already executing; do not submit a second command") from None
        os.close(descriptor)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    @contextmanager
    def _graph(self, directory):
        meta = json.loads((directory / "metadata.json").read_text())
        if meta["mode"] == "live" and self.agents is None:
            load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
        agents = self.agents or (DemoAgents(meta["scenario"]) if meta["mode"] == "demo"
                                else ReasoningAgents(llm_from_environment()))
        with SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver:
            yield build_lifecycle(agents, directory, Journal(directory / "audit.sqlite"), saver)

    @staticmethod
    def config(run_id):
        return {"configurable": {"thread_id": run_id}, "recursion_limit": 100,
                "max_concurrency": 3}

    def start(self, requirement: str, *, mode="demo", scenario="greenfield", source: Path | None = None,
              test_python: Path | None = None):
        if not requirement.strip() or len(requirement) > 10_000:
            raise ValueError("Requirement must contain 1–10,000 characters")
        if mode not in {"demo", "live"}:
            raise ValueError("Mode must be demo or live")
        interpreter = str(test_python.absolute()) if test_python else sys.executable
        if not Path(interpreter).is_file():
            raise ValueError("Test interpreter does not exist")
        if mode == "demo":
            DemoAgents(scenario)  # Validate scenario before creating files.
            if source is not None:
                raise ValueError("Demo scenarios use only their built-in fixtures; omit source")
            snapshot = {"src/demo_destination.py": "def valid_destination(value):\n    return True\n"} if scenario == "brownfield" else {}
        else:
            if source is None:
                raise ValueError("Live mode requires an explicit source directory")
            snapshot = read_snapshot(source)
        run_id = uuid.uuid4().hex
        directory = self.root / run_id
        directory.mkdir(mode=0o700)
        meta = {"run_id": run_id, "mode": mode, "scenario": scenario,
                "source": str(source.resolve()) if source else "built-in demo fixture"}
        (directory / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        restore_workspace(directory / "workspace", snapshot)
        initial = {"run_id": run_id, "requirement": requirement.strip(), "revision": 1,
                   "mode": mode, "status": "running", "snapshot": snapshot,
                   "snapshot_hash": digest(snapshot), "repair_count": 0,
                   "test_python": interpreter,
                   "execute_tests": False, "feedback": [], "failure": None}
        Journal(directory / "audit.sqlite").add("run_started", 1, requirement_hash=digest(requirement),
                                                snapshot_hash=initial["snapshot_hash"], mode=mode)
        with self._locked(directory), self._graph(directory) as graph:
            graph.invoke(initial, self.config(run_id))
        return self.view(run_id)

    def view(self, run_id):
        directory = self.directory(run_id)
        # Building a graph with inert demo agents is enough to inspect interrupts.
        with SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver:
            graph = build_lifecycle(DemoAgents(), directory, Journal(directory / "audit.sqlite"), saver)
            snapshot = graph.get_state(self.config(run_id))
            pending = [i.value for task in snapshot.tasks for i in task.interrupts]
        state = dict(snapshot.values)
        journal = Journal(directory / "audit.sqlite")
        return {"run_id": run_id, "state": state, "pending": pending,
                "status": "awaiting_" + pending[0]["gate"] if pending else state.get("status", "not_started"),
                "metrics": journal.metrics(), "artifacts": str(directory)}

    def resume(self, run_id, decision: dict):
        parsed = HumanDecision.model_validate(decision)
        directory = self.directory(run_id)
        with self._locked(directory):
            current = self.view(run_id)
            if not current["pending"]:
                raise ValueError("This run is not waiting for a human decision")
            # Reject stale approvals before consuming the interrupt, so a mistaken
            # click cannot invalidate an otherwise reviewable run.
            if parsed.action == "approve" and parsed.expected_digest != current["pending"][0]["digest"]:
                raise ValueError("Stale approval digest; reload and review the current artifact")
            with self._graph(directory) as graph:
                graph.invoke(Command(resume=parsed.model_dump()), self.config(run_id))
        return self.view(run_id)

    def stop(self, run_id, actor="local-user"):
        directory = self.directory(run_id)
        current = self.view(run_id)
        if current["status"] in {"completed", "stopped", "rejected", "review_needed"}:
            return current
        (directory / "STOP").touch()
        Journal(directory / "audit.sqlite").add("stop_requested", current["state"].get("revision", 1), actor=actor)
        if not (directory / "RUNNING").exists() and current["pending"]:
            # The gate observes STOP before doing anything with the resume value.
            return self.resume(run_id, {"action": "stop", "actor": actor, "note": "Operator requested safe stop"})
        return {**current, "stop_requested": True}

    def list_runs(self):
        return [self.view(path.name) for path in sorted(self.root.iterdir())
                if path.is_dir() and re.fullmatch(r"[0-9a-f]{32}", path.name)]

    def metrics(self):
        runs = self.list_runs()
        terminal = [run for run in runs if run["status"] in {"completed", "stopped", "rejected", "review_needed"}]
        successful = sum(run["status"] == "completed" for run in terminal)
        return {"runs": len(runs), "terminal_runs": len(terminal), "successful_runs": successful,
                "success_rate": successful / len(terminal) if terminal else None,
                "retries": sum(run["metrics"]["retry"] for run in runs),
                "rollbacks": sum(run["metrics"]["rollback"] for run in runs)}
