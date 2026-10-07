"""Offline tests use the real LangGraph runtime with a scripted LLM boundary."""

import json

import pytest
from pydantic import ValidationError

from agent_orchestrator import cli
from agent_orchestrator.models import EngineeringPlan, EngineeringState, RequirementAnalysis
from agent_orchestrator.workflow import run_workflow

REQUIREMENT = "Add expiration support to shortened URLs."
ANALYSIS = {
    "normalized_requirement": "Support optional expiration for shortened URLs.",
    "ambiguities": ["Which HTTP status should an expired URL return?"],
    "assumptions": ["Proposed: existing URLs remain non-expiring; needs confirmation."],
    "acceptance_criteria": ["A URL cannot redirect at or after its expiration instant."],
}
PLAN = {
    "tasks": [
        {"id": "T1", "description": "Confirm expiration semantics and prerequisites.", "depends_on": []},
        {"id": "T2", "description": "Implement expiration and boundary tests after approval.", "depends_on": ["T1"]},
    ],
    "execution_order": ["T1", "T2"],
    "risks": ["No URL shortener exists yet; implementation requires a service foundation."],
}


class ScriptedLLM:
    def __init__(self, analysis=None, plan=None):
        self.analysis = ANALYSIS if analysis is None else analysis
        self.plan = PLAN if plan is None else plan
        self.calls = []

    def generate(self, schema, *, instructions, context):
        self.calls.append((schema, json.loads(context)))
        return schema.model_validate(
            self.analysis if schema is RequirementAnalysis else self.plan
        )


def test_real_graph_hands_analysis_to_planner_and_preserves_input():
    llm = ScriptedLLM()
    state = run_workflow(REQUIREMENT, llm)
    assert [schema for schema, _ in llm.calls] == [RequirementAnalysis, EngineeringPlan]
    assert llm.calls[1][1] == {"requirement": REQUIREMENT, "analysis": ANALYSIS}
    assert state.model_dump() == {"requirement": REQUIREMENT, "analysis": ANALYSIS, "plan": PLAN}


def test_invalid_analysis_stops_before_planning():
    llm = ScriptedLLM(analysis={**ANALYSIS, "acceptance_criteria": []})
    with pytest.raises(ValidationError):
        run_workflow(REQUIREMENT, llm)
    assert len(llm.calls) == 1


@pytest.mark.parametrize("changes", [
    {"execution_order": ["T2", "T1"]},
    {"execution_order": ["T1", "T1"]},
    {"execution_order": ["T1"]},
    {"tasks": [PLAN["tasks"][0], PLAN["tasks"][0]]},
    {"tasks": [PLAN["tasks"][0], {**PLAN["tasks"][1], "depends_on": ["missing"]}]},
    {"tasks": [PLAN["tasks"][0], {**PLAN["tasks"][1], "depends_on": ["T2"]}]},
    {"tasks": [{**PLAN["tasks"][0], "depends_on": ["T2"]}, PLAN["tasks"][1]]},
    {"tasks": [PLAN["tasks"][0], {**PLAN["tasks"][1], "depends_on": ["T1", "T1"]}]},
])
def test_invalid_dependency_graph_is_rejected(changes):
    with pytest.raises(ValidationError):
        run_workflow(REQUIREMENT, ScriptedLLM(plan={**PLAN, **changes}))


def test_blank_requirement_never_calls_llm():
    llm = ScriptedLLM()
    with pytest.raises(ValidationError):
        run_workflow("   ", llm)
    assert llm.calls == []


def test_cli_prints_complete_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "llm_from_environment", ScriptedLLM)
    monkeypatch.setattr("sys.argv", ["engineering-plan", REQUIREMENT])
    assert cli.main() == 0
    output = capsys.readouterr()
    state = EngineeringState.model_validate_json(output.out)
    assert state.plan.execution_order == ["T1", "T2"]
    assert output.err == ""


def test_cli_failure_is_nonzero_and_does_not_leak_provider_response(monkeypatch, capsys):
    class FailingLLM:
        calls = 0

        def generate(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("sensitive provider response")

    llm = FailingLLM()
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "llm_from_environment", lambda: llm)
    monkeypatch.setattr("sys.argv", ["engineering-plan"])
    assert cli.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "sensitive" not in output.err
    assert "RuntimeError" in output.err
    assert llm.calls == 1
