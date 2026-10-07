"""Exercise browser-session behavior without making provider requests."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from test_workflow import ANALYSIS, ScriptedLLM

APP = Path(__file__).parents[1] / "planning_demo.py"


def test_ui_runs_only_on_submit_and_keeps_result_on_rerun(monkeypatch):
    llm = ScriptedLLM()
    monkeypatch.setattr("agent_orchestrator.llm.llm_from_environment", lambda: llm)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    assert not llm.calls
    app.button[0].click().run()
    assert not app.exception
    assert len(llm.calls) == 2
    assert app.session_state["result"]["plan"]["execution_order"] == ["T1", "T2"]
    assert app.session_state["completed"] == ["requirement_agent", "planning_agent"]
    app.run()
    assert len(llm.calls) == 2
    assert not app.exception


def test_blank_submission_clears_stale_results_and_does_not_call_llm(monkeypatch):
    llm = ScriptedLLM()
    monkeypatch.setattr("agent_orchestrator.llm.llm_from_environment", lambda: llm)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.button[0].click().run()
    app.text_area[0].set_value("   ")
    app.button[0].click().run()
    assert not app.exception
    assert len(llm.calls) == 2
    assert app.error[0].value == "Enter a requirement before generating a plan."
    assert "result" not in app.session_state


def test_planning_failure_preserves_analysis_and_redacts_error(monkeypatch):
    class FailingPlanner(ScriptedLLM):
        def generate(self, schema, **kwargs):
            if self.calls:
                raise RuntimeError("secret provider response")
            return super().generate(schema, **kwargs)

    llm = FailingPlanner()
    monkeypatch.setattr("agent_orchestrator.llm.llm_from_environment", lambda: llm)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["result"]["analysis"] == ANALYSIS
    assert app.session_state["result"]["plan"] is None
    assert app.session_state["completed"] == ["requirement_agent"]
    assert "RuntimeError" in app.error[0].value
    assert "secret" not in app.error[0].value


def test_configuration_failure_is_visible_without_crashing(monkeypatch):
    def missing_config():
        raise ValueError("missing key")

    monkeypatch.setattr("agent_orchestrator.llm.llm_from_environment", missing_config)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.button[0].click().run()
    assert not app.exception
    assert "Check your .env configuration" in app.error[0].value
    assert "result" not in app.session_state
