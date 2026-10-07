import httpx
import pytest
from langchain_openai.chat_models.base import OpenAIRateLimitError

from agent_orchestrator.errors import describe_error


@pytest.mark.parametrize("code,kind,expected", [
    ("insufficient_quota", "insufficient_quota", "API quota is unavailable"),
    ("credit_balance_exhausted", "insufficient_quota", "credits are exhausted"),
    ("project_spend_limit_exceeded", "insufficient_quota", "project API spend limit"),
    ("organization_spend_limit_exceeded", "insufficient_quota", "organization API spend limit"),
    ("organization_usage_limit_exceeded", "insufficient_quota", "organization API usage limit"),
    ("rate_limit_exceeded", "tokens", "throttling"),
    ("slow_down", "rate_limit_error", "throttling"),
    (None, "insufficient_quota", "API quota is unavailable"),
    ("secret unknown code", "secret type", "HTTP 429"),
])
def test_rate_limit_diagnostics_are_specific_and_redacted(code, kind, expected):
    error = OpenAIRateLimitError(
        "secret provider message",
        response=httpx.Response(429, request=httpx.Request("POST", "https://example.test")),
        body={"code": code, "type": kind, "message": "secret provider message"},
    )
    message = describe_error(error)
    assert expected in message
    assert "secret" not in message
