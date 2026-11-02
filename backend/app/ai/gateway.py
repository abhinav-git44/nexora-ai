"""AI gateway: the only entry point application code uses to call a model.

Responsibilities: routing by task, provider fallback, timeouts, retries (SDK-level + cross-provider), token budgeting,
response caching for idempotent tasks, PII redaction, output validation, rate limiting, cost + usage metering.
"""
import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.ai.catalog import catalog, model_info, estimate_cost
from app.ai.providers.base import LLMRequest, LLMResponse, ProviderError
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.demo_provider import DemoProvider
from app.ai.safety import redact_pii, validate_output
from app.core.config import get_settings
from app.core import ratelimit
from app.models import AIRequest, AIResponseCache

log = logging.getLogger("nexora.ai")
PROVIDERS = {"anthropic": AnthropicProvider(), "openai": OpenAIProvider(), "demo": DemoProvider()}
CACHEABLE_TASKS = {"summarize", "classify", "extract"}
# Bump whenever prompts, schemas or engine behaviour change so cached responses from the old logic are never served.
CACHE_VERSION = "2026-11-02.3"
TIER_TO_ROUTE = {"fast": "summarize", "balanced": "chat", "frontier": "analysis"}


class AIUnavailable(Exception):
    pass


def provider_status() -> dict:
    s = get_settings()
    return {
        "anthropic": PROVIDERS["anthropic"].available(),
        "openai": PROVIDERS["openai"].available(),
        "demo_mode": not (PROVIDERS["anthropic"].available() or PROVIDERS["openai"].available()) or s.ai_default_provider == "demo",
        "default_provider": s.ai_default_provider,
    }


def resolve_candidates(task_type: str, preference: str | None = None) -> list[tuple[str, str]]:
    s = get_settings()
    routes = catalog()["routes"]
    route_key = TIER_TO_ROUTE.get(preference or "", task_type)
    if preference and preference in catalog()["models"]:
        models = [preference] + [m for m in routes.get(task_type, routes["chat"])["candidates"] if m != preference]
    else:
        models = routes.get(route_key, routes["chat"])["candidates"]
    out = []
    for m in models:
        p = model_info(m)["provider"]
        if s.ai_default_provider in ("anthropic", "openai") and p != s.ai_default_provider and any(
                model_info(x)["provider"] == s.ai_default_provider for x in models):
            continue
        if s.ai_default_provider != "demo" and p in PROVIDERS and PROVIDERS[p].available():
            out.append((p, m))
    out.append(("demo", "demo-local"))  # last-resort fallback keeps product usable; responses flagged demo
    return out


def _cache_key(org_id, task_type, req: LLMRequest) -> str:
    candidates = [m for _, m in resolve_candidates(task_type)]
    payload = json.dumps({"v": CACHE_VERSION, "c": candidates, "o": str(org_id), "t": task_type, "s": req.system, "m": [asdict(m) for m in req.messages],
                          "j": req.json_schema, "md": {k: v for k, v in req.metadata.items() if k != "context"}}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def generate(db: Session, req: LLMRequest, *, org_id=None, user_id=None, feature: str = "chat",
             preference: str | None = None, use_cache: bool | None = None) -> LLMResponse:
    s = get_settings()
    task_type = req.task_type
    route = catalog()["routes"].get(task_type, catalog()["routes"]["chat"])
    req.max_tokens = min(req.max_tokens or route["max_tokens"], route["max_tokens"] * 2)
    req.effort = req.effort or route.get("effort")
    if org_id:
        ratelimit.enforce(f"ai:{org_id}", s.ai_rate_limit_per_minute)

    # PII protection before data leaves our boundary.
    for m in req.messages:
        if m.role == "user":
            m.content, _ = redact_pii(m.content)

    cache_on = (task_type in CACHEABLE_TASKS) if use_cache is None else use_cache
    key = _cache_key(org_id, task_type, req) if cache_on and not req.tools else None
    if key:
        hit = db.get(AIResponseCache, key)
        if hit and hit.expires_at > datetime.now(timezone.utc):
            r = LLMResponse(**{k: v for k, v in hit.response.items() if k in LLMResponse.__dataclass_fields__ and k != "tool_calls"})
            db.add(AIRequest(org_id=org_id, user_id=user_id, feature=feature, task_type=task_type, provider=r.provider, model=r.model,
                             input_tokens=0, output_tokens=0, cost_usd=0, latency_ms=0, status="success", cache_hit=True))
            return r

    errors = []
    candidates = resolve_candidates(task_type, preference)
    for i, (pname, model) in enumerate(candidates):
        provider = PROVIDERS[pname]
        t0 = time.perf_counter()
        try:
            resp = provider.complete(model, req, timeout_s=s.ai_request_timeout_s)
        except ProviderError as e:
            latency = int((time.perf_counter() - t0) * 1000)
            errors.append(f"{pname}/{model}: {e}")
            db.add(AIRequest(org_id=org_id, user_id=user_id, feature=feature, task_type=task_type, provider=pname, model=model,
                             latency_ms=latency, status="error", error=str(e)[:1000], fallback_used=i > 0))
            log.warning("AI provider failure (%s/%s): %s", pname, model, e)
            if not e.retryable:
                break
            continue
        latency = int((time.perf_counter() - t0) * 1000)
        resp.text = validate_output(resp.text)
        cost = estimate_cost(resp.model if resp.model in catalog()["models"] else model, resp.input_tokens, resp.output_tokens, resp.cached_tokens)
        db.add(AIRequest(org_id=org_id, user_id=user_id, feature=feature, task_type=task_type, provider=resp.provider, model=resp.model,
                         input_tokens=resp.input_tokens, output_tokens=resp.output_tokens, cached_tokens=resp.cached_tokens,
                         cost_usd=cost, latency_ms=latency, status="refusal" if resp.refusal else "success", fallback_used=i > 0))
        resp_meta = {"latency_ms": latency, "cost_usd": cost, "fallback_used": i > 0, "errors": errors}
        resp.__dict__["meta"] = resp_meta
        if key and not resp.refusal:
            d = {k: v for k, v in asdict(resp).items() if k not in ("tool_calls",)}
            db.merge(AIResponseCache(key=key, org_id=org_id, response=d, expires_at=datetime.now(timezone.utc) + timedelta(hours=24)))
            db.flush()  # make the entry visible to identical requests later in the same transaction
        return resp
    raise AIUnavailable("All AI providers failed: " + "; ".join(errors))
