"use client";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { toastError } from "@/lib/hooks";
import { fmtDate, fmtNumber, fmtUSD, timeAgo } from "@/lib/utils";
import { Badge, Button, Callout, Card, CardBody, CardHeader, CodeBlock, EmptyState, Field, Input, LoadingBlock, PageHeader, Select, Stat, StatusBadge, Switch, Table, Tabs, Td, Textarea, Th } from "@/components/ui";

type T = "overview" | "orgs" | "users" | "jobs" | "ai" | "workflows" | "audit" | "flags" | "support" | "product";

export default function Admin() {
  const [tab, setTab] = useState<T>("overview");
  return (
    <div className="animate-in">
      <PageHeader title="Admin console" description="Platform-wide operations. Every endpoint here is protected server-side and hidden (404) from non-admins." />
      <Tabs className="mb-6" value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Overview" }, { value: "orgs", label: "Organisations" }, { value: "users", label: "Users" }, { value: "jobs", label: "Jobs" }, { value: "ai", label: "AI spend" },
        { value: "workflows", label: "Workflow failures" }, { value: "audit", label: "Security audit" }, { value: "flags", label: "Feature flags" }, { value: "support", label: "Support" }, { value: "product", label: "Product metrics" }]} />
      {tab === "overview" && <Overview />}{tab === "orgs" && <Orgs />}{tab === "users" && <Users />}{tab === "jobs" && <Jobs />}{tab === "ai" && <AISpend />}
      {tab === "workflows" && <WfFailures />}{tab === "audit" && <AuditAll />}{tab === "flags" && <Flags />}{tab === "support" && <SupportAdmin />}{tab === "product" && <Product />}
    </div>
  );
}

function Overview() {
  const { data } = useSWR<any>("/admin/overview", { refreshInterval: 15000 });
  if (!data) return <LoadingBlock rows={5} />;
  const h = data.health;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Organisations" value={data.organizations} /><Stat label="Users" value={data.users} sub={`${data.active_users_7d} active (7d)`} />
        <Stat label="MRR (Stripe-billed)" value={fmtUSD(data.mrr_usd.stripe_billed, 0)} sub={`${fmtUSD(data.mrr_usd.demo_billing, 0)} demo-billed`} />
        <Stat label="AI spend (7d)" value={fmtUSD(data.ai_7d.cost_usd, 4)} sub={`${fmtNumber(data.ai_7d.requests)} calls · ${(data.ai_7d.error_rate * 100).toFixed(1)}% errors`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card><CardHeader title="System health" /><CardBody className="space-y-2 text-[13px]">
          {[["Database", h.database], ["Redis (rate limits/cache)", h.redis], ["Background worker", h.worker], ["Anthropic", h.ai_providers.anthropic], ["OpenAI", h.ai_providers.openai]].map(([k, v]) => (
            <div key={k as string} className="flex justify-between"><span>{k}</span>{v ? <Badge tone="success" dot>ok</Badge> : <Badge tone={k === "Anthropic" || k === "OpenAI" ? "warning" : "danger"} dot>{k === "Anthropic" || k === "OpenAI" ? "not configured" : "down"}</Badge>}</div>))}
          {h.ai_providers.demo_mode && <Callout tone="warning">AI is running in demo mode (no provider keys).</Callout>}
          <p className="text-[12px] text-subtle">Worker last completed a job {timeAgo(data.worker_last_completed_at)}.</p>
        </CardBody></Card>
        <Card><CardHeader title="Subscriptions" /><CardBody className="space-y-1.5 text-[13px]">{Object.entries(data.subscriptions_by_plan).map(([p, n]) => <div key={p} className="flex justify-between capitalize"><span>{p}</span><span className="tabular-nums">{n as number}</span></div>)}
          <p className="pt-2 text-[12px] text-subtle">{data.mrr_usd.note}</p></CardBody></Card>
        <Card><CardHeader title="Jobs & workflows" /><CardBody className="space-y-1.5 text-[13px]">
          {Object.entries(data.jobs).map(([s, n]) => <div key={s} className="flex justify-between"><StatusBadge status={s} /><span className="tabular-nums">{n as number}</span></div>)}
          <div className="border-t border-line pt-2 text-[12px] text-subtle">Workflow runs (7d): {Object.entries(data.workflows_7d).map(([s, n]) => `${s} ${n}`).join(" · ") || "none"}</div>
        </CardBody></Card>
      </div>
    </div>
  );
}

function Orgs() {
  const [q, setQ] = useState("");
  const { data, mutate } = useSWR<any[]>(`/admin/orgs${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  const update = async (id: string, body: Record<string, unknown>) => { try { await api(`/admin/orgs/${id}`, { method: "PATCH", body, noOrg: true }); mutate(); toast.success("Updated"); } catch (e) { toastError(e); } };
  return (
    <Card><CardHeader title="Organisations" action={<Input className="w-56" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search organisations" />} />
      {!data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>Name</Th><Th>Plan</Th><Th>Members</Th><Th>AI cost</Th><Th>Created</Th><Th>Status</Th><Th /></tr></thead><tbody>{data.map((o) => (
        <tr key={o.id}><Td className="font-medium">{o.name}<div className="font-mono text-[11px] text-subtle">{o.id}</div></Td>
          <Td><Select className="h-8 w-36 text-[12.5px]" value={o.plan} onChange={(e) => update(o.id, { plan: e.target.value })} aria-label="Plan">{["free", "starter", "professional", "enterprise"].map((p) => <option key={p}>{p}</option>)}</Select><div className="text-[11px] text-subtle">{o.status}</div></Td>
          <Td>{o.members}</Td><Td>{fmtUSD(o.ai_cost_usd, 4)}</Td><Td className="text-subtle">{fmtDate(o.created_at)}</Td>
          <Td>{o.suspended ? <Badge tone="danger">suspended</Badge> : o.deletion_requested_at ? <Badge tone="warning">deleting</Badge> : <Badge tone="success">active</Badge>}</Td>
          <Td><Button size="sm" variant="ghost" onClick={() => update(o.id, { suspended: !o.suspended })}>{o.suspended ? "Unsuspend" : "Suspend"}</Button></Td></tr>
      ))}</tbody></Table>}</Card>
  );
}

function Users() {
  const [q, setQ] = useState("");
  const { data, mutate } = useSWR<any[]>(`/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <Card><CardHeader title="Users" action={<Input className="w-56" placeholder="Search email or name" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users" />} />
      {!data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>User</Th><Th>Verified</Th><Th>Last login</Th><Th>Status</Th><Th /></tr></thead><tbody>{data.map((u) => (
        <tr key={u.id}><Td><div className="font-medium">{u.full_name} {u.is_super_admin && <Badge tone="danger">admin</Badge>}</div><div className="text-[12px] text-subtle">{u.email}</div></Td>
          <Td>{u.email_verified ? "✓" : "—"}</Td><Td className="text-subtle">{timeAgo(u.last_login_at)}</Td><Td><StatusBadge status={u.is_active ? "active" : "deactivated"} /></Td>
          <Td>{!u.is_super_admin && <Button size="sm" variant="ghost" onClick={async () => { try { await api(`/admin/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active }, noOrg: true }); mutate(); } catch (e) { toastError(e); } }}>{u.is_active ? "Deactivate" : "Reactivate"}</Button>}</Td></tr>
      ))}</tbody></Table>}</Card>
  );
}

function Jobs() {
  const [status, setStatus] = useState("failed");
  const { data, mutate } = useSWR<any[]>(`/admin/jobs?status=${status}`);
  return (
    <Card><CardHeader title="Background jobs" description="Postgres-backed queue with retries and exponential backoff." action={<Select className="w-36" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Job status">{["failed", "queued", "running", "succeeded"].map((s) => <option key={s}>{s}</option>)}</Select>} />
      {!data ? <CardBody><LoadingBlock /></CardBody> : !data.length ? <CardBody><EmptyState title={`No ${status} jobs`} /></CardBody> : <Table><thead><tr><Th>Kind</Th><Th>Attempts</Th><Th>Error</Th><Th>Created</Th><Th /></tr></thead><tbody>{data.map((j) => (
        <tr key={j.id}><Td><code className="font-mono text-[12px]">{j.kind}</code></Td><Td>{j.attempts}</Td><Td className="max-w-md truncate text-[12px] text-danger" title={j.last_error}>{j.last_error?.split("\n")[0]}</Td><Td className="text-subtle">{timeAgo(j.created_at)}</Td>
          <Td>{j.status === "failed" && <Button size="sm" variant="ghost" onClick={async () => { await api(`/admin/jobs/${j.id}/retry`, { method: "POST", noOrg: true }); mutate(); toast.success("Re-queued"); }}>Retry</Button>}</Td></tr>
      ))}</tbody></Table>}</Card>
  );
}

function AISpend() {
  const { data } = useSWR<any>("/admin/ai-usage?days=30");
  if (!data) return <LoadingBlock />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card><CardHeader title="By model (30d)" /><Table><thead><tr><Th>Model</Th><Th>Requests</Th><Th>Tokens</Th><Th>Cost</Th></tr></thead><tbody>{data.by_model.map((m: any) => <tr key={m.model}><Td>{m.provider}/<span className="font-mono text-[12px]">{m.model}</span></Td><Td>{fmtNumber(m.requests)}</Td><Td>{fmtNumber(m.tokens)}</Td><Td>{fmtUSD(m.cost_usd, 4)}</Td></tr>)}</tbody></Table></Card>
      <Card><CardHeader title="Top organisations by spend" /><Table><thead><tr><Th>Organisation</Th><Th>Requests</Th><Th>Cost</Th></tr></thead><tbody>{data.top_orgs.map((o: any) => <tr key={o.organization}><Td>{o.organization}</Td><Td>{fmtNumber(o.requests)}</Td><Td>{fmtUSD(o.cost_usd, 4)}</Td></tr>)}</tbody></Table></Card>
    </div>
  );
}

function WfFailures() {
  const { data } = useSWR<any[]>("/admin/workflow-failures");
  return <Card><CardHeader title="Recent workflow failures" />{!data ? <CardBody><LoadingBlock /></CardBody> : !data.length ? <CardBody><EmptyState title="No failures" /></CardBody> :
    <Table><thead><tr><Th>Organisation</Th><Th>Workflow</Th><Th>Error</Th><Th>When</Th></tr></thead><tbody>{data.map((f) => <tr key={f.id}><Td>{f.organization}</Td><Td>{f.workflow}</Td><Td className="max-w-md truncate text-[12px] text-danger">{f.error}</Td><Td className="text-subtle">{timeAgo(f.created_at)}</Td></tr>)}</tbody></Table>}</Card>;
}

function AuditAll() {
  const [action, setAction] = useState("");
  const { data } = useSWR<any[]>(`/admin/audit-logs${action ? `?action=${action}` : ""}`);
  return <Card><CardHeader title="Security audit log (all tenants)" action={<Input className="w-48" placeholder="action prefix e.g. auth" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action prefix" />} />
    {!data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>When</Th><Th>Action</Th><Th>Org</Th><Th>Details</Th><Th>IP</Th></tr></thead><tbody>{data.map((l) => <tr key={l.id}><Td className="whitespace-nowrap text-subtle">{fmtDate(l.created_at, true)}</Td><Td><code className="font-mono text-[12px]">{l.action}</code></Td><Td className="font-mono text-[11px] text-subtle">{l.org_id?.slice(0, 8) || "—"}</Td><Td className="max-w-sm truncate text-[12px] text-subtle">{JSON.stringify(l.details)}</Td><Td className="text-subtle">{l.ip}</Td></tr>)}</tbody></Table>}</Card>;
}

function Flags() {
  const { data, mutate } = useSWR<any[]>("/admin/feature-flags");
  const [f, setF] = useState({ key: "", description: "", enabled: false });
  const save = async (body: any) => { try { await api("/admin/feature-flags", { method: "PUT", body, noOrg: true }); mutate(); toast.success("Saved"); } catch (e) { toastError(e); } };
  return (
    <Card><CardHeader title="Feature flags" description="Global switches with per-organisation overrides (set via API)." />
      <CardBody className="space-y-4">
        <form className="grid gap-2 sm:grid-cols-[1fr_2fr_auto_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); save({ ...f, org_overrides: {} }); setF({ key: "", description: "", enabled: false }); }}>
          <Field label="Key"><Input value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} placeholder="ai_workflow_suggestions" required pattern="[a-z0-9_.\-]{2,80}" /></Field>
          <Field label="Description"><Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Switch checked={f.enabled} onChange={(v) => setF({ ...f, enabled: v })} label="Enabled" /><Button type="submit">Add</Button>
        </form>
        <ul className="divide-y divide-line">{data?.map((x) => (
          <li key={x.key} className="flex items-center gap-3 py-2.5 text-[13px]"><code className="font-mono">{x.key}</code><span className="flex-1 text-subtle">{x.description}</span>
            {Object.keys(x.org_overrides).length > 0 && <Badge>{Object.keys(x.org_overrides).length} overrides</Badge>}
            <Switch checked={x.enabled} onChange={(v) => save({ ...x, enabled: v })} /></li>
        ))}</ul>
      </CardBody></Card>
  );
}

function SupportAdmin() {
  const { data, mutate } = useSWR<any[]>("/admin/support-tickets");
  const [notes, setNotes] = useState<Record<string, string>>({});
  return (
    <div className="space-y-3">{!data ? <LoadingBlock /> : !data.length ? <EmptyState title="No tickets" /> : data.map((t) => (
      <Card key={t.id}><CardBody>
        <div className="flex flex-wrap items-center gap-2 text-[13px]"><StatusBadge status={t.status === "resolved" ? "succeeded" : "pending"} label={t.status} /><Badge>{t.priority}</Badge><span className="font-medium">{t.subject}</span><span className="ml-auto text-subtle">{t.organization} · {timeAgo(t.created_at)}</span></div>
        <p className="mt-2 whitespace-pre-wrap text-[13px] text-muted">{t.body}</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row"><Input placeholder="Reply / internal note" value={notes[t.id] ?? t.admin_note ?? ""} onChange={(e) => setNotes({ ...notes, [t.id]: e.target.value })} aria-label="Admin note" />
          <Button size="sm" variant="outline" onClick={async () => { await api(`/admin/support-tickets/${t.id}`, { method: "PATCH", body: { admin_note: notes[t.id], status: "pending" }, noOrg: true }); mutate(); }}>Save note</Button>
          <Button size="sm" onClick={async () => { await api(`/admin/support-tickets/${t.id}`, { method: "PATCH", body: { admin_note: notes[t.id] ?? t.admin_note, status: "resolved" }, noOrg: true }); mutate(); toast.success("Resolved"); }}>Resolve</Button></div>
      </CardBody></Card>
    ))}</div>
  );
}

function Product() {
  const { data } = useSWR<any>("/admin/product-metrics");
  const exp = useSWR<any>("/experiments/results");
  if (!data) return <LoadingBlock />;
  const a = data.activation; const r = data.retention;
  const pct = (n: number, d: number) => (d ? `${((n / d) * 100).toFixed(0)}%` : "—");
  return (
    <div className="space-y-6">
      <Callout tone="info">{data.note}</Callout>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Signups (all time)" value={a.signups} /><Stat label="Activation: first AI answer" value={pct(a.first_ai, a.signups)} sub={`${a.first_ai} users`} />
        <Stat label="Activation: first outcome" value={pct(a.first_outcome, a.signups)} sub={a.median_ttfv_min !== null ? `median TTFV ${Math.round(a.median_ttfv_min)} min` : "TTFV —"} />
        <Stat label="D7 / D30 retention" value={`${pct(r.retained_d7, r.eligible_d7)} / ${pct(r.retained_d30, r.eligible_d30)}`} sub={`${r.eligible_d7} / ${r.eligible_d30} eligible`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card><CardHeader title="North Star: weekly AI-assisted outcomes" /><Table><thead><tr><Th>Week</Th><Th>Outcomes</Th></tr></thead><tbody>{data.north_star_weekly.map((w: any) => <tr key={w.week}><Td>{w.week}</Td><Td className="tabular-nums">{w.outcomes}</Td></tr>)}</tbody></Table></Card>
        <Card><CardHeader title="Experiments" description="Assignment counts only — no results are reported until an experiment has real traffic." />
          <CardBody>{exp.data && <CodeBlock className="max-h-80">{JSON.stringify(Object.fromEntries(Object.entries(exp.data.experiments).map(([k, v]: any) => [k, { status: v.config.status, variants: v.config.variants, assignments: v.assignments }])), null, 2)}</CodeBlock>}</CardBody></Card>
      </div>
    </div>
  );
}
