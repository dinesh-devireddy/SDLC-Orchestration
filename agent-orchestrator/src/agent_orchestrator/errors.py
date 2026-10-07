"""Safe, actionable diagnostics shared by the CLI and UI."""

from openai import RateLimitError


def describe_error(error: Exception) -> str:
    if isinstance(error, RateLimitError):
        # Only render known codes and our own text, never raw provider messages.
        guidance = {
            "insufficient_quota": "API quota is unavailable. Check API credits, billing, and project/organization limits.",
            "credit_balance_exhausted": "API credits are exhausted. Check your API billing balance.",
            "organization_spend_limit_exceeded": "The organization API spend limit was reached. Check organization limits.",
            "project_spend_limit_exceeded": "The project API spend limit was reached. Check project limits.",
            "organization_usage_limit_exceeded": "The organization API usage limit was reached. Check your approved usage limit.",
        }
        code = error.code
        if code not in guidance and error.type == "insufficient_quota":
            code = "insufficient_quota"
        if code in guidance:
            return f"Run stopped ({code}). {guidance[code]} Retrying will not fix this until API access is restored."
        if code in ("rate_limit_exceeded", "slow_down"):
            return (
                f"Run stopped ({code}). The provider is throttling requests or tokens. "
                "Wait before resubmitting and check the model's API rate limits."
            )
        return (
            "Run stopped (HTTP 429). The provider did not supply a recognized cause. "
            "Check both API billing/quota and request/token rate limits."
        )
    return (
        f"Run stopped ({type(error).__name__}). Check your .env configuration, "
        "model access, endpoint, and structured-output support."
    )
