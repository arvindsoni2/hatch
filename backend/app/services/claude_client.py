"""Provider-agnostic LLM client wrapping llm_factory.

Replaces the previous Anthropic-SDK-specific ClaudeClient. All services
that previously called ClaudeClient (email_generator, digest_service,
feedback_generator, etc.) continue to work unchanged via the same
complete() / complete_json() / complete_structured() interface, but now
honour whatever provider is configured in profile.yaml.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.tools.llm_factory import get_json_model, get_primary_model

logger = logging.getLogger(__name__)

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond ONLY with valid JSON. "
    "No markdown, no code blocks, no explanation."
)


class ClaudeClient:
    """Provider-agnostic LLM client using the LLM factory.

    Interface is backwards-compatible with the previous Anthropic-specific
    implementation so existing callers (EmailGenerator, DigestService, etc.)
    work without changes.
    """

    def __init__(
        self,
        api_key: str | None = None,  # kept for call-site compatibility; ignored
        model: str | None = None,    # kept for compatibility; profile.yaml controls model
        temperature: float = 0.3,
        max_concurrent: int = 10,
    ) -> None:
        self._temperature = temperature

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> str:
        """Send a completion request and return the text response."""
        llm = get_primary_model()
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = await llm.ainvoke(messages)
        content = response.content
        return content if isinstance(content, str) else str(content)

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a completion request and parse the response as JSON.

        Retries up to 3 times if the response is not valid JSON.
        Uses get_json_model() to pass format="json" to Ollama for token-level
        JSON constraint.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                llm = get_json_model()
                messages = [SystemMessage(content=system + _JSON_INSTRUCTION), HumanMessage(content=user)]
                response = await llm.ainvoke(messages)
                text = response.content if isinstance(response.content, str) else str(response.content)
                # Strip Qwen3 / DeepSeek reasoning blocks before JSON parsing
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                cleaned = text.strip()
                # Strip markdown code fences
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    # Local models (Gemma, Llama) often wrap JSON in prose — extract it
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if match:
                        return json.loads(match.group())
                    raise
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("JSON parse failed (attempt %d/3): %s", attempt + 1, exc)

        raise ValueError(f"LLM did not return valid JSON after 3 attempts: {last_error}")

    async def complete_structured(
        self,
        system: str,
        user: str,
        schema_description: str,
    ) -> dict[str, Any]:
        """Return structured JSON matching the given schema description."""
        augmented_system = (
            f"{system}\n\nReturn a JSON object matching: {schema_description}"
            + _JSON_INSTRUCTION
        )
        text = await self.complete(augmented_system, user)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(cleaned)
