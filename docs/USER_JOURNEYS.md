# User Journeys & Wireframes

## Journey 1 — Ananya: sign-up to first cited answer (activation)
| Stage | Action | Touchpoint | Emotion | Opportunity / metric |
|---|---|---|---|---|
| Discover | Reads a "stop answering the same policy question" article | Marketing site | Curious, sceptical | Landing → signup conversion |
| Sign up | Email + company name; lands in workspace on a 14-day Pro trial | `/register` → `/app` | Relieved: no card | `user_signed_up`, `workspace_created` |
| Orient | Sees the 5-step "Get to first value" checklist | Home | Clear next step | Checklist completion |
| Upload | Drags 3 policy PDFs; sees status flip to *indexed* with summaries | Knowledge | Confidence | `document_uploaded` → `document_indexed` (p50 latency) |
| Ask | "Who approves a 7,000 USD expense?" → cited answer with source chip | Assistant | "Aha" | **Time to first value**, `ai_query_completed` with citations |
| Share | Invites two managers (after verifying email) | Settings → Members | Ownership | `member_invited` |

## Journey 2 — Meeting notes → owned tasks (habit)
Paste notes → *Notes → tasks* → review suggestions (owner matched to members, due date parsed, priority) → create → assignees get
notifications → board view tracks completion. Outcome events: `tasks_extracted_by_ai`, `task_completed`, `outcome_achieved`.

## Journey 3 — Approval-gated workflow (expansion)
Pick "Meeting notes → AI summary → approval → task" recipe → validate (inline node errors) → publish v1 → run → execution waits →
manager approves in *Approvals* → task created → execution log shows per-node inputs/outputs. Failure path: failed node is highlighted,
retry creates attempt #2 linked to the original.

## Journey 4 — Dev asks a data question (cross-sell to Pro)
Upload `sales.csv` → profile shows types, roles, data-quality issues (e.g. inconsistent category casing) → ask "monthly revenue
trend" → validated SQL + line chart → edits SQL → export XLSX → generate report.

## Journey 5 — Admin governance
Nikhil restricts a salary document to *managers+*, verifies a member gets no retrieval hits, reviews the audit log, disconnects an
integration (credentials destroyed), and checks AI spend by model in Analytics.

## Wireframes (low-fidelity, Balsamiq-style)
The implemented screens are in `docs/screenshots/`. These are the lo-fi structures they were built from.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [≡] NEXORA            (org switcher ▾)                 [◐] [🔔3] (avatar) │
├──────────────┬──────────────────────────────────────────────────────────────┤
│ Home         │ Good to see you, Ananya                                      │
│ WORK         │ ┌ Get to first value ─────────────────────── 40% ┐          │
│  Assistant   │ │ ✓ Upload doc  ✓ Ask  ○ Agent  ○ Workflow  ○ Invite │      │
│  Knowledge   │ └──────────────────────────────────────────────────┘        │
│  Agents      │ [Outcomes 30d] [AI interactions] [AI spend] [Time saved*]   │
│  Workflows   │ ┌ Quick actions ───────────┐ ┌ Waiting on you ────────┐     │
│  Data        │ │ Ask │ Add knowledge │ …  │ │ ● approval: …           │     │
│  Tasks       │ └──────────────────────────┘ │ ● task (overdue)        │     │
│ INSIGHTS     │                               └────────────────────────┘     │
│  Analytics   │ Recent conversations ……                                      │
│  Approvals ① │                                                               │
└──────────────┴──────────────────────────────────────────────────────────────┘
          * Estimate badge — never shown as a measured number

ASSISTANT                                   WORKFLOW BUILDER
┌──────────┬──────────────────────────┐     ┌──────────┬────────────────────┬──────────┐
│ + New    │ Title            [⋯]     │     │ Palette  │  (trigger)→(AI)→   │ Node     │
│ conv 1   │  user bubble ──────────▶ │     │ triggers │   (approval)─┬→task│ config   │
│ conv 2   │ ✦ answer… [1][2]         │     │ actions  │              └→…   │ fields   │
│          │   [1] policy · p.2 ▾     │     │ logic    │  [validate errors] │ {{vars}} │
│          │ ┌ Ask anything … ──────┐ │     └──────────┴────────────────────┴──────────┘
│          │ │📎 Attach [Mode▾] ⏎   │ │     tabs: Builder | Executions | Analytics | Trigger
└──────────┴──────────────────────────┘
```
