# AI Evaluation Framework

## What is evaluated
`ai-engine/run_eval.py` executes the **real application code paths** (gateway → retrieval → citation verification → SQL guard →
agent tool selection) inside an isolated, auto-deleted evaluation organisation, against `ai-engine/evals/golden.jsonl`:

| Case type | # | Measures |
|---|---|---|
| rag | 14 | answer correctness (expected facts), citation accuracy (first citation = expected document), groundedness (all citations verified), retrieval hit@1/hit@6/MRR |
| unanswerable | 3 | hallucination rate (answers instead of "not found") |
| injection | 1 | correctness **and** injection resistance (must not repeat the injected claim) |
| extract | 2 | field accuracy, exact-match |
| tasks | 2 | task recall, no false tasks, priority correctness |
| sql | 3 | NL→SQL success (validated, executed, expected shape) |
| tool | 4 | tool-selection accuracy |
Plus latency p50/p95, number of model calls, total cost and cost per request (from the `ai_requests` ledger).

## Latest run (committed: `ai-engine/results/latest.json`)
**Engine: demo-local (no LLM key in this environment) · local-hash-v1 embeddings · 29 cases**

| Metric | Result |
|---|---|
| Answer correctness (RAG) | 0.929 (13/14) |
| Citation accuracy | 0.929 |
| Groundedness | 1.0 |
| Retrieval hit@1 / hit@6 / MRR | 0.929 / 1.0 / 0.964 |
| Hallucination rate (unanswerable) | 0.0 |
| Injection resistance | 1.0 |
| Extraction field accuracy | 1.0 |
| Task-extraction recall | 1.0 |
| NL→SQL success | 1.0 |
| Tool-selection accuracy | 1.0 |
| Latency p50 / p95 | 0 ms / 6 ms (local engine) |
| Cost | $0 (34 metered demo calls) |

**How to read this honestly.** These numbers validate the *pipeline* (retrieval, permissions, guards, citation mapping, metering)
on a small synthetic corpus written by the developer. They do **not** measure generative quality: the demo engine is extractive and
rule-based, and several cases were authored alongside it. The one failure (`rag-01`, "who approves 7,000 USD?") is a genuine gap —
the extractive engine cannot reason that 7,000 > 5,000. Production claims require running the same suite with a real provider and on
customer-specific private sets.

## Process
1. Any change to prompts, routes, model ids, chunking or retrieval → run `backend/.venv/bin/python ai-engine/run_eval.py`.
2. Compare with `latest.json`; a drop > 2 pts on correctness/groundedness or any rise in hallucination blocks the change.
3. CI runs the suite on every push (demo engine — regression gate for pipeline logic). A nightly job with real keys is recommended
   once budgets exist (≈ 40 calls/run).
4. Expand the golden set from production 👎 feedback (anonymised, with customer consent) and per-customer private sets.
5. `--chunking-sweep` compares chunking strategies on retrieval metrics.

## Metric definitions
* **Correctness:** answer contains any expected fact string (normalised, commas removed).
* **Groundedness:** every citation in the answer is verified (cited sentence lexically supported by the cited chunk).
* **Citation accuracy:** the first citation points to the expected document.
* **Hallucination rate:** share of unanswerable questions where the answer does not decline.
* **Tool-selection accuracy:** first tool call equals the expected tool.
* **Cost per request:** Σ `ai_requests.cost_usd` ÷ calls during the run.
