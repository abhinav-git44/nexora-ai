"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, Brain, CheckCircle2, Play, ShieldCheck, Wrench, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, fmtNumber, fmtPct, fmtUSD, timeAgo } from "@/lib/utils";
import type { Agent, AgentRun, RunStep } from "@/lib/types";
import { Badge, Button, Callout, Card, CardBody, CardHeader, Checkbox, CodeBlock, EmptyState, Field, Input, LoadingBlock, Markdown, PageHeader, Select, Stat, StatusBadge, Switch, Table, Tabs, Td, Textarea, Th } from "@/components/ui";

type ToolInfo = { name: string; description: string; min_role: string; sensitive: boolean; category: string };

function StepView({ s }: { s: RunStep }) {
  const icon = s.type === "thought" ? Brain : s.type === "tool_call" ? Wrench : s.type === "approval" ? ShieldCheck : s.type === "final" ? CheckCircle2 : AlertTriangle;
  const I = icon;
  const tone = s.status === "ok" ? "text-brand" : s.status === "pending" ? "text-warning" : "text-danger";
  return (
    <li className="relative pl-8">
      <span className={cn("absolute left-0 top-0.5 flex h-6 w-6 items-center justify-center rounded-full border border-line bg-panel", tone)}><I className="h-3.5 w-3.5" /></span>
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        <span className="font-medium capitalize">{s.type.replace("_", " ")}</span>{s.tool && <Badge>{s.tool}</Badge>}
        {s.status !== "ok" && <StatusBadge status={s.status} />}{s.attempt > 1 && <Badge tone="warning">attempt {s.attempt}</Badge>}
        <span className="text-subtle">{s.latency_ms ? `${s.latency_ms} ms` : ""}</span>
      </div>
      {s.type === "thought" && s.output?.text && <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-[12.5px] text-muted">{s.output.text}</p>}
      {s.type === "thought" && s.output?.tool_calls?.length > 0 && <p className="mt-1 text-[12px] text-subtle">→ calls {s.output.tool_calls.map((t: { name: string }) => t.name).join(", ")}</p>}
      {(s.type === "tool_call" || s.type === "approval") && (
        <details className="mt-1"><summary className="cursor-pointer text-[12px] text-subtle">input / output</summary>
          <CodeBlock className="mt-1 max-h-60">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</CodeBlock></details>
      )}
      {s.type === "error" && <p className="mt-1 text-[12.5px] text-danger">{s.output?.error}</p>}
    </li>
  );
}

function RunPanel({ runId }: { runId: string }) {
  const run = useOrgSWR<AgentRun>(`/agents/runs/${runId}`, { refreshInterval: (r) => (r && ["queued", "running"].includes(r.status) ? 1200 : r?.status === "awaiting_approval" ? 4000 : 0) });
  if (!run.data) return <LoadingBlock rows={3} />;
  const r = run.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]"><StatusBadge status={r.status} /><span className="text-subtle">{r.steps_count} steps · {fmtNumber(r.total_tokens)} tokens · {fmtUSD(r.cost_usd, 4)}{r.duration_ms ? ` · ${(r.duration_ms / 1000).toFixed(1)}s` : ""}</span>
        {["queued", "running", "awaiting_approval"].includes(r.status) && <Button size="sm" variant="ghost" onClick={async () => { await api(`/agents/runs/${r.id}/cancel`, { method: "POST" }); run.mutate(); }}>Cancel</Button>}</div>
      {r.status === "awaiting_approval" && <Callout tone="warning" icon={ShieldCheck} title="Waiting for human approval">A manager must approve the pending action in <Link className="underline" href="/app/approvals">Approvals</Link> before the agent continues.</Callout>}
      <ol className="space-y-4 border-l border-line pl-0 [&>li]:ml-[-1px]">{r.steps?.map((s) => <StepView key={s.idx} s={s} />)}</ol>
      {r.output && <Card><CardHeader title="Result" /><CardBody><Markdown>{r.output}</Markdown>{r.structured_output && <CodeBlock className="mt-3">{JSON.stringify(r.structured_output, null, 2)}</CodeBlock>}</CardBody></Card>}
      {r.error && <Callout tone="danger" icon={XCircle} title="Run failed">{r.error}</Callout>}
    </div>
  );
}

export default function AgentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const sp = useSearchParams();
  const router = useRouter();
  const { can } = useAuth();
  const agent = useOrgSWR<Agent>(`/agents/${id}`);
  const runs = useOrgSWR<AgentRun[]>(`/agents/${id}/runs`, { refreshInterval: 5000 });
  const metrics = useOrgSWR<any>(`/agents/${id}/metrics`);
  const [tab, setTab] = useState<"console" | "config" | "runs" | "metrics">((sp.get("tab") as "config") || "console");
  const [input, setInput] = useState("");
  const [runId, setRunId] = useState<string | null>(sp.get("run"));
  const [busy, setBusy] = useState(false);
  if (!agent.data) return <LoadingBlock rows={6} />;
  const a = agent.data;
  return (
    <div className="animate-in">
      <Link href="/app/agents" className="mb-3 inline-flex items-center gap-1 text-[13px] text-subtle hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />Agents</Link>
      <PageHeader title={a.name} description={a.description} actions={<><Badge>{a.model_route}</Badge><Badge>{a.tools.length} tools</Badge>{a.memory_enabled && <Badge tone="brand">memory</Badge>}</>} />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: "console", label: "Test console" }, { value: "config", label: "Configuration" }, { value: "runs", label: "Runs", count: runs.data?.length }, { value: "metrics", label: "Performance" }]} />
      {tab === "console" && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="lg:col-span-2 self-start"><CardHeader title="Run the agent" description="Runs execute in the background worker; steps stream in as they complete." />
            <CardBody className="space-y-3">
              <Textarea rows={6} value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. Extract action items from these notes and create tasks…" aria-label="Agent input" />
              <Button className="w-full" loading={busy} disabled={!input.trim() || !can("agents.run")} onClick={async () => {
                setBusy(true);
                try { const r = await api<AgentRun>(`/agents/${id}/runs`, { body: { input } }); setRunId(r.id); runs.mutate(); } catch (e) { toastError(e); } finally { setBusy(false); }
              }}><Play className="h-4 w-4" />Run</Button>
              <div className="rounded-lg bg-panel-2 p-3 text-[12px] text-subtle">
                <div className="mb-1 font-medium text-fg">Guardrails</div>
                Max {a.max_steps} model steps · {fmtNumber(a.max_tokens_per_run)} token budget · tools: {a.tools.join(", ") || "none"}
                {a.approval_required_tools.length > 0 && <> · approval required for {a.approval_required_tools.join(", ")}</>}
              </div>
            </CardBody></Card>
          <div className="lg:col-span-3">{runId ? <RunPanel runId={runId} /> : <EmptyState icon={Play} title="No run selected" description="Run the agent or pick a previous run from the Runs tab." />}</div>
        </div>
      )}
      {tab === "config" && <ConfigEditor agent={a} onSaved={() => agent.mutate()} canEdit={can("agents.write")} onArchived={() => router.push("/app/agents")} />}
      {tab === "runs" && (
        <Card>{!runs.data?.length ? <CardBody><EmptyState title="No runs yet" /></CardBody> : (
          <Table><thead><tr><Th>Input</Th><Th>Status</Th><Th>Steps</Th><Th>Tokens</Th><Th>Cost</Th><Th>When</Th></tr></thead>
            <tbody>{runs.data.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-panel-2" onClick={() => { setRunId(r.id); setTab("console"); }}>
                <Td className="max-w-xs truncate">{r.input}</Td><Td><StatusBadge status={r.status} /></Td><Td>{r.steps_count}</Td><Td>{fmtNumber(r.total_tokens)}</Td><Td>{fmtUSD(r.cost_usd, 4)}</Td><Td className="text-subtle">{timeAgo(r.created_at)}</Td>
              </tr>))}</tbody></Table>
        )}</Card>
      )}
      {tab === "metrics" && metrics.data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Runs" value={metrics.data.runs} sub={`${metrics.data.awaiting_approval} awaiting approval`} />
            <Stat label="Success rate" value={fmtPct(metrics.data.success_rate)} sub={`${metrics.data.failed} failed`} />
            <Stat label="Avg duration" value={metrics.data.avg_duration_ms ? `${(metrics.data.avg_duration_ms / 1000).toFixed(1)}s` : "—"} />
            <Stat label="Total cost" value={fmtUSD(metrics.data.total_cost_usd, 4)} sub={`${fmtNumber(metrics.data.avg_tokens)} avg tokens`} />
          </div>
          <Card><CardHeader title="Tool usage" description="Calls and failures per tool — a quick read on tool-selection quality." />
            {metrics.data.tool_usage.length ? <Table><thead><tr><Th>Tool</Th><Th>Calls</Th><Th>Errors / blocked</Th></tr></thead><tbody>{metrics.data.tool_usage.map((t: any) => <tr key={t.tool}><Td>{t.tool}</Td><Td>{t.calls}</Td><Td className={t.errors ? "text-danger" : ""}>{t.errors}</Td></tr>)}</tbody></Table> : <CardBody><p className="text-sm text-subtle">No tool calls yet.</p></CardBody>}</Card>
        </div>
      )}
    </div>
  );
}

function ConfigEditor({ agent, onSaved, canEdit, onArchived }: { agent: Agent; onSaved: () => void; canEdit: boolean; onArchived: () => void }) {
  const tools = useOrgSWR<ToolInfo[]>("/agents/tools");
  const [f, setF] = useState(agent);
  const [busy, setBusy] = useState(false);
  useEffect(() => setF(agent), [agent]);
  const set = <K extends keyof Agent>(k: K, v: Agent[K]) => setF({ ...f, [k]: v });
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2"><CardHeader title="Behaviour" />
        <CardBody className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} disabled={!canEdit} /></Field>
            <Field label="Model route" hint="Routes pick a cost-appropriate model with automatic provider fallback."><Select value={f.model_route} onChange={(e) => set("model_route", e.target.value)} disabled={!canEdit}>
              <option value="agent">Agent (balanced, tool use)</option><option value="fast">Fast / low cost</option><option value="analysis">Deep analysis (frontier)</option><option value="chat">Chat</option></Select></Field>
          </div>
          <Field label="Description"><Input value={f.description} onChange={(e) => set("description", e.target.value)} disabled={!canEdit} /></Field>
          <Field label="Instructions" hint="The agent's operating procedure. Guardrails (tool rules, injection defence) are appended automatically."><Textarea rows={8} value={f.instructions} onChange={(e) => set("instructions", e.target.value)} disabled={!canEdit} /></Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Max model steps"><Input type="number" min={1} max={20} value={f.max_steps} onChange={(e) => set("max_steps", Number(e.target.value))} disabled={!canEdit} /></Field>
            <Field label="Token budget / run"><Input type="number" min={1000} max={200000} step={1000} value={f.max_tokens_per_run} onChange={(e) => set("max_tokens_per_run", Number(e.target.value))} disabled={!canEdit} /></Field>
            <Field label="Output format"><Select value={f.output_format} onChange={(e) => set("output_format", e.target.value)} disabled={!canEdit}><option value="markdown">Markdown</option><option value="json">JSON (schema)</option><option value="text">Plain text</option></Select></Field>
          </div>
          {f.output_format === "json" && <Field label="Output JSON schema"><Textarea rows={6} className="font-mono text-[12px]" defaultValue={JSON.stringify(f.output_schema ?? { type: "object", properties: {}, required: [], additionalProperties: false }, null, 2)}
            onBlur={(e) => { try { set("output_schema", JSON.parse(e.target.value)); } catch { toast.error("Invalid JSON schema"); } }} disabled={!canEdit} /></Field>}
          <Switch checked={f.memory_enabled} onChange={(v) => set("memory_enabled", v)} label="Remember a short note from each successful run" disabled={!canEdit} />
          {f.memory_enabled && f.memory.length > 0 && <div className="rounded-lg bg-panel-2 p-3 text-[12px] text-muted">{f.memory.slice(-3).map((m) => <p key={m.at}>• {m.note}</p>)}
            <button className="mt-1 text-brand-text" onClick={async () => { await api(`/agents/${agent.id}/memory/clear`, { method: "POST" }); onSaved(); }}>Clear memory</button></div>}
        </CardBody></Card>
      <Card className="self-start"><CardHeader title="Tools & permissions" description="Agents can only call tools you allow. Sensitive tools always require approval." />
        <CardBody className="space-y-3">
          {tools.data?.map((t) => {
            const on = f.tools.includes(t.name);
            return (
              <div key={t.name} className="rounded-lg border border-line p-2.5">
                <Checkbox checked={on} onChange={(v) => setF({ ...f, tools: v ? [...f.tools, t.name] : f.tools.filter((x) => x !== t.name), approval_required_tools: v ? f.approval_required_tools : f.approval_required_tools.filter((x) => x !== t.name) })}
                  label={<span className="font-medium">{t.name}{t.sensitive && <Badge tone="warning" className="ml-1.5">sensitive</Badge>}</span>} />
                <p className="ml-6 mt-0.5 text-[11.5px] text-subtle">{t.description} <span className="capitalize">(min role: {t.min_role})</span></p>
                {on && !t.sensitive && <div className="ml-6 mt-1"><Checkbox checked={f.approval_required_tools.includes(t.name)} onChange={(v) => set("approval_required_tools", v ? [...f.approval_required_tools, t.name] : f.approval_required_tools.filter((x) => x !== t.name))} label={<span className="text-[12px]">Require approval</span>} /></div>}
              </div>
            );
          })}
          {canEdit && <div className="flex gap-2 pt-2">
            <Button loading={busy} onClick={async () => { setBusy(true); try { const { id, created_at, runs, success_rate, last_run_at, memory, ...body } = f; void id; void created_at; void runs; void success_rate; void last_run_at; void memory; await api(`/agents/${agent.id}`, { method: "PUT", body }); toast.success("Agent saved"); onSaved(); } catch (e) { toastError(e); } finally { setBusy(false); } }}>Save changes</Button>
            <Button variant="ghost" className="text-danger" onClick={async () => { if (!confirm("Archive this agent?")) return; await api(`/agents/${agent.id}`, { method: "DELETE" }); onArchived(); }}>Archive</Button>
          </div>}
        </CardBody></Card>
    </div>
  );
}
