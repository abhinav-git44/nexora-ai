"""Model catalogue and routing table.

Model IDs and prices are data, not code: override with MODEL_CATALOG_PATH (JSON with the same shape) when providers
release or retire models. Anthropic prices verified against Anthropic docs (cached 2026-10-06). OpenAI entries are
configuration defaults that MUST be verified against https://platform.openai.com/docs/models before production use.
"""
import json
from functools import lru_cache
from app.core.config import get_settings

DEFAULT_CATALOG = {
    "models": {
        # price_in / price_out = USD per 1M tokens; cache_read = USD per 1M cached input tokens
        "claude-opus-5-5":   {"provider": "anthropic", "tier": "frontier", "price_in": 4.00, "price_out": 20.00, "cache_read": 0.20,
                               "context": 1_000_000, "tools": True, "structured": True, "verified": True},
        "claude-sonnet-5-5": {"provider": "anthropic", "tier": "balanced", "price_in": 2.00, "price_out": 10.00, "cache_read": 0.20,
                               "context": 1_000_000, "tools": True, "structured": True, "verified": True},
        "claude-haiku-5-5":  {"provider": "anthropic", "tier": "fast", "price_in": 0.10, "price_out": 0.50, "cache_read": 0.01,
                               "context": 1_000_000, "tools": True, "structured": True, "verified": True},
        "gpt-5":             {"provider": "openai", "tier": "frontier", "price_in": 1.25, "price_out": 10.00, "cache_read": 0.125,
                               "context": 400_000, "tools": True, "structured": True, "verified": False},
        "gpt-5-mini":        {"provider": "openai", "tier": "fast", "price_in": 0.25, "price_out": 2.00, "cache_read": 0.025,
                               "context": 400_000, "tools": True, "structured": True, "verified": False},
        "demo-local":        {"provider": "demo", "tier": "demo", "price_in": 0.0, "price_out": 0.0, "cache_read": 0.0,
                               "context": 200_000, "tools": True, "structured": True, "verified": True},
    },
    # Each route lists candidates in preference order; the gateway skips providers without credentials and
    # falls back down the list on retryable failure. "effort" applies to providers that support it.
    "routes": {
        "classify":     {"candidates": ["claude-haiku-5-5", "gpt-5-mini"], "max_tokens": 512, "effort": "low",
                         "why": "Short, low-stakes labels: cheapest fast model is sufficient."},
        "summarize":    {"candidates": ["claude-haiku-5-5", "gpt-5-mini"], "max_tokens": 2048, "effort": "low",
                         "why": "Short summaries are latency-sensitive and quality saturates on fast models."},
        "extract":      {"candidates": ["claude-sonnet-5-5", "gpt-5-mini"], "max_tokens": 4096, "effort": "medium",
                         "why": "Schema-constrained extraction needs reliable structured output."},
        "chat":         {"candidates": ["claude-sonnet-5-5", "gpt-5", "claude-haiku-5-5"], "max_tokens": 4096, "effort": "medium",
                         "why": "Balanced quality/latency for interactive Q&A and RAG answers."},
        "analysis":     {"candidates": ["claude-opus-5-5", "gpt-5", "claude-sonnet-5-5"], "max_tokens": 8192, "effort": "high",
                         "why": "Reports and decision support benefit from the strongest reasoning model."},
        "agent":        {"candidates": ["claude-sonnet-5-5", "gpt-5", "claude-opus-5-5"], "max_tokens": 4096, "effort": "medium",
                         "why": "Tool calling across multiple steps; balanced tier keeps per-run cost bounded."},
        "sql":          {"candidates": ["claude-sonnet-5-5", "gpt-5-mini"], "max_tokens": 1024, "effort": "medium",
                         "why": "NL-to-SQL is structured and short; output is validated before execution anyway."},
    },
}

ROUTES_USER_SELECTABLE = ["auto", "fast", "balanced", "frontier"]


@lru_cache
def catalog() -> dict:
    path = get_settings().model_catalog_path
    if path:
        with open(path) as f:
            override = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_CATALOG))
        merged["models"].update(override.get("models", {}))
        merged["routes"].update(override.get("routes", {}))
        return merged
    return DEFAULT_CATALOG


def model_info(model: str) -> dict:
    return catalog()["models"].get(model, {"provider": "unknown", "price_in": 0, "price_out": 0, "cache_read": 0})


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    m = model_info(model)
    uncached = max(input_tokens - cached_tokens, 0)
    return round((uncached * m["price_in"] + cached_tokens * m.get("cache_read", 0) + output_tokens * m["price_out"]) / 1_000_000, 6)
