"use client";
import Link from "next/link";
import { ArrowRight, Bot, BookOpen, CheckCircle2, Circle, Database, MessageSquare, Upload, Users, Workflow } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useOrgSWR } from "@/lib/hooks";
import { Badge, ButtonLink, Card, CardBody, CardHeader, EmptyState, LoadingBlock, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { fmtNumber, fmtUSD, timeAgo } from "@/lib/utils";
import type { Agent, Conversation, Doc, Task } from "@/lib/types";

export default function Home() {
  const { user, org, can } = useAuth();
  const docs = useOrgSWR<Doc[]>("/documents");
  const convs = useOrgSWR<Conversation[]>("/conversations");
  const agents = useOrgSWR<Agent[]>("/agents");
  const wfs = useOrgSWR<{ id: string; status: string }[]>("/workflows");
  const members = useOrgSWR<unknown[]>("/orgs/current/members");
  const tasks = useOrgSWR<Task[]>("/tasks?assignee=me");
  const approvals = useOrgSWR<{ id: string; title: string; created_at: string }[]>("/approvals?status=pending");
  const dash = useOrgSWR<any>(can("analytics.read") ? "/analytics/dashboard?days=30" : null);

  const steps = [
    { done: (docs.data?.length ?? 0) > 0, label: "Upload your first document", href: "/app/knowledge", icon: Upload },
    { done: (convs.data?.length ?? 0) > 0, label: "Ask the assistant a question", href: "/app/assistant", icon: MessageSquare },
    { done: (agents.data?.length ?? 0) > 0, label: "Create an agent from a template", href: "/app/agents", icon: Bot },
    { done: (wfs.data ?? []).some((w) => w.status === "published"), label: "Publish a workflow", href: "/app/workflows", icon: Workflow },
    { done: (members.data?.length ?? 0) > 1, label: "Invite a teammate", href: "/app/settings/members", icon: Users },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const k = dash.data?.kpis;

  return (
    <div className="animate-in">
      <PageHeader eyebrow={org?.name} title={`Good to see you, ${user?.full_name.split(" ")[0]}`} description="Your operations workspace at a glance." />

      {doneCount < steps.length && (
        <Card className="mb-6">
          <CardHeader title="Get to first value" description={`${doneCount} of ${steps.length} complete — most teams finish in under 15 minutes.`}
            action={<Badge tone="brand">{Math.round((doneCount / steps.length) * 100)}%</Badge>} />
          <CardBody className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {steps.map((s) => (
              <Link key={s.label} href={s.href} className="flex items-center gap-2.5 rounded-lg border border-line p-3 text-[13px] hover:bg-panel-2">
                {s.done ? <CheckCircle2 className="h-4 w-4 shrink-0 text-success" /> : <Circle className="h-4 w-4 shrink-0 text-subtle" />}
                <span className={s.done ? "text-subtle line-through" : "text-fg"}>{s.label}</span>
              </Link>
            ))}
          </CardBody>
        </Card>
      )}

      {k && (
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="AI-assisted outcomes (30d)" value={fmtNumber(k.outcomes.value)} delta={k.outcomes.delta} sub="North Star input" />
          <Stat label="AI interactions" value={fmtNumber(k.ai_interactions.value)} delta={k.ai_interactions.delta} />
          <Stat label="AI spend" value={fmtUSD(k.ai_cost_usd.value)} sub={`${fmtNumber(k.tokens.value)} tokens`} />
          <Stat label="Time saved" value={`${dash.data.estimates.time_saved_hours.value} h`} estimate sub={<Link href="/app/analytics" className="underline">method</Link>} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Quick actions" />
          <CardBody className="grid gap-3 sm:grid-cols-2">
            {[
              { href: "/app/assistant", icon: MessageSquare, t: "Ask the assistant", d: "Grounded answers with citations" },
              { href: "/app/knowledge", icon: BookOpen, t: "Add knowledge", d: "PDF, DOCX, XLSX, CSV, TXT, MD" },
              { href: "/app/data", icon: Database, t: "Analyse a dataset", d: "Plain-English questions → safe SQL" },
              { href: "/app/tasks?extract=1", icon: CheckCircle2, t: "Notes → tasks", d: "Extract action items with AI" },
            ].map((a) => (
              <Link key={a.href} href={a.href} className="group flex items-start gap-3 rounded-xl border border-line p-4 hover:border-line-strong hover:bg-panel-2">
                <div className="rounded-lg bg-brand-soft p-2"><a.icon className="h-4 w-4 text-brand" /></div>
                <div className="flex-1"><div className="text-sm font-medium">{a.t}</div><div className="text-[12.5px] text-subtle">{a.d}</div></div>
                <ArrowRight className="h-4 w-4 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
              </Link>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Waiting on you" action={<ButtonLink href="/app/approvals" variant="ghost" size="sm">All</ButtonLink>} />
          <CardBody className="space-y-2">
            {approvals.isLoading && <LoadingBlock rows={2} />}
            {approvals.data?.length === 0 && tasks.data?.filter((t) => t.status !== "done").length === 0 && <p className="text-[13px] text-subtle">Nothing pending. 🎉</p>}
            {approvals.data?.slice(0, 3).map((a) => (
              <Link key={a.id} href="/app/approvals" className="flex items-center gap-2 rounded-lg border border-line p-2.5 text-[13px] hover:bg-panel-2">
                <StatusBadge status="pending" label="approval" /><span className="flex-1 truncate">{a.title}</span>
              </Link>
            ))}
            {tasks.data?.filter((t) => t.status !== "done").slice(0, 5).map((t) => (
              <Link key={t.id} href={`/app/tasks?task=${t.id}`} className="flex items-center gap-2 rounded-lg border border-line p-2.5 text-[13px] hover:bg-panel-2">
                <StatusBadge status={t.priority} /><span className="flex-1 truncate">{t.title}</span>{t.overdue && <Badge tone="danger">overdue</Badge>}
              </Link>
            ))}
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Recent conversations" action={<ButtonLink href="/app/assistant" variant="ghost" size="sm">Open assistant</ButtonLink>} />
        <CardBody>
          {convs.isLoading ? <LoadingBlock rows={3} /> : !convs.data?.length ? (
            <EmptyState icon={MessageSquare} title="No conversations yet" description="Ask about your policies, customers or processes." action={<ButtonLink href="/app/assistant" size="sm">Start a conversation</ButtonLink>} />
          ) : (
            <ul className="divide-y divide-line">
              {convs.data.slice(0, 5).map((c) => (
                <li key={c.id}><Link href={`/app/assistant/${c.id}`} className="flex items-center justify-between gap-3 py-2.5 text-[13.5px] hover:text-brand-text">
                  <span className="truncate">{c.title}</span><span className="shrink-0 text-[12px] text-subtle">{timeAgo(c.updated_at)}</span></Link></li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
