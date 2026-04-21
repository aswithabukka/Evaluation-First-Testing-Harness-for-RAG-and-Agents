"""Unit tests for OpenRouter provider routing in the shared LLMClient.

We don't make real HTTP calls — the OpenAI SDK isn't even guaranteed to be
installed in the test env. Instead we verify:
  * OpenRouter detection heuristics (slug-style model IDs, explicit base_url)
  * Correct api_key selection precedence across env vars
  * MODEL_PRICES covers the models we recommend in the README
  * get_default_client() honours LLM_PROVIDER / LLM_DEFAULT_MODEL
"""
from __future__ import annotations

import os

import pytest

from runner.evaluators._llm import (
    LLMClient,
    MODEL_PRICES,
    OPENROUTER_BASE_URL,
    estimate_cost,
    get_default_client,
    is_openrouter_model,
    reset_default_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts with a clean LLM env + a fresh default client."""
    for k in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "LLM_PROVIDER",
        "LLM_DEFAULT_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)
    reset_default_client()
    yield
    reset_default_client()


# ---------------------------------------------------------------- heuristics


def test_slug_models_detected_as_openrouter():
    assert is_openrouter_model("deepseek/deepseek-chat")
    assert is_openrouter_model("qwen/qwen-3-72b-instruct")
    assert is_openrouter_model("moonshotai/kimi-k2-instruct")
    assert is_openrouter_model("openai/gpt-4o")


def test_bare_models_not_openrouter():
    assert not is_openrouter_model("gpt-4o")
    assert not is_openrouter_model("gpt-4o-mini")
    assert not is_openrouter_model("claude-3-5-sonnet-20241022")


# ---------------------------------------------------------------- client routing


def test_openrouter_auto_detected_from_slug_model():
    c = LLMClient(api_key="fake", default_model="moonshotai/kimi-k2.6")
    assert c.using_openrouter is True
    assert c._base_url == OPENROUTER_BASE_URL
    # Headers set — OpenRouter attribution.
    assert "HTTP-Referer" in c._default_headers
    assert c._default_headers["X-Title"] == "rag-eval-harness"


def test_explicit_base_url_forces_openrouter_headers():
    c = LLMClient(
        api_key="fake",
        default_model="gpt-4o",
        base_url="https://openrouter.ai/api/v1",
    )
    assert c.using_openrouter is True
    assert c._default_headers


def test_openai_bare_model_does_not_enable_openrouter():
    c = LLMClient(api_key="fake", default_model="gpt-4o")
    assert c.using_openrouter is False
    assert c._base_url is None
    assert c._default_headers == {}


# ---------------------------------------------------------------- api-key precedence


def test_openrouter_key_wins_when_slug_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-123")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key-456")
    c = LLMClient(default_model="moonshotai/kimi-k2.6")
    assert c._api_key == "or-key-123"


def test_openai_key_wins_for_bare_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-123")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key-456")
    c = LLMClient(default_model="gpt-4o")
    assert c._api_key == "oa-key-456"


def test_falls_back_to_other_provider_key_when_primary_missing(monkeypatch):
    """Slug model + no OPENROUTER_API_KEY should still try to use
    OPENAI_API_KEY — lets users experiment without rotating keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "oa-only")
    c = LLMClient(default_model="moonshotai/kimi-k2.6")
    assert c._api_key == "oa-only"
    assert c.using_openrouter is True


# ---------------------------------------------------------------- cost table


def test_recommended_openrouter_models_have_prices():
    """Models documented in the README must have a MODEL_PRICES entry —
    otherwise budget tracking silently reports $0 and lies on the dashboard."""
    required = [
        # Current recommended open-source judges (April 2026):
        "qwen/qwen3.6-plus",
        "moonshotai/kimi-k2.6",
        "deepseek/deepseek-v3.2",
        "qwen/qwen3-max-thinking",
        "qwen/qwen3.5-397b-a17b",
        "moonshotai/kimi-k2-thinking",
        "z-ai/glm-5",
        # Calibration baselines:
        "anthropic/claude-opus-4.7",
        "anthropic/claude-sonnet-4.6",
        "gpt-5.4",
        "gpt-5.4-mini",
    ]
    missing = [m for m in required if m not in MODEL_PRICES]
    assert missing == [], f"MODEL_PRICES missing entries: {missing}"


def test_oss_cheaper_than_frontier_proprietary():
    """Sanity: OSS judges should be materially cheaper than Claude Opus or
    GPT-5.4. If this inverts, someone mis-edited the price table."""
    ds_in, ds_out = MODEL_PRICES["deepseek/deepseek-v3.2"]
    opus_in, opus_out = MODEL_PRICES["anthropic/claude-opus-4.7"]
    assert ds_in < opus_in
    assert ds_out < opus_out


def test_cost_estimate_matches_table():
    # DeepSeek V3.2 at 1M input tokens = $0.25 exactly.
    cost = estimate_cost("deepseek/deepseek-v3.2", input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(0.25)


def test_cost_unknown_model_is_zero_not_crash():
    """Unknown model IDs should be treated as zero-cost rather than raising —
    evaluators must not die because a pricing table is stale."""
    assert estimate_cost("never-heard-of-this", 100, 100) == 0.0


# ---------------------------------------------------------------- default client


def test_default_client_uses_openrouter_when_only_that_key_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    client = get_default_client()
    assert client.using_openrouter is True
    # Default should be the current recommended primary judge.
    assert client._default_model == "qwen/qwen3.6-plus"


def test_default_client_respects_llm_provider_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "moonshotai/kimi-k2.6")
    client = get_default_client()
    assert client.using_openrouter is True
    assert client._default_model == "moonshotai/kimi-k2.6"


def test_default_client_uses_openai_when_both_keys_and_no_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    client = get_default_client()
    assert client.using_openrouter is False
    assert client._default_model == "gpt-4o"
