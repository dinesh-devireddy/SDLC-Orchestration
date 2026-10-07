"""Check the provider adapter without network access or credentials."""

from unittest.mock import MagicMock

import pytest

from agent_orchestrator.llm import OpenAICompatibleLLM, llm_from_environment
from agent_orchestrator.models import RequirementAnalysis


def test_adapter_requests_schema_and_validates_output():
    client = MagicMock()
    client.with_structured_output.return_value.invoke.return_value = {
        "normalized_requirement": "Support expiration.",
        "ambiguities": [], "assumptions": [],
        "acceptance_criteria": ["Expired URLs do not redirect."],
    }
    result = OpenAICompatibleLLM(client).generate(
        RequirementAnalysis, instructions="Analyze", context="Requirement"
    )
    client.with_structured_output.assert_called_once_with(RequirementAnalysis, method="json_schema")
    client.with_structured_output.return_value.invoke.assert_called_once_with([
        ("system", "Analyze"), ("human", "Requirement")
    ])
    assert isinstance(result, RequirementAnalysis)


def test_environment_config_disables_sdk_retries(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("agent_orchestrator.llm.ChatOpenAI", factory)
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUT_METHOD", "function_calling")
    llm = llm_from_environment()
    assert llm.method == "function_calling"
    assert factory.call_args.kwargs["max_retries"] == 0
    assert factory.call_args.kwargs["timeout"] == 15
    assert factory.call_args.kwargs["base_url"] == "http://localhost:8000/v1"


def test_missing_configuration_fails_before_client_creation(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="Set LLM_API_KEY"):
        llm_from_environment()
