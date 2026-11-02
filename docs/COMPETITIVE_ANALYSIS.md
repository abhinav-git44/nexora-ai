# Competitive Analysis

> Prices are from public pages/secondary sources accessed **Nov 2026**; several sources disagree, so treat as *indicative and verify*.

## 1. Landscape
| Category | Examples | Core strength | Gap NEXORA targets |
|---|---|---|---|
| AI in productivity suites | Notion AI, Microsoft 365 Copilot, Google Gemini for Workspace | Distribution; AI where docs already live | Per-seat AI cost for every user; limited workflow approvals and outcome measurement for SMB tiers |
| General AI assistants (team plans) | ChatGPT Business/Team, Claude Team | Best-in-class models; file Q&A | Not a system of record for tasks/workflows; governance & tenant-level analytics are thin for small teams |
| Enterprise AI search | Glean, Guru | Search across many SaaS tools, enterprise permissions | Priced and sold for enterprise; heavy rollout |
| Automation platforms | Zapier, Make, n8n | Connector breadth, mature triggers | No knowledge layer; AI governance is DIY; execution-priced |
| Agent builders | Lindy, Relevance AI and similar | Fast agent creation | Weaker on knowledge governance, tasks, BI |

## 2. Feature comparison (V1 scope)
| Capability | NEXORA | Notion AI | M365 Copilot | ChatGPT Business | Zapier | n8n | Glean |
|---|---|---|---|---|---|---|---|
| Cited answers from uploaded docs | ✅ hybrid RAG + citation verification | ✅ | ✅ | ✅ (files) | ⚠️ via AI steps | ⚠️ DIY | ✅ |
| Role-based document access in retrieval | ✅ min-role + per-user | ✅ (page perms) | ✅ (M365 perms) | ⚠️ workspace-level | ❌ | ❌ | ✅ |
| Visual workflows with approval steps | ✅ | ⚠️ automations | ⚠️ Power Automate (separate) | ❌ | ✅ | ✅ | ❌ |
| Agents with tool allow-list + human approval | ✅ | ⚠️ | ⚠️ (Copilot Studio) | ⚠️ | ⚠️ | ✅ DIY | ⚠️ |
| NL → safe SQL on uploaded data | ✅ AST-validated, read-only | ❌ | ⚠️ Excel Copilot | ✅ code interpreter | ❌ | ❌ | ❌ |
| Tasks from meeting notes | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| Customer-visible AI cost per outcome | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Self-host / BYOK | ✅ Docker + BYOK keys | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| INR pricing | ✅ | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ |

✅ native · ⚠️ partial/separate product · ❌ not offered (based on public positioning; verify before external use)

## 3. Pricing snapshot (indicative)
| Product | Indicative price | Pricing unit |
|---|---|---|
| Notion Business (AI included) | ~$20/user/mo annual (sources: $18–$24) | Per seat |
| Microsoft 365 Copilot Business | ~$21/user/mo list (promos reported) + base licence | Per seat |
| Zapier Team | $69–$103.50/mo (sources disagree) | Per task tier |
| n8n Cloud Starter | ~$24/mo, 2.5k executions; self-host free | Per execution |
| Glean | Not public (enterprise) | Contract |
| **NEXORA Professional** | **$199/mo for up to 20 members** | Per org (seat band) |

For a 10-person team, per-seat AI at ~$20 ≈ $200/mo *before* automation tooling — the reference point for NEXORA Pro.

## 4. Positioning map
```
               Governed / auditable
                        ▲
          Glean ●       │        ● NEXORA (target)
                        │
  Knowledge-centric ◄───┼───► Action/automation-centric
                        │
   Notion AI ●  ChatGPT ●       ● Zapier   ● n8n
                        ▼
                 Lightweight / DIY
```

## 5. Competitive risks & responses
| Risk | Likelihood | Response |
|---|---|---|
| Suites (Notion/Microsoft/Google) add approval workflows & cost dashboards | High | Win on cross-tool neutrality, SMB pricing per org, India focus, evaluation transparency; integrate *with* suites rather than replace |
| Model vendors ship team agents with connectors | High | Stay provider-neutral (routing, fallback, BYOK); our moat is governance + workflow data model, not the model |
| n8n adds RAG/knowledge templates | Medium | Partner: NEXORA calls n8n; keep ownership of definitions, permissions, outcomes |
| Price compression in AI | High (good for margin) | Pass through via higher limits; keep cost-per-outcome positioning |
