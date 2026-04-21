"""
Shared LLM client infra for evaluators.

Provides:
* ``LLMClient.chat_json``  — deterministic JSON call with retries/backoff.
* Per-prompt caching keyed on (model, prompt, params) — avoids re-paying for
  identical judge calls within a run (and across reruns if the cache is persisted).
* Cost tracking via per-1M-token USD rates (editable in ``MODEL_PRICES``).
* Concurrency via ``threading.Semaphore`` — bounds in-flight judge calls so we
  don't hit provider rate limits.
* Errors returned as ``LLMError`` instead of raising, so evaluators can map
  them to ``EvalError`` on the MetricScores.

Providers: the module uses the ``openai`` Python SDK as transport but is
provider-agnostic. Any OpenAI-compatible endpoint (OpenRouter, Groq,
Together, local vLLM / Ollama) works by passing ``base_url`` + ``api_key``
to ``LLMClient``. OpenRouter is treated as a first-class path because it
unifies access to DeepSeek V3, Qwen 3, Kimi K2, QwQ, and GPT models under
one API — useful when you want to swap judges without touching code.

    # GPT-4o via OpenAI:
    client = LLMClient(default_model="gpt-4o")

    # DeepSeek V3 via OpenRouter — same interface, different base URL:
    client = LLMClient(
        default_model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

The module auto-detects OpenRouter if ``OPENROUTER_API_KEY`` is set in the
environment and ``OPENAI_API_KEY`` is not — see ``get_default_client()``.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# OpenRouter's public endpoint. Overridable via OPENROUTER_BASE_URL if the
# user has a self-hosted OpenRouter mirror or a corp proxy.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# USD per 1M tokens, (input, output). Used for budget tracking and run
# reporting, not billing. OpenRouter pricing is updated frequently — these
# are defaults for cost visibility; a missing entry is treated as $0 rather
# than crashing the run.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # Source: OpenRouter live catalog as of 2026-04-21. Refresh with:
    #   curl https://openrouter.ai/api/v1/models | jq
    #
    # ── OpenAI (direct + OpenRouter mirror) ────────────────────────────
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.1": (1.25, 10.00),
    "openai/gpt-5.4": (2.50, 15.00),
    "openai/gpt-5.4-mini": (0.75, 4.50),
    "openai/gpt-5.4-nano": (0.20, 1.25),
    "openai/gpt-5.4-pro": (30.00, 180.00),
    "openai/gpt-5.1": (1.25, 10.00),
    "openai/gpt-5.1-chat": (1.25, 10.00),
    "openai/gpt-5-pro": (15.00, 120.00),
    # Legacy OpenAI models kept for historical runs:
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "o3-deep-research": (10.00, 40.00),
    "o4-mini-deep-research": (2.00, 8.00),
    # ── Anthropic Claude ───────────────────────────────────────────────
    "anthropic/claude-opus-4.7": (5.00, 25.00),           # 1M context
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "anthropic/claude-opus-4.5": (5.00, 25.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),         # 1M context
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    # ── DeepSeek (still the cheapest strong judge) ─────────────────────
    "deepseek/deepseek-v3.2": (0.25, 0.38),               # flagship, recommended
    "deepseek/deepseek-v3.2-exp": (0.27, 0.41),
    "deepseek/deepseek-v3.2-speciale": (0.40, 1.20),
    "deepseek/deepseek-v3.1-terminus": (0.21, 0.79),
    "deepseek/deepseek-chat-v3.1": (0.15, 0.75),
    "deepseek/deepseek-r1-0528": (0.50, 2.15),            # reasoning specialist
    # ── Qwen 3.6 / 3.5 (fantastic price/perf + 1M context options) ─────
    "qwen/qwen3.6-plus": (0.33, 1.95),                    # 1M context
    "qwen/qwen3.5-397b-a17b": (0.39, 2.34),               # MoE flagship
    "qwen/qwen3.5-122b-a10b": (0.26, 2.08),
    "qwen/qwen3.5-35b-a3b": (0.16, 1.30),
    "qwen/qwen3.5-27b": (0.20, 1.56),
    "qwen/qwen3.5-9b": (0.10, 0.15),
    "qwen/qwen3.5-plus-02-15": (0.26, 1.56),              # 1M context
    "qwen/qwen3.5-flash-02-23": (0.07, 0.26),             # 1M context, cheapest
    "qwen/qwen3-max-thinking": (0.78, 3.90),              # reasoning
    "qwen/qwen3-max": (0.78, 3.90),
    "qwen/qwen3-235b-a22b-thinking-2507": (0.13, 0.60),   # reasoning, cheap
    # ── Moonshot Kimi K2 family (262k context, long-answer specialist) ─
    "moonshotai/kimi-k2.6": (0.60, 2.80),                 # current flagship
    "moonshotai/kimi-k2.5": (0.44, 2.00),
    "moonshotai/kimi-k2-thinking": (0.60, 2.50),          # reasoning variant
    "moonshotai/kimi-k2-0905": (0.40, 2.00),
    "moonshotai/kimi-k2": (0.57, 2.30),
    # ── Z.AI GLM (new strong contender) ────────────────────────────────
    "z-ai/glm-5.1": (1.05, 3.50),
    "z-ai/glm-5": (0.65, 2.08),
    "z-ai/glm-5-turbo": (1.20, 4.00),
    "z-ai/glm-4.7": (0.38, 1.74),
    "z-ai/glm-4.6": (0.39, 1.90),
    # ── xAI Grok (2M context — useful for very long evals) ─────────────
    "x-ai/grok-4.20": (2.00, 6.00),                       # 2M context
    "x-ai/grok-4.1-fast": (0.20, 0.50),
    # ── Google Gemini ──────────────────────────────────────────────────
    "google/gemini-2.5-flash-image": (0.30, 2.50),
}


def is_openrouter_model(model: str) -> bool:
    """Heuristic: OpenRouter model IDs always contain a provider slug prefix
    like ``deepseek/``, ``qwen/``, ``moonshotai/``. Bare names like ``gpt-4o``
    hit OpenAI directly."""
    return "/" in model


@dataclass
class LLMError:
    type: str           # "rate_limit" | "timeout" | "parse_error" | "auth" | "server" | "other"
    message: str
    retryable: bool


@dataclass
class LLMResult:
    content: str | None
    parsed: Any = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: LLMError | None = None
    cache_hit: bool = False
    metadata: dict = field(default_factory=dict)


def prompt_hash(model: str, system: str, user: str, params: dict) -> str:
    """Stable hash for caching and for the run manifest."""
    payload = json.dumps(
        {"model": model, "system": system, "user": user, "params": params},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = MODEL_PRICES.get(model)
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0


class _TTLCache:
    """Thread-safe in-memory cache with optional TTL. Small and good enough."""

    def __init__(self, ttl_seconds: float = 60 * 60):
        self._data: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self._ttl:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)


class LLMClient:
    """Thin wrapper over any OpenAI-compatible endpoint with retries, cost
    accounting, and caching.

    Not a full provider abstraction — deliberately narrow so evaluators have
    one consistent entry point.

    Args:
        api_key: Explicit key. If omitted, falls back to OPENROUTER_API_KEY
            (when ``base_url`` points at OpenRouter or ``default_model`` is
            an OpenRouter-style ``provider/model`` slug), else OPENAI_API_KEY.
        default_model: Model ID to use when a call doesn't specify one.
            ``provider/model`` style (e.g. ``deepseek/deepseek-chat``)
            auto-routes through OpenRouter.
        base_url: Override the endpoint. ``None`` means OpenAI's default
            unless ``default_model`` is OpenRouter-style, in which case we
            auto-switch to ``OPENROUTER_BASE_URL``.
        http_referer, x_title: OpenRouter-recommended request headers used
            for their attribution / leaderboard. Safe to leave as defaults.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        base_url: str | None = None,
        max_retries: int = 4,
        timeout_seconds: float = 60.0,
        max_concurrency: int = 8,
        cache_ttl_seconds: float = 60 * 60,
        http_referer: str = "https://github.com/aswithabukka/Evaluation-First-Testing-Harness-for-RAG-and-Agents",
        x_title: str = "rag-eval-harness",
    ):
        # Auto-detect OpenRouter when the caller gave us a slug-style model
        # (deepseek/deepseek-chat) OR explicitly pointed at the OpenRouter
        # base URL. Both cases flip us onto OpenRouter.
        using_openrouter = (
            (base_url is not None and "openrouter" in base_url)
            or is_openrouter_model(default_model)
        )
        if base_url is None and using_openrouter:
            base_url = os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL)

        # Key precedence: explicit arg → provider-appropriate env var →
        # OPENAI_API_KEY fallback. The fallback ordering means an engineer
        # who exports both keys doesn't need to choose.
        if api_key is None:
            if using_openrouter:
                api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            else:
                api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")

        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
        self._max_retries = max_retries
        self._timeout = timeout_seconds
        self._sem = threading.Semaphore(max_concurrency)
        self._cache = _TTLCache(cache_ttl_seconds)
        self._client = None
        self._total_cost = 0.0
        self._total_cost_lock = threading.Lock()
        self._default_headers: dict[str, str] = {}
        if using_openrouter:
            # OpenRouter's recommended attribution headers. Optional, but
            # they make your requests visible on the OpenRouter leaderboard
            # and are trivially cheap to send.
            self._default_headers = {"HTTP-Referer": http_referer, "X-Title": x_title}

    @property
    def using_openrouter(self) -> bool:
        return self._base_url is not None and "openrouter" in self._base_url

    # ------------------------------------------------------------------ public

    @property
    def total_cost_usd(self) -> float:
        with self._total_cost_lock:
            return self._total_cost

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.0,
        seed: int | None = 0,
        max_tokens: int | None = 1024,
        use_cache: bool = True,
    ) -> LLMResult:
        """Run a deterministic JSON chat call with retries and caching.

        Returns ``LLMResult`` — never raises on provider errors.
        """
        model = model or self._default_model
        params = {"temperature": temperature, "seed": seed, "max_tokens": max_tokens}
        key = prompt_hash(model, system, user, params)

        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                cached.cache_hit = True
                return cached

        result = self._call_with_retries(model, system, user, params)
        result.metadata["prompt_hash"] = key

        if use_cache and result.error is None:
            self._cache.set(key, result)

        return result

    # ------------------------------------------------------------------ retries

    def _call_with_retries(
        self, model: str, system: str, user: str, params: dict
    ) -> LLMResult:
        last_error: LLMError | None = None
        start = time.time()

        for attempt in range(self._max_retries + 1):
            with self._sem:
                r = self._call_openai(model, system, user, params)

            if r.error is None:
                r.latency_ms = (time.time() - start) * 1000.0
                return r

            last_error = r.error
            if not r.error.retryable or attempt == self._max_retries:
                break

            # Exponential backoff with jitter — standard rate-limit handling.
            sleep = min(2.0 ** attempt + random.uniform(0, 0.5), 30.0)
            time.sleep(sleep)

        return LLMResult(
            content=None,
            error=last_error,
            latency_ms=(time.time() - start) * 1000.0,
        )

    # ------------------------------------------------------------------ provider

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import openai  # lazy — evaluators without LLM calls don't need it.
        except ImportError:
            self._client = False
            return
        kwargs: dict[str, Any] = {
            "api_key": self._api_key,
            "timeout": self._timeout,
        }
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._default_headers:
            kwargs["default_headers"] = self._default_headers
        self._client = openai.OpenAI(**kwargs)

    def _call_openai(self, model: str, system: str, user: str, params: dict) -> LLMResult:
        self._ensure_client()
        if not self._client:
            return LLMResult(
                content=None,
                error=LLMError(type="other", message="openai sdk not installed", retryable=False),
            )

        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=params["temperature"],
                seed=params["seed"],
                max_tokens=params["max_tokens"],
            )
        except Exception as e:
            return LLMResult(content=None, error=self._classify(e))

        content = resp.choices[0].message.content if resp.choices else None
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0
        cost = estimate_cost(model, in_tok, out_tok)

        with self._total_cost_lock:
            self._total_cost += cost

        parsed = None
        if content:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                return LLMResult(
                    content=content,
                    error=LLMError(type="parse_error", message=str(e), retryable=False),
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                )

        return LLMResult(
            content=content,
            parsed=parsed,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )

    @staticmethod
    def _classify(exc: Exception) -> LLMError:
        name = type(exc).__name__.lower()
        msg = str(exc)
        if "ratelimit" in name or "429" in msg:
            return LLMError(type="rate_limit", message=msg, retryable=True)
        if "timeout" in name or "timed out" in msg.lower():
            return LLMError(type="timeout", message=msg, retryable=True)
        if "auth" in name or "401" in msg or "403" in msg:
            return LLMError(type="auth", message=msg, retryable=False)
        if "server" in name or "500" in msg or "502" in msg or "503" in msg:
            return LLMError(type="server", message=msg, retryable=True)
        return LLMError(type="other", message=msg, retryable=False)


# Shared default instance — evaluators that don't need a custom config reuse this.
_DEFAULT_CLIENT: LLMClient | None = None
_DEFAULT_CLIENT_LOCK = threading.Lock()


def get_default_client(api_key: str | None = None) -> LLMClient:
    """Return a process-wide singleton LLMClient.

    Provider selection (first match wins):

    1. ``LLM_PROVIDER=openrouter`` env var — force OpenRouter and pick the
       default model from ``LLM_DEFAULT_MODEL`` (fallback ``deepseek/deepseek-chat``).
    2. ``OPENROUTER_API_KEY`` set AND ``OPENAI_API_KEY`` unset — auto-route
       through OpenRouter.
    3. Otherwise — OpenAI, default model ``gpt-4o``.

    Callers that need different settings (e.g. a Kimi K2 judge for one
    evaluator + DeepSeek for another) should instantiate ``LLMClient``
    directly and pass it in.
    """
    global _DEFAULT_CLIENT
    with _DEFAULT_CLIENT_LOCK:
        if _DEFAULT_CLIENT is not None:
            return _DEFAULT_CLIENT

        provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        env_model = os.getenv("LLM_DEFAULT_MODEL", "").strip()
        has_openrouter_key = bool(os.getenv("OPENROUTER_API_KEY"))
        has_openai_key = bool(os.getenv("OPENAI_API_KEY"))

        use_openrouter = (
            provider == "openrouter"
            or (has_openrouter_key and not has_openai_key)
        )

        if use_openrouter:
            # Default to Qwen 3.6 Plus — best price/perf judge as of April 2026:
            # 1M context, $0.33/$1.95 per 1M tokens, strong JSON compliance.
            # Override via LLM_DEFAULT_MODEL for alternatives like
            # moonshotai/kimi-k2.6, deepseek/deepseek-v3.2, or qwen/qwen3-max-thinking.
            default_model = env_model or "qwen/qwen3.6-plus"
            _DEFAULT_CLIENT = LLMClient(
                api_key=api_key,
                default_model=default_model,
                base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            )
        else:
            default_model = env_model or "gpt-4o"
            _DEFAULT_CLIENT = LLMClient(
                api_key=api_key,
                default_model=default_model,
            )
        return _DEFAULT_CLIENT


def reset_default_client() -> None:
    """Testing hook — clear the singleton so a test can reconfigure the
    environment and get a fresh client."""
    global _DEFAULT_CLIENT
    with _DEFAULT_CLIENT_LOCK:
        _DEFAULT_CLIENT = None
