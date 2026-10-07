"""One provider adapter; agents depend only on the small StructuredLLM protocol."""

import os
from typing import Literal, Protocol, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

Output = TypeVar("Output", bound=BaseModel)


class StructuredLLM(Protocol):
    def generate(self, schema: type[Output], *, instructions: str, context: str) -> Output:
        """Return validated data matching schema, or raise an error."""
        ...


class OpenAICompatibleLLM:
    def __init__(
        self,
        client: ChatOpenAI,
        method: Literal["json_schema", "function_calling"] = "json_schema",
    ) -> None:
        self.client = client
        self.method = method

    def generate(self, schema: type[Output], *, instructions: str, context: str) -> Output:
        structured = self.client.with_structured_output(schema, method=self.method)
        result = structured.invoke([
            ("system", instructions),
            ("human", context),
        ])
        # Pydantic validates output locally, including our dependency invariants.
        return schema.model_validate(result)


def llm_from_environment() -> StructuredLLM:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not api_key or api_key == "replace-me" or not model:
        raise ValueError("Set LLM_API_KEY and LLM_MODEL in .env or your environment")
    method = os.getenv("LLM_STRUCTURED_OUTPUT_METHOD", "json_schema")
    if method not in ("json_schema", "function_calling"):
        raise ValueError("Unsupported LLM_STRUCTURED_OUTPUT_METHOD")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    if not 0 < timeout <= 300:
        raise ValueError("LLM_TIMEOUT_SECONDS must be between 0 and 300 seconds")
    client = ChatOpenAI(
        api_key=api_key,
        model=model,
        base_url=os.getenv("LLM_BASE_URL") or None,
        timeout=timeout,
        max_retries=0,  # No hidden SDK retries; a future graph controller will own them.
    )
    return OpenAICompatibleLLM(client, method=method)
