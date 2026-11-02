# Product Decision Log

| ID | Date | Decision | Options considered | Rationale | Consequence / revisit when |
|---|---|---|---|---|---|
| D-001 | M0 | Target ops-heavy teams of 10–200 people, India first | Enterprise; horizontal consumer; US-first | Underserved by enterprise AI search; price-sensitive to per-seat AI; founder market access | Revisit after design-partner interviews |
| D-002 | M0 | Modular monolith + separate worker | Microservices; serverless functions | One deploy, ACID across modules, small team velocity | Extract RAG/workflows if independent scaling is needed |
| D-003 | M0 | Per-org seat-band pricing with hard limits, no overage | Per-seat; pure usage | Team price drives expansion usage; predictable bills for SMBs | Financial model shows Pro margin risk → D-012 |
| D-004 | M0 | 14-day Professional reverse trial → Free | Free-only; card-required trial | Users experience governance/data features before deciding | Measure trial→paid; experiment E4 |
| D-005 | S2 | Provider-neutral AI gateway with routing and fallback | Single provider SDK calls in features | Resilience, cost control, no lock-in, one metering point | New providers = one adapter |
| D-006 | S2 | Labelled local demo engine when no keys | Hard dependency on API keys; mocked UI | Every flow testable offline/CI; honest labelling | Never shown as AI quality evidence |
| D-007 | S3 | Own persisted single-agent state machine instead of LangGraph/multi-agent | LangGraph; CrewAI-style multi-agent | Approvals must pause for hours across processes; full audit; ≤3 tools per job | Adopt a graph framework if branching agent plans become necessary |
| D-008 | S2 | Hybrid retrieval (pgvector + Postgres FTS, RRF) in the main DB | Dedicated vector DB (Pinecone/Qdrant) | Permission filters in the same SQL as the search; one fewer system | Revisit beyond ~10M chunks |
| D-009 | S2 | Dimension-less vector + per-model HNSW expression indexes | Fixed-dim column per model; separate tables | Painless embedding migrations | Query must cast to use index |
| D-010 | S5 | NL→SQL guarded by AST allow-list + read-only role, datasets as tables | Let LLM query pandas; sandboxed code execution | Familiar SQL for analysts; strong, testable guard; works with BI | Multi-table joins need allow-listed relationships |
| D-011 | S4 | NEXORA owns workflow definitions; n8n as a node, not the engine | Embed n8n UI; build on Temporal | Permissions, approvals, outcomes and billing live with us; n8n covers connector breadth | Revisit engine if long-running workflows dominate |
| D-012 | S6 | Recommend Pro cap 5,000 messages + credit packs; Starter organic-only acquisition | Raise prices; keep 10k cap | Sensitivity analysis: Pro margin 11% at full use; Starter LTV/CAC 1.5× | Validate with experiments before applying to existing customers |
| D-013 | S6 | North Star = weekly AI-assisted outcomes (completed actions), not AI calls | Messages sent; WAU | Aligns value, retention and pricing; resists vanity growth | Add usefulness signal for chat answers |
| D-014 | S6 | Postgres job queue instead of Redis/Celery | Celery + Redis; cloud queues | Transactional enqueue with business writes; fewer moving parts | Move at >50 jobs/s |
| D-015 | S6 | Time saved shown only as labelled estimate with published assumptions | Hide; present as fact | Leadership wants ROI; honesty prevents credibility loss | Replace with measured time-and-motion data |
