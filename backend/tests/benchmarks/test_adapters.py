from __future__ import annotations

import json

import httpx
import pytest

from benchmarks.adapters import BenchmarkHTTPError, BenchmarkLLMClient
from benchmarks.contracts import ModelSpec


def _response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.mark.asyncio
async def test_ollama_adapter_sends_seed_json_format_and_collects_metrics() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _response(
            {
                "message": {"role": "assistant", "content": '{"summary":"ok"}'},
                "done": True,
                "load_duration": 2_000_000,
                "prompt_eval_count": 120,
                "prompt_eval_duration": 30_000_000,
                "eval_count": 20,
                "eval_duration": 40_000_000,
            }
        )

    spec = ModelSpec(
        id="gemma4-e2b",
        runtime="ollama",
        model="gemma4:e2b",
        endpoint="http://127.0.0.1:11434",
        context_size=16384,
    )
    client = BenchmarkLLMClient(
        spec,
        seed=41,
        transport=httpx.MockTransport(handler),
    )

    result = await client.complete_json("system", "user", max_tokens=512)
    await client.aclose()

    assert result == {"summary": "ok"}
    assert captured["format"] == "json"
    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["options"] == {
        "seed": 41,
        "temperature": 0.3,
        "num_predict": 512,
        "num_ctx": 16384,
    }
    assert client.observations[0].prompt_tokens == 120
    assert client.observations[0].completion_tokens == 20
    assert client.observations[0].load_duration_ms == 2.0
    assert client.observations[0].eval_duration_ms == 40.0


@pytest.mark.asyncio
async def test_llamacpp_adapter_uses_openai_json_contract_and_timings() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        captured.update(json.loads(request.content))
        return _response(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": '{"summary":"ok"}'}}
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 16},
                "timings": {
                    "prompt_n": 80,
                    "prompt_ms": 25.0,
                    "predicted_n": 16,
                    "predicted_ms": 50.0,
                    "predicted_per_second": 12.5,
                },
            }
        )

    spec = ModelSpec(
        id="qwen35-4b",
        runtime="llamacpp",
        model="Qwen_Qwen3.5-4B-Q4_K_M.gguf",
        endpoint="http://127.0.0.1:8080",
        context_size=16384,
    )
    client = BenchmarkLLMClient(
        spec,
        seed=23,
        transport=httpx.MockTransport(handler),
    )

    result = await client.complete_json("system", "user", max_tokens=1024)
    await client.aclose()

    assert result == {"summary": "ok"}
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["seed"] == 23
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 1024
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert client.observations[0].prompt_tokens == 80
    assert client.observations[0].completion_tokens == 16
    assert client.observations[0].eval_duration_ms == 50.0


@pytest.mark.asyncio
async def test_adapter_retries_malformed_json_and_records_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        content = "not json" if attempts < 3 else "{'summary': 'repaired'}"
        return _response(
            {
                "message": {"role": "assistant", "content": content},
                "done": True,
            }
        )

    spec = ModelSpec(
        id="qwen3-8b",
        runtime="ollama",
        model="qwen3:8b",
        endpoint="http://localhost:11434",
        context_size=16384,
    )
    client = BenchmarkLLMClient(spec, seed=11, transport=httpx.MockTransport(handler))

    result = await client.complete_json("system", "user")
    await client.aclose()

    assert result == {"summary": "repaired"}
    assert attempts == 3
    assert len(client.observations) == 3
    assert client.observations[0].error == "malformed_json"
    assert client.observations[2].error is None


@pytest.mark.asyncio
async def test_adapter_raises_typed_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response({"error": "model unavailable"}, status_code=404)

    spec = ModelSpec(
        id="missing",
        runtime="ollama",
        model="missing:model",
        endpoint="http://127.0.0.1:11434",
        context_size=16384,
    )
    client = BenchmarkLLMClient(spec, seed=11, transport=httpx.MockTransport(handler))

    with pytest.raises(BenchmarkHTTPError, match="404"):
        await client.complete_json("system", "user")
    await client.aclose()

    assert client.observations[0].status_code == 404
