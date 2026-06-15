"""Provider-agnostic LLM client wrapping llm_factory.

All services that previously used ClaudeClient continue to work via the same
complete() / complete_json() / complete_structured() interface, honouring
whatever provider is configured in profile.yaml.
"""
from __future__ import annotations

import asyncio
import ast
import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel as PydanticBaseModel

from ..agents.tools.llm_factory import get_json_model, get_primary_model, record_trace
from ..agents.tools.profile_loader import load_profile

logger = logging.getLogger(__name__)

_LLM_CALL_TIMEOUT_SECONDS = 1800

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond ONLY with valid JSON. "
    "No markdown, no code blocks, no explanation."
)


class LLMClient:
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
        model_name = load_profile().llm.primary_model
        llm = get_primary_model()
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        t0 = time.monotonic()
        response = await asyncio.wait_for(
            llm.bind(max_tokens=max_tokens).ainvoke(messages),
            timeout=_LLM_CALL_TIMEOUT_SECONDS,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        record_trace(model_name, duration_ms, text)
        return text

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        schema: type[PydanticBaseModel] | None = None,
    ) -> dict[str, Any]:
        """Send a completion request and parse the response as JSON.

        schema: when provided on the llamacpp path, upgrades response_format
        from json_object to json_schema (grammar-enforced). Pass-through only;
        the parse-and-retry loop below is unchanged.

        Retries up to 3 times if the response is not valid JSON.
        Uses get_json_model() to pass format="json" to Ollama for token-level
        JSON constraint.
        """
        model_name = load_profile().llm.primary_model
        # Qwen3 generates <think>...</think> chains at 1-2 t/s; for structured
        # JSON tasks CoT wastes tokens and causes 300s HTTP timeouts. /no_think
        # disables it while keeping the same model and grammar enforcement.
        no_think = "/no_think\n" if "qwen" in model_name.lower() else ""
        last_error: Exception | None = None
        cleaned = ""
        for attempt in range(3):
            try:
                llm = get_json_model(schema=schema)
                messages = [SystemMessage(content=no_think + system + _JSON_INSTRUCTION), HumanMessage(content=user)]
                t0 = time.monotonic()
                response = await asyncio.wait_for(
                    llm.bind(max_tokens=max_tokens).ainvoke(messages),
                    timeout=_LLM_CALL_TIMEOUT_SECONDS,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)
                text = response.content if isinstance(response.content, str) else str(response.content)
                record_trace(model_name, duration_ms, text)
                # Strip reasoning blocks: Qwen3/DeepSeek <think>...</think>
                # and Gemma 4 channel form <|channel>...<channel|>
                text = re.sub(r"<\|channel>.*?<channel\|>", "", text, flags=re.DOTALL)
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                cleaned = text.strip()
                # Strip markdown code fences
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    # gemma4 / other local models sometimes emit Python-style single-quoted
                    # dicts — ast.literal_eval handles those safely.
                    try:
                        result = ast.literal_eval(cleaned)
                        if isinstance(result, (dict, list)):
                            return result  # type: ignore[return-value]
                    except (ValueError, SyntaxError):
                        pass
                    # Local models often wrap JSON in prose — try to extract it.
                    # Try object first, then array (Ollama format=json forces objects).
                    for pattern in (r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', r'\[.*\]', r'\{.*\}'):
                        match = re.search(pattern, cleaned, re.DOTALL)
                        if match:
                            try:
                                return json.loads(match.group())
                            except json.JSONDecodeError:
                                try:
                                    result = ast.literal_eval(match.group())
                                    if isinstance(result, (dict, list)):
                                        return result  # type: ignore[return-value]
                                except (ValueError, SyntaxError):
                                    pass
                    raise
            except Exception as exc:
                last_error = exc
                logger.warning("JSON parse failed (attempt %d/3): %s", attempt + 1, exc)
                if attempt == 0:
                    logger.debug("Raw LLM output (first 500 chars): %r", cleaned[:500])

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
        text = re.sub(r"<\|channel>.*?<channel\|>", "", text, flags=re.DOTALL)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                result = ast.literal_eval(cleaned)
                if isinstance(result, (dict, list)):
                    return result  # type: ignore[return-value]
            except (ValueError, SyntaxError):
                pass
            for pattern in (r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', r'\[.*\]', r'\{.*\}'):
                match = re.search(pattern, cleaned, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        try:
                            result = ast.literal_eval(match.group())
                            if isinstance(result, (dict, list)):
                                return result  # type: ignore[return-value]
                        except (ValueError, SyntaxError):
                            pass
            raise
