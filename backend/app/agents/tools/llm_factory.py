"""LangChain model factory — provider-agnostic LLM access for all agents.

Agents call get_triage_model() or get_primary_model(). The provider and model
names come from profile.yaml so users can switch between Anthropic, OpenAI,
Google, Ollama, Azure, or Bedrock without touching any agent code.

Never import provider SDKs (anthropic, openai, google.generativeai) directly
in agent code. Always go through this module.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import time
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from .context_budgets import PRIMARY_CTX
from .profile_loader import load_profile

logger = logging.getLogger(__name__)

_MODELS_YAML = Path(__file__).parent.parent.parent / "config" / "models.yaml"


@functools.lru_cache(maxsize=1)
def _load_cost_table() -> dict[str, tuple[float, float]]:
    """Load per-million-token pricing from config/models.yaml."""
    try:
        with _MODELS_YAML.open() as fh:
            data = yaml.safe_load(fh)
        table: dict[str, tuple[float, float]] = {}
        for fragment, entry in (data.get("cost_table") or {}).items():
            table[fragment] = (float(entry["input_per_1m"]), float(entry["output_per_1m"]))
        return table
    except Exception:
        logger.warning("Could not load %s — cost estimates will be zero.", _MODELS_YAML)
        return {}


try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:
    _BaseCallbackHandler = object  # type: ignore[assignment,misc]

# ── In-memory LLM trace ring buffer ──────────────────────────────────────────

@dataclass
class _LLMTrace:
    id: int
    ts: str
    model: str
    duration_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    response_preview: str

_trace_counter: int = 0
_trace_buffer: deque[_LLMTrace] = deque(maxlen=100)


class CostTrackingCallback(_BaseCallbackHandler):  # type: ignore[misc]
    """LangChain callback that captures token usage and queues CostTracking rows.

    Usage:
        cb = CostTrackingCallback(agent_name="scorer", model="gemini-2.5-flash", job_id=job_id)
        llm.invoke(prompt, config={"callbacks": [cb]})
        await cb.flush(db)
    """

    def __init__(self, agent_name: str, model: str, job_id: str | None = None) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.model = model
        self.job_id = job_id
        self._pending: list[dict[str, Any]] = []

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = (response.llm_output or {}).get("token_usage", {})
        tokens_in = usage.get("prompt_tokens") or usage.get("input_token_count") or 0
        tokens_out = usage.get("completion_tokens") or usage.get("generated_token_count") or 0
        if not tokens_in and not tokens_out:
            text = " ".join(
                g.text for gen in response.generations for g in gen if hasattr(g, "text")
            )
            tokens_out = estimate_tokens(text)
        cost = estimate_cost(self.model, tokens_in, tokens_out)
        self._pending.append({
            "agent_name": self.agent_name,
            "model": self.model,
            "job_id": self.job_id,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_estimate": cost,
        })

    async def flush(self, db: Any) -> None:
        """Write all queued CostTracking rows to the database."""
        if not self._pending:
            return
        from ...models.cost_tracking import CostTracking
        for row in self._pending:
            db.add(CostTracking(**row))
        await db.flush()
        self._pending.clear()


class _LatencyCallback(_BaseCallbackHandler):  # type: ignore[misc]
    """Always-on callback attached to every model to record latency + response preview."""

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model = model_name
        self._t0: float = 0.0

    def on_chat_model_start(self, _serialized: dict, messages: list, **kwargs: Any) -> None:
        self._t0 = time.monotonic()

    def on_llm_start(self, _serialized: dict, _prompts: list, **kwargs: Any) -> None:
        self._t0 = time.monotonic()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        global _trace_counter
        duration_ms = int((time.monotonic() - self._t0) * 1000) if self._t0 else 0

        usage = (response.llm_output or {}).get("token_usage", {})
        tokens_in = usage.get("prompt_tokens") or usage.get("input_token_count") or 0
        tokens_out = usage.get("completion_tokens") or usage.get("generated_token_count") or 0

        preview = ""
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or ""
                if not text:
                    msg = getattr(gen, "message", None)
                    if msg:
                        content = getattr(msg, "content", "")
                        text = content if isinstance(content, str) else str(content)
                if text:
                    preview = text[:300]
                    break
            if preview:
                break

        if not tokens_out:
            tokens_out = estimate_tokens(preview)

        _trace_counter += 1
        _trace_buffer.append(_LLMTrace(
            id=_trace_counter,
            ts=datetime.now(timezone.utc).isoformat(),
            model=self._model,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost(self._model, tokens_in, tokens_out),
            response_preview=preview,
        ))


def record_trace(
    model_name: str,
    duration_ms: int,
    content: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Record a completed LLM call to the trace buffer."""
    global _trace_counter
    tokens_out = tokens_out or estimate_tokens(content)
    _trace_counter += 1
    _trace_buffer.append(_LLMTrace(
        id=_trace_counter,
        ts=datetime.now(timezone.utc).isoformat(),
        model=model_name,
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=estimate_cost(model_name, tokens_in, tokens_out),
        response_preview=content[:300],
    ))


def get_llm_traces() -> list[dict[str, Any]]:
    """Return the last 100 LLM traces in reverse-chronological order."""
    return [
        {
            "id": t.id,
            "ts": t.ts,
            "model": t.model,
            "duration_ms": t.duration_ms,
            "tokens_in": t.tokens_in,
            "tokens_out": t.tokens_out,
            "cost_usd": t.cost_usd,
            "response_preview": t.response_preview,
        }
        for t in reversed(_trace_buffer)
    ]


def clear_llm_traces() -> None:
    """Wipe the in-memory trace buffer."""
    _trace_buffer.clear()


def _attach_tracer(model: BaseChatModel, model_name: str) -> BaseChatModel:
    """Attach the latency callback via with_config (Runnable-level, Pydantic-safe)."""
    try:
        return model.with_config({"callbacks": [_LatencyCallback(model_name)]})  # type: ignore[return-value]
    except Exception:
        return model


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return approximate USD cost for a model call based on config/models.yaml pricing."""
    model_lower = model.lower()
    for fragment, (in_rate, out_rate) in _load_cost_table().items():
        if fragment in model_lower:
            return round(
                (tokens_in / 1_000_000) * in_rate + (tokens_out / 1_000_000) * out_rate,
                6,
            )
    return 0.0


_TINY_MODEL_PATTERNS = ("e2b", ":0.6b", ":1b", ":1.7b", ":3b", "mini", "lite", "nano")

# Recommended Ollama defaults for CPU-only consumer hardware (see LLM-1/LLM-2 spec)
_OLLAMA_RECOMMENDED_ORDER = [
    "qwen3:30b-a3b",   # MoE, ~3B active — best quality on 32 GB
    "gemma4:26b-a4b",  # MoE, ~4B active — strong alternative on 16–32 GB
    "qwen3:4b",        # dense 4B Q4 — default primary for 8–16 GB
    "gemma4:e2b",      # edge-optimised triage model
]


def _maybe_add_think_token(system_prompt: str, provider: str, reasoning: bool, model_name: str = "") -> str:
    """Inject thinking-mode control into the system prompt (model-family-aware).

    - gemma4: thinking is OFF by default; prepend <|think|> only when reasoning=True
    - qwen3:  thinking is ON by default; prepend /no_think when reasoning=False
    - others: no-op
    """
    if provider != "ollama":
        return system_prompt
    m = model_name.lower()
    if m.startswith("gemma4"):
        if reasoning:
            return f"<|think|>\n{system_prompt}"
    elif m.startswith("qwen3"):
        if not reasoning:
            return f"/no_think\n{system_prompt}"
    return system_prompt


def _detect_ollama_model(llm_cfg: Any) -> str:
    """Query running Ollama instance and return the name of the first available model.

    Tries the configured base_url first, then falls back to the container-internal
    address. Raises ValueError with a helpful message if Ollama is unreachable or
    has no models pulled.
    """
    base = (llm_cfg.base_url or "http://host.docker.internal:11434").rstrip("/")
    candidates = list({base, "http://host.docker.internal:11434", "http://localhost:11434"})
    for url in candidates:
        try:
            req = urllib.request.urlopen(f"{url}/api/tags", timeout=3)
            models = json.loads(req.read()).get("models", [])
            if models:
                available = [m["name"] for m in models]
                # Prefer recommended models in priority order over arbitrary first
                for rec in _OLLAMA_RECOMMENDED_ORDER:
                    for a in available:
                        if a == rec or a.startswith(rec.split(":")[0] + ":"):
                            logger.info("Auto-detected Ollama model '%s' from %s", a, url)
                            return a
                name = available[0]
                logger.info("Auto-detected Ollama model '%s' from %s", name, url)
                return name
        except Exception:
            continue
    raise ValueError(
        "No model configured (triage_model / primary_model in profile.yaml is empty) "
        "and no Ollama models found. Pull a model first:\n"
        "  ollama pull qwen3:4b      # recommended primary (CPU-optimised, 8–16 GB RAM)\n"
        "  ollama pull gemma4:e2b   # recommended triage (fast, low memory)\n"
        "Then select the models in Settings → AI Provider."
    )


def _build_model(model_name: str, llm_cfg: Any) -> BaseChatModel:
    """Instantiate a LangChain chat model from profile LLM config."""
    if not model_name:
        if llm_cfg.provider == "ollama":
            model_name = _detect_ollama_model(llm_cfg)
        else:
            raise ValueError(
                f"LLM model name is empty for provider '{llm_cfg.provider}'. "
                "Set triage_model / primary_model in profile.yaml → llm section."
            )

    # llamacpp exposes an OpenAI-compatible API — use ChatOpenAI directly.
    # - timeout=3600: local LLM queue can stack 7 concurrent jobs × 180s/call = 1260s wait.
    # - num_ctx is NOT passed: the server --ctx-size flag governs context length.
    # - thinking/reasoning: Qwen3.5 thinking is controlled via extra_body chat_template_kwargs;
    #   must NOT touch _maybe_add_think_token (that is the Ollama gemma4 mechanism only).
    if llm_cfg.provider == "llamacpp":
        if not llm_cfg.base_url:
            raise ValueError(
                "provider='llamacpp' requires base_url to be set in profile.yaml → llm.base_url "
                "(e.g. 'http://llamacpp:8080/v1')"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        reasoning = getattr(llm_cfg, "reasoning", False)
        extra_body: dict[str, Any] = {
            "chat_template_kwargs": {"enable_thinking": bool(reasoning)},
        }
        return _attach_tracer(ChatOpenAI(
            model=model_name,
            base_url=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            timeout=1800,
            model_kwargs={"extra_body": extra_body},
        ), model_name)

    if llm_cfg.provider == "openrouter":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        api_key = os.getenv(llm_cfg.api_key_env or "OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured. Run: hatch secrets set openrouter")
        return _attach_tracer(ChatOpenAI(
            model=model_name,
            base_url=llm_cfg.base_url or "https://openrouter.ai/api/v1",
            openai_api_key=api_key,
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
        ), model_name)

    provider = llm_cfg.provider

    kwargs: dict[str, Any] = {
        "temperature": llm_cfg.temperature,
        "max_retries": llm_cfg.max_retries,
    }

    # Resolve API key from env (never read key directly from profile)
    if llm_cfg.api_key_env:
        api_key = os.getenv(llm_cfg.api_key_env, "")
        if api_key:
            kwargs["api_key"] = api_key

    # base_url is used for Ollama and Azure endpoints.
    # Ollama falls back to host.docker.internal so it works from inside containers
    # even when profile.yaml was saved without an explicit base_url.
    _ollama_default = "http://host.docker.internal:11434"
    effective_base_url = llm_cfg.base_url or (_ollama_default if llm_cfg.provider == "ollama" else None)
    if effective_base_url:
        kwargs["base_url"] = effective_base_url

    # Ollama-specific tuning:
    # - request_timeout: hard ceiling to prevent silent hangs on slow CPU inference
    # - num_ctx: Ollama defaults to 4096 but CV/CL prompts consume ~4K tokens alone
    # - thinking-mode is model-family-aware (gemma4 vs qwen3 — see _maybe_add_think_token)
    if llm_cfg.provider == "ollama":
        reasoning = getattr(llm_cfg, "reasoning", False)
        kwargs["request_timeout"] = 3600  # 1-hour ceiling; local LLM queue can run 20+ min
        kwargs["num_ctx"] = PRIMARY_CTX
        kwargs["format"] = "json"  # token-level JSON constraint — prevents markdown output
        # qwen3: thinking is ON by default; must explicitly disable unless reasoning=True
        if model_name.lower().startswith("qwen3"):
            kwargs["think"] = reasoning
        else:
            # gemma4 and others: reasoning token injected via _maybe_add_think_token
            kwargs["reasoning"] = reasoning
        top_p = getattr(llm_cfg, "top_p", None)
        top_k = getattr(llm_cfg, "top_k", None)
        if top_p is not None:
            kwargs["top_p"] = top_p
        if top_k is not None:
            kwargs["top_k"] = top_k
        if not reasoning and any(p in model_name.lower() for p in _TINY_MODEL_PATTERNS):
            logger.warning(
                "primary_model '%s' is a small model but llm.reasoning=False. "
                "Consider upgrading to qwen3:4b (primary) or gemma4:e2b (triage).",
                model_name,
            )

    return _attach_tracer(init_chat_model(
        model=model_name,
        model_provider=provider,
        **kwargs,
    ), model_name)


def get_triage_model() -> BaseChatModel:
    """Return the fast/cheap triage model configured in profile.yaml.

    For llamacpp: routes to triage_base_url (the dedicated triage server on :8081).
    Falls back to base_url when triage_base_url is unset — fold-onto-primary mode.
    """
    profile = load_profile()
    llm_cfg = profile.llm
    triage_url = getattr(llm_cfg, "triage_base_url", "") or llm_cfg.base_url
    if triage_url != llm_cfg.base_url:
        llm_cfg = llm_cfg.model_copy(update={"base_url": triage_url})
    return _build_model(profile.llm.triage_model, llm_cfg)


def get_primary_model() -> BaseChatModel:
    """Return the strong primary model configured in profile.yaml.

    Used for: detailed scoring, CV tailoring, coaching, question generation.
    Default: Sonnet / GPT-4o / Gemini Pro (depends on provider).
    """
    profile = load_profile()
    return _build_model(profile.llm.primary_model, profile.llm)


def with_schema(llm: BaseChatModel, schema: type[BaseModel]) -> Runnable:
    """Wrap llm.with_structured_output using the per-provider correct method.

    - llamacpp: method='json_schema' (grammar-backed, structurally valid)
    - all other providers: LangChain default (function-calling / tool-use)
    """
    profile = load_profile()
    if profile.llm.provider == "llamacpp":
        return llm.with_structured_output(schema, method="json_schema")
    return llm.with_structured_output(schema)


def get_json_model(schema: type[BaseModel] | None = None) -> BaseChatModel:
    """Return the primary model configured for JSON-constrained output.

    schema: when provided on the llamacpp path, upgrades response_format from
    json_object to json_schema (grammar-enforced). Return type is unchanged
    (a chat model emitting JSON text); complete_json()'s parse-and-retry loop
    is untouched.

    For Ollama providers, passes format='json' to enable constrained token
    sampling — only valid JSON tokens are sampled at the model level.
    For all other providers, delegates to get_primary_model() (JSON is
    enforced via system-prompt instructions instead).
    """
    profile = load_profile()
    llm_cfg = profile.llm
    if llm_cfg.provider == "ollama":
        model_name = llm_cfg.primary_model or _detect_ollama_model(llm_cfg)
        reasoning = getattr(llm_cfg, "reasoning", False)
        kwargs: dict[str, Any] = {
            "temperature": llm_cfg.temperature,
            "max_retries": llm_cfg.max_retries,
            "format": "json",
            "base_url": llm_cfg.base_url or "http://host.containers.internal:11434",
            "request_timeout": 3600,  # 1-hour ceiling; local LLM queue can run 20+ min
            # Ollama defaults to 4096 context but CV/CL prompts consume ~4000 tokens.
            # Force 16 K to leave headroom for thinking tokens + the full generated JSON.
            "num_ctx": PRIMARY_CTX,
        }
        # qwen3 uses the `think` kwarg (ON by default, we disable unless reasoning=True)
        # gemma4/others use the `reasoning` kwarg (OFF by default)
        if model_name.lower().startswith("qwen3"):
            kwargs["think"] = reasoning
        else:
            kwargs["reasoning"] = reasoning
        top_p = getattr(llm_cfg, "top_p", None)
        top_k = getattr(llm_cfg, "top_k", None)
        if top_p is not None:
            kwargs["top_p"] = top_p
        if top_k is not None:
            kwargs["top_k"] = top_k
        return _attach_tracer(init_chat_model(
            model=model_name,
            model_provider="ollama",
            **kwargs,
        ), model_name)
    if llm_cfg.provider == "llamacpp":
        if not llm_cfg.base_url:
            raise ValueError(
                "provider='llamacpp' requires base_url to be set in profile.yaml → llm.base_url "
                "(e.g. 'http://llamacpp:8080/v1')"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        if schema is not None:
            response_format: dict = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        else:
            response_format = {"type": "json_object"}
        return _attach_tracer(ChatOpenAI(
            model=llm_cfg.primary_model,
            base_url=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            timeout=1800,
            model_kwargs={"response_format": response_format},
        ), llm_cfg.primary_model)
    return _build_model(llm_cfg.primary_model, llm_cfg)
