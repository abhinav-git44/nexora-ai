import Link from "next/link";
import { ArrowRight, Bot, BookOpen, CheckSquare, Database, FileSearch, Lock, MessageSquare, ShieldCheck, Sparkles, Workflow, Gauge, KeyRound, Eye } from "lucide-react";
import { ButtonLink } from "@/components/ui";

const MODULES = [
  { icon: MessageSquare, title: "AI Business Assistant", body: "Ask questions, summarise documents, extract structured data and draft reports — answers grounded in your knowledge with inline citations." },
  { icon: BookOpen, title: "Knowledge Base & RAG", body: "Upload PDF, DOCX, XLSX, CSV, TXT and Markdown. Hybrid semantic + keyword search, reranking, versioning and role-based document access." },
  { icon: Bot, title: "Agent Studio", body: "Configure single-purpose agents with allow-listed tools, step and token budgets, execution logs and human approval for sensitive actions." },
  { icon: Workflow, title: "Visual Workflows", body: "Drag-and-drop triggers, AI actions and logic. Versioned publishing, webhooks with HMAC, approvals, retries and execution history." },
  { icon: Database, title: "Data Intelligence", body: "Ask your CSV/XLSX data questions in plain English. Generated SQL is parsed, validated and executed read-only — never destructive." },
  { icon: CheckSquare, title: "Tasks from conversations", body: "Turn meeting notes into owned, prioritised tasks. Kanban, list and calendar views with comments, attachments and activity." },
];

const STEPS = [
  { n: "01", title: "Connect your knowledge", body: "Upload policies, SOPs and datasets. NEXORA extracts, chunks and indexes them in minutes." },
  { n: "02", title: "Ask, analyse, automate", body: "Use the assistant, deploy an agent template or publish a workflow from a starter recipe." },
  { n: "03", title: "Measure outcomes", body: "Track completed AI-assisted outcomes, AI spend per outcome and adoption — measured, not guessed." },
];

const FAQ = [
  { q: "Which AI models does NEXORA use?", a: "A provider-neutral gateway routes each task to an appropriate Anthropic Claude or OpenAI model (cheap fast models for classification, stronger models for analysis) with automatic fallback. Workspaces can bring their own API keys." },
  { q: "Can one customer ever see another customer's data?", a: "Every table is tenant-scoped, every query and retrieval filters by organisation, and isolation is covered by automated tests. Documents can additionally be restricted by role." },
  { q: "Does it work without an AI key?", a: "Yes, in a clearly labelled demo mode: a local extractive engine answers from your documents, extracts tasks and drives agents so you can evaluate every flow. Generative quality requires a configured provider." },
  { q: "Do agents act on their own?", a: "Only with tools you allow. Anything with external side effects — email, webhooks — always pauses for a manager's approval, and every step is logged." },
  { q: "Is there an India-friendly billing option?", a: "Pricing is available in USD and INR. Stripe is supported today; Razorpay is the planned India-native provider (see the monetisation strategy)." },
];

export default function Landing() {
  return (
    <>
      <section className="relative overflow-hidden border-b border-line">
        <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_70%_50%_at_50%_-10%,var(--brand-soft),transparent)]" />
        <div className="mx-auto max-w-6xl px-4 pb-20 pt-20 text-center sm:px-6 sm:pt-28">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-3 py-1 text-[12px] text-muted"><Sparkles className="h-3.5 w-3.5 text-brand" /> AI business operations & workflow intelligence</span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl">One intelligent workspace.<br /><span className="text-brand">Infinite business possibilities.</span></h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">NEXORA brings your company knowledge, AI agents, workflow automation and business data into one secure workspace — so teams spend less time searching, copying and chasing, and more time deciding.</p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <ButtonLink href="/register" size="lg">Start free — 14-day Professional trial <ArrowRight className="h-4 w-4" /></ButtonLink>
            <ButtonLink href="/pricing" size="lg" variant="outline">See pricing</ButtonLink>
          </div>
          <p className="mt-3 text-[12px] text-subtle">No card required. Free plan available after the trial.</p>
          <div className="mx-auto mt-14 max-w-4xl rounded-2xl border border-line bg-panel p-2 shadow-pop">
            <div className="rounded-xl border border-line bg-canvas p-5 text-left">
              <div className="flex items-center gap-2 text-[12px] text-subtle"><FileSearch className="h-3.5 w-3.5" /> Assistant · grounded in 3 documents</div>
              <p className="mt-3 text-sm font-medium">Who needs to approve a 7,000 USD expense, and how fast are receipts due?</p>
              <div className="mt-3 rounded-lg border border-line bg-panel p-3 text-[13.5px] leading-relaxed text-muted">
                Expenses above 5,000 USD require <b className="text-fg">CFO approval and a written business case</b> <sup className="text-brand">[1]</sup>. Receipts must be submitted within <b className="text-fg">30 days</b> <sup className="text-brand">[1]</sup>.
                <div className="mt-2 flex gap-2 text-[11.5px]"><span className="rounded bg-panel-2 px-1.5 py-0.5">[1] Travel & Expense Policy · Approval limits</span></div>
              </div>
              <p className="mt-2 text-[11px] text-subtle">Illustrative example using the sample policy shipped with the demo workspace.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="product" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">Everything operations teams stitch together — in one place</h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-muted">Replace the patchwork of chat tools, wikis, spreadsheets and point automations with a single workspace that shares one permission model and one audit trail.</p>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => (
            <div key={m.title} className="rounded-xl border border-line bg-panel p-5 shadow-card">
              <div className="mb-3 inline-flex rounded-lg bg-brand-soft p-2"><m.icon className="h-5 w-5 text-brand" /></div>
              <h3 className="font-semibold">{m.title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{m.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y border-line bg-panel">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-16 sm:px-6 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n}><div className="font-mono text-sm text-brand">{s.n}</div><h3 className="mt-2 font-semibold">{s.title}</h3><p className="mt-1.5 text-[13.5px] text-muted">{s.body}</p></div>
          ))}
        </div>
      </section>

      <section id="security" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Built for trust from the first commit</h2>
            <p className="mt-3 text-muted">AI is only useful in operations if it is safe to point at real business data. NEXORA's controls are enforced on the server and covered by automated tests.</p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {[
              [Lock, "Tenant isolation", "Org-scoped queries, retrieval and jobs; 404 on cross-tenant access."],
              [ShieldCheck, "Prompt-injection defence", "Uploaded content is flagged, neutralised and treated as data, never instructions."],
              [KeyRound, "Secrets stay server-side", "Provider keys never reach the browser; integration credentials encrypted at rest."],
              [Eye, "Audit & approvals", "Sensitive agent actions need a manager's approval; every change is audit-logged."],
              [Database, "Read-only analytics", "LLM-generated SQL is parsed and allow-listed; destructive statements are rejected."],
              [Gauge, "Usage guardrails", "Rate limits, token budgets and plan quotas protect cost and availability."],
            ].map(([Icon, t, b]) => {
              const I = Icon as typeof Lock;
              return <li key={t as string} className="rounded-xl border border-line bg-panel p-4"><I className="h-4 w-4 text-brand" /><div className="mt-2 text-sm font-semibold">{t as string}</div><div className="mt-1 text-[12.5px] text-muted">{b as string}</div></li>;
            })}
          </ul>
        </div>
      </section>

      <section id="faq" className="border-t border-line bg-panel">
        <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
          <h2 className="text-center text-2xl font-semibold tracking-tight">Frequently asked questions</h2>
          <div className="mt-8 divide-y divide-line rounded-xl border border-line bg-canvas">
            {FAQ.map((f) => (
              <details key={f.q} className="group p-4">
                <summary className="cursor-pointer list-none font-medium marker:hidden">{f.q}<span className="float-right text-subtle group-open:rotate-45 transition-transform">+</span></summary>
                <p className="mt-2 text-[13.5px] text-muted">{f.a}</p>
              </details>
            ))}
          </div>
          <div className="mt-10 text-center"><ButtonLink href="/register" size="lg">Create your workspace</ButtonLink>
            <p className="mt-3 text-[12px] text-subtle">Already have an account? <Link href="/login" className="text-brand-text underline">Sign in</Link></p></div>
        </div>
      </section>
    </>
  );
}
