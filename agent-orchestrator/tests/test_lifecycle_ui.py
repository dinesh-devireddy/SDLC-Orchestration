from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from agent_orchestrator.lifecycle.runner import RunManager


def test_control_room_demo_starts_without_provider_and_waits_for_review(tmp_path, monkeypatch):
    manager = RunManager(tmp_path)
    monkeypatch.setattr("agent_orchestrator.lifecycle.runner.RunManager", lambda: manager)

    def no_llm():
        raise AssertionError("Demo must not construct an LLM client")

    monkeypatch.setattr("agent_orchestrator.lifecycle.runner.llm_from_environment", no_llm)
    page = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(str(page), default_timeout=15).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert manager.list_runs()[0]["status"] == "awaiting_patch"
    assert any("authorize" in checkbox.label for checkbox in app.checkbox)
    app.run()
    assert len(manager.list_runs()) == 1
    assert manager.list_runs()[0]["status"] == "awaiting_patch"


def test_mode_changes_fields_without_starting_a_run(tmp_path, monkeypatch):
    manager = RunManager(tmp_path)
    monkeypatch.setattr("agent_orchestrator.lifecycle.runner.RunManager", lambda: manager)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=15).run()
    assert any(s.label == "Offline scenario" for s in app.selectbox)
    assert not app.text_area
    assert not app.text_input
    app.selectbox(key="mode").set_value("live").run()
    assert not app.exception
    assert not any(s.label == "Offline scenario" for s in app.selectbox)
    assert any(t.label == "Requirement" for t in app.text_area)
    assert any(t.label == "Source directory" for t in app.text_input)
    assert any("API charges" in c.label for c in app.checkbox)
    app.selectbox(key="mode").set_value("demo").run()
    assert not app.text_input
    assert not app.checkbox
    assert not manager.list_runs()


def test_revision_and_decision_fields_are_conditional(tmp_path, monkeypatch):
    manager = RunManager(tmp_path)
    monkeypatch.setattr("agent_orchestrator.lifecycle.runner.RunManager", lambda: manager)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=15).run()
    app.button[0].click().run()
    assert not any(t.label == "New requirement" for t in app.text_area)
    assert not any(c.language == "diff" for c in app.code)
    next(s for s in app.selectbox if s.label == "View proposed changes for revision").set_value(1).run()
    assert any(c.language == "diff" for c in app.code)
    next(s for s in app.selectbox if s.label == "Decision").set_value("revise").run()
    assert any(t.label == "New requirement" for t in app.text_area)
    assert not any("authorize" in c.label for c in app.checkbox)
    next(s for s in app.selectbox if s.label == "Decision").set_value("approve").run()
    assert not any(t.label == "New requirement" for t in app.text_area)
    assert any("authorize" in c.label for c in app.checkbox)
    assert len(manager.list_runs()) == 1
    assert manager.list_runs()[0]["status"] == "awaiting_patch"


def test_approve_with_note_and_test_permission_reaches_final_review(tmp_path, monkeypatch):
    manager = RunManager(tmp_path)
    monkeypatch.setattr("agent_orchestrator.lifecycle.runner.RunManager", lambda: manager)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=15).run()
    app.button[0].click().run()
    next(b for b in app.button if b.label == "Approve and continue").click().run()
    assert app.error
    assert manager.list_runs()[0]["status"] == "awaiting_patch"
    next(t for t in app.text_area if t.label == "Review note (required)").set_value("Reviewed demo code and tests")
    next(c for c in app.checkbox if "authorize" in c.label).check()
    next(b for b in app.button if b.label == "Approve and continue").click().run()
    assert not app.exception
    assert manager.list_runs()[0]["status"] == "awaiting_release"
    assert not any("authorize" in c.label for c in app.checkbox)
    app.run()
    assert len(manager.list_runs()) == 1
    assert manager.list_runs()[0]["status"] == "awaiting_release"
