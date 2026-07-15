"""Loopback-only llama.cpp and Ollama clients for reproducible benchmarks."""
from __future__ import annotations

import ast
import json
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .contracts import ModelSpec

_MAX_JSON_ATTEMPTS = 3
_DEFAULT_TIMEOUT_SECONDS = 1800.0


class BenchmarkInferenceError(RuntimeError):
    """Base class for typed inference failures stored by the runner."""


class BenchmarkHTTPError(BenchmarkInferenceError):
    pass


class BenchmarkTimeoutError(BenchmarkInferenceError):
    pass


class BenchmarkMalformedJSONError(BenchmarkInferenceError):
    pass


class GenerationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int
    duration_ms: float
    status_code: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    load_duration_ms: float | None = None
    prompt_eval_duration_ms: float | None = None
    eval_duration_ms: float | None = None
    tokens_per_second: float | None = None
    error: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


def _strip_model_markup(text: str) -> str:
    value = re.sub(r"<\|channel>.*?<channel\|>", "", text, flags=re.DOTALL)
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL).strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    return value.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_model_markup(text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            result = ast.literal_eval(cleaned)
        except (SyntaxError, ValueError) as exc:
            raise BenchmarkMalformedJSONError("model response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise BenchmarkMalformedJSONError("model response must be a JSON object")
    return result


class BenchmarkLLMClient:
    """Small service-compatible client that bypasses profile.yaml entirely."""

    def __init__(
        self,
        spec: ModelSpec,
        seed: int,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.spec = spec
        self.seed = seed
        self.observations: list[GenerationObservation] = []
        self._client = httpx.AsyncClient(
            base_url=str(spec.endpoint).rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _request(self, system: str, user: str, max_tokens: int) -> tuple[str, dict[str, Any]]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self.spec.runtime == "ollama":
            return "/api/chat", {
                "model": self.spec.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": "json",
                "options": {
                    "seed": self.seed,
                    "temperature": self.spec.temperature,
                    "num_predict": max_tokens,
                    "num_ctx": self.spec.context_size,
                },
            }
        return "/v1/chat/completions", {
            "model": self.spec.model,
            "messages": messages,
            "stream": False,
            "temperature": self.spec.temperature,
            "seed": self.seed,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_format": "none",
        }

    def _content(self, payload: dict[str, Any]) -> str:
        if self.spec.runtime == "ollama":
            return str(payload.get("message", {}).get("content", ""))
        choices = payload.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", ""))

    def _observation(
        self,
        *,
        attempt: int,
        duration_ms: float,
        status_code: int | None,
        payload: dict[str, Any],
        error: str | None,
    ) -> GenerationObservation:
        if self.spec.runtime == "ollama":
            eval_count = payload.get("eval_count")
            eval_duration_ns = payload.get("eval_duration")
            tokens_per_second = None
            if isinstance(eval_count, int) and isinstance(eval_duration_ns, (int, float)) and eval_duration_ns:
                tokens_per_second = eval_count / (eval_duration_ns / 1_000_000_000)
            return GenerationObservation(
                attempt=attempt,
                duration_ms=duration_ms,
                status_code=status_code,
                prompt_tokens=payload.get("prompt_eval_count"),
                completion_tokens=eval_count,
                load_duration_ms=_ns_to_ms(payload.get("load_duration")),
                prompt_eval_duration_ms=_ns_to_ms(payload.get("prompt_eval_duration")),
                eval_duration_ms=_ns_to_ms(eval_duration_ns),
                tokens_per_second=tokens_per_second,
                error=error,
                raw_metadata={
                    key: payload[key]
                    for key in ("done", "done_reason", "total_duration")
                    if key in payload
                },
            )

        usage = payload.get("usage") or {}
        timings = payload.get("timings") or {}
        return GenerationObservation(
            attempt=attempt,
            duration_ms=duration_ms,
            status_code=status_code,
            prompt_tokens=usage.get("prompt_tokens", timings.get("prompt_n")),
            completion_tokens=usage.get("completion_tokens", timings.get("predicted_n")),
            prompt_eval_duration_ms=timings.get("prompt_ms"),
            eval_duration_ms=timings.get("predicted_ms"),
            tokens_per_second=timings.get("predicted_per_second"),
            error=error,
            raw_metadata={"timings": timings} if timings else {},
        )

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        del schema  # Production services currently supply their JSON contract in the prompt.
        path, request_payload = self._request(system, user, max_tokens)
        last_error: BenchmarkMalformedJSONError | None = None
        for attempt in range(1, _MAX_JSON_ATTEMPTS + 1):
            started = time.monotonic()
            try:
                response = await self._client.post(path, json=request_payload)
            except httpx.TimeoutException as exc:
                duration_ms = (time.monotonic() - started) * 1000
                self.observations.append(
                    self._observation(
                        attempt=attempt,
                        duration_ms=duration_ms,
                        status_code=None,
                        payload={},
                        error="timeout",
                    )
                )
                raise BenchmarkTimeoutError(f"{self.spec.id} inference timed out") from exc

            duration_ms = (time.monotonic() - started) * 1000
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {}
            if response.status_code >= 400:
                self.observations.append(
                    self._observation(
                        attempt=attempt,
                        duration_ms=duration_ms,
                        status_code=response.status_code,
                        payload=payload,
                        error="http_error",
                    )
                )
                raise BenchmarkHTTPError(
                    f"{self.spec.id} returned HTTP {response.status_code}: {payload}"
                )

            try:
                result = _parse_json_object(self._content(payload))
            except BenchmarkMalformedJSONError as exc:
                last_error = exc
                self.observations.append(
                    self._observation(
                        attempt=attempt,
                        duration_ms=duration_ms,
                        status_code=response.status_code,
                        payload=payload,
                        error="malformed_json",
                    )
                )
                continue

            self.observations.append(
                self._observation(
                    attempt=attempt,
                    duration_ms=duration_ms,
                    status_code=response.status_code,
                    payload=payload,
                    error=None,
                )
            )
            return result

        raise BenchmarkMalformedJSONError(
            f"{self.spec.id} did not return a JSON object after {_MAX_JSON_ATTEMPTS} attempts"
        ) from last_error


def _ns_to_ms(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return value / 1_000_000
