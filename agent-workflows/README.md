# Agent workflows

Source of truth: `backend/app/agents/` (exported snapshot in `templates.json`, regenerate with the snippet in `scripts/export_catalogs.py`).

- **Runtime** (`runtime.py`): single-agent, persisted state machine `queued → running → (awaiting_approval ⇄ running)* → succeeded|failed`.
  State (provider-neutral message list + pending tool calls) is stored on `agent_runs.state` after every step so runs can pause for
  human approval and resume in another worker. Each step is an `agent_run_steps` row (thought, tool_call, approval, final, error).
- **Guardrails**: tool allow-list per agent; minimum role per tool (re-checked at execution with the *current* membership, never
  escalated); sensitive tools (`send_email`, `send_webhook`) always require approval; max model steps; per-run token budget;
  tool retries for transient errors only; tool output wrapped as untrusted data and injection-scored.
- **Why not a multi-agent graph framework?** See PRODUCT_DECISION_LOG D-007: one agent with a narrow toolset was more reliable,
  cheaper and easier to audit for the eight target jobs; the persisted state machine gives the resumability LangGraph would provide.

Templates: Business Research, HR Recruitment, Sales Intelligence, Customer Support, Document Analysis, Data Analytics,
Project Management, Operations.
