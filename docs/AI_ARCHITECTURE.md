# AI Architecture

## 1. Gateway (single entry point) — `app/ai/gateway.py`
Every model call goes through `generate(db, LLMRequest, org_id, user_id, feature, preference)`:
1. **Route** by `task_type` (classify, summarize, extract, chat, analysis, agent, sql) to an ordered candidate list from the catalogue.
2. **Filter** to providers with credentials (Anthropic, OpenAI); append the **demo engine** as a last resort so the product degrades
   instead of failing (responses are flagged `demo` and labelled in the UI).
3. **Rate-limit** per organisation (Redis), **redact PII** (cards, Aadhaar, PAN, API keys) from user content before it leaves.
4. **Cache** idempotent tasks (summaries, classification, extraction) for 24h keyed by org + request hash (duplicate-request handling).
5. **Call** the provider with timeout + SDK retries; on retryable failure (429/5xx/connection/auth/model-not-found) **fall back** to
   the next candidate; non-retryable (400) stops.
6. **Validate output** (strip leaked secrets), **meter** every attempt in `ai_requests` (tokens, cached tokens, cost, latency,
   status, fallback, cache hit) — the source for cost dashboards and unit economics.

## 2. Provider adapters (common interface `LLMProvider.complete`)
| | Anthropic (`anthropic` SDK 2.x, Messages API) | OpenAI (`openai` SDK 3.x, Responses API) |
|---|---|---|
| System prompt | `system=[{text, cache_control: ephemeral}]` → **prompt caching** of stable prefixes | `instructions` + `prompt_cache_key` per task |
| Reasoning depth | `output_config.effort` (low/medium/high); adaptive thinking is the model default — no `thinking` param, no sampling params (rejected on current models) | `reasoning.effort` for reasoning models; `temperature` only for non-reasoning models |
| Tools | `tools[{name, description, input_schema, strict: true}]`, `tool_choice` auto (forced choice is rejected on current models) | `tools[{type: function, …, strict: true}]` |
| Structured output | `output_config.format = {type: json_schema}` | `text.format = {type: json_schema, strict: true}` |
| Multi-turn tools | Assistant content replayed **unchanged** (incl. thinking blocks); all tool results in one user message | `function_call` + `function_call_output` items |
| Safety | `stop_reason == "refusal"` handled; server-side refusal **fallbacks** (`fallbacks: "default"`, beta header) on Opus/Sonnet 5.5, toggle `ANTHROPIC_REFUSAL_FALLBACK` | standard errors |
| Errors | typed exception chain → retryable vs non-retryable | same |

Model identifiers and prices are **data** (`ai/catalog.py`, overridable with `MODEL_CATALOG_PATH`), not code, so retiring a model is a
config change. Anthropic entries use the current family (Opus 5.5, Sonnet 5.5, Haiku 5.5); OpenAI entries are marked `verified: false`
until checked against OpenAI's model page.

## 3. Routing policy (cost-aware, not "most expensive wins")
| Task | 1st choice | Fallbacks | Effort | Rationale |
|---|---|---|---|---|
| classify | claude-haiku-5-5 | gpt-5-mini | low | Labels saturate on fast models |
| summarize | claude-haiku-5-5 | gpt-5-mini | low | Latency-sensitive, low risk |
| extract | claude-sonnet-5-5 | gpt-5-mini | medium | Schema reliability |
| chat / RAG | claude-sonnet-5-5 | gpt-5, haiku | medium | Balanced quality/latency |
| analysis / reports | claude-opus-5-5 | gpt-5, sonnet | high | Hard reasoning, low volume |
| agent | claude-sonnet-5-5 | gpt-5, opus | medium | Tool use over several steps; bounded per-run cost |
| sql | claude-sonnet-5-5 | gpt-5-mini | medium | Short structured output, validated anyway |
Users can choose *fast / balanced / frontier* per conversation; agents choose a route in config. The eval framework (§6) is how a
route change is approved: quality ≥ baseline and cost/latency within budget.

## 4. Cost optimisation
Prompt caching (stable system prompts first, volatile content last) · response caching for idempotent tasks · token budgeting
(history truncated to 6k tokens; retrieved context ≤ 6k; per-route `max_tokens`) · model selection by task · per-org rate limits and
plan quotas · agent step and token budgets · cost per outcome visible to customers and admins.

## 5. Safety controls
| Threat | Control | Where |
|---|---|---|
| Prompt injection in documents/tool output | Detection (pattern scoring), neutralisation, untrusted-data preamble, `<document>`/`<tool_output>` wrapping, rerank penalty | `ai/safety.py`, `rag/retrieval.py`, `agents/runtime.py` |
| Unauthorised tool use | Per-agent allow-list, per-tool minimum role re-checked at execution (never escalates), sensitive tools always require approval | `agents/tools.py`, `runtime.py` |
| Data exfiltration via URLs | SSRF guard (public IPs only, https in prod), no redirects | `core/netguard.py` |
| Destructive SQL | AST allow-list, read-only transaction, timeout, row cap, separate role | `data/sqlguard.py` |
| PII leakage to providers/logs | Redaction before send; secrets stripped from output | `ai/safety.py` |
| Runaway cost | Rate limits, quotas, budgets, metering | `gateway.py`, `plans.py` |
| Hallucination | Grounded prompting, "not found" instruction, citation verification, eval hallucination rate | `chat.py`, `retrieval.py` |

## 6. Evaluation
See AI_EVALUATION_FRAMEWORK.md — golden set across RAG, unanswerable, injection, extraction, task extraction, NL→SQL and tool
selection; run on every prompt/model/retrieval change (CI job).

## 7. Agents
Single-agent tool loop with a persisted state machine (agent-workflows/README.md). Chosen over multi-agent graphs because each of the
8 target jobs needs ≤ 3 tools and a human checkpoint, which a single loop handles more reliably and cheaply.
