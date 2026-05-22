"""Async Claude API client with retry, rate limiting, and cost tracking."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# Model to use for all tailoring calls
MODEL = "claude-sonnet-4-20250514"

# Cost per 1M tokens in GBP (approximate, Sonnet pricing)
COST_INPUT_PER_M_GBP = 2.40
COST_OUTPUT_PER_M_GBP = 12.00

# Log directory for usage tracking
_LOG_DIR = Path("data/logs")


class ClaudeClient:
    """Async wrapper around the Anthropic API with rate limiting and cost tracking.

    Attributes:
        model: Claude model ID to use.
        temperature: Default temperature for completions.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL,
        temperature: float = 0.3,
        max_concurrent: int = 10,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.model = model
        self.temperature = temperature
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> str:
        """Send a single completion request and return the text response.

        Args:
            system: System prompt.
            user: User message.
            max_tokens: Maximum tokens in response.
            temperature: Override default temperature if provided.

        Returns:
            Response text from Claude.
        """
        temp = temperature if temperature is not None else self.temperature
        response = await self._call_with_retry(
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temp,
        )
        content = response.content[0].text if response.content else ""
        self._log_usage(response.usage, "complete")
        return content

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a completion request and parse the response as JSON.

        Retries up to 3 times if the response is not valid JSON.

        Args:
            system: System prompt (should instruct JSON output).
            user: User message.
            max_tokens: Maximum tokens in response.

        Returns:
            Parsed JSON dict.

        Raises:
            ValueError: If JSON parsing fails after all retries.
        """
        json_system = system + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, no explanation."
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                text = await self.complete(json_system, user, max_tokens)
                # Strip any markdown code fences if present
                cleaned = text.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("JSON parse failed (attempt %d/3): %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(1)

        raise ValueError(f"Claude did not return valid JSON after 3 attempts: {last_error}")

    async def complete_structured(
        self,
        system: str,
        user: str,
        schema_description: str,
    ) -> dict[str, Any]:
        """Use tool_use to enforce structured JSON output matching a schema.

        Args:
            system: System prompt.
            user: User message.
            schema_description: Plain-English description of the output schema.

        Returns:
            Structured dict from tool_use input.
        """
        tool_def = {
            "name": "structured_output",
            "description": f"Return structured data matching: {schema_description}",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        }
        async with self._semaphore:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[tool_def],
                tool_choice={"type": "any"},
            )
        self._log_usage(response.usage, "complete_structured")

        for block in response.content:
            if block.type == "tool_use" and block.name == "structured_output":
                return block.input  # type: ignore[return-value]

        # Fallback: try to parse text content as JSON
        text_blocks = [b for b in response.content if hasattr(b, "text")]
        if text_blocks:
            return json.loads(text_blocks[0].text)  # type: ignore[return-value]
        raise ValueError("No structured output returned from Claude")

    async def _call_with_retry(
        self,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        retries: int = 3,
    ) -> Any:
        """Execute an API call with exponential backoff on rate limit errors.

        Args:
            system: System prompt.
            user: User message.
            max_tokens: Max tokens.
            temperature: Sampling temperature.
            retries: Number of retry attempts.

        Returns:
            Raw Anthropic Message response.
        """
        delay = 2.0
        async with self._semaphore:
            for attempt in range(retries):
                try:
                    return await self._client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                    )
                except anthropic.RateLimitError:
                    if attempt == retries - 1:
                        raise
                    logger.warning("Rate limited — sleeping %.1fs (attempt %d/%d)", delay, attempt + 1, retries)
                    await asyncio.sleep(delay)
                    delay *= 2
                except anthropic.APIError as exc:
                    if attempt == retries - 1:
                        raise
                    logger.warning("API error %s — retry %d/%d", exc, attempt + 1, retries)
                    await asyncio.sleep(delay)
                    delay *= 2
        raise RuntimeError("Unreachable")  # pragma: no cover

    def _log_usage(self, usage: Any, call_type: str) -> None:
        """Append token usage and cost estimate to the JSONL log file.

        Args:
            usage: Anthropic usage object with input_tokens / output_tokens.
            call_type: Label for the log entry.
        """
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            in_tokens = getattr(usage, "input_tokens", 0) or 0
            out_tokens = getattr(usage, "output_tokens", 0) or 0
            cost = (in_tokens / 1_000_000 * COST_INPUT_PER_M_GBP) + (
                out_tokens / 1_000_000 * COST_OUTPUT_PER_M_GBP
            )
            record = {
                "ts": datetime.utcnow().isoformat(),
                "model": self.model,
                "call_type": call_type,
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "cost_gbp": round(cost, 6),
            }
            with (_LOG_DIR / "claude_usage.jsonl").open("a") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:  # pragma: no cover
            logger.debug("Usage log write failed: %s", exc)
