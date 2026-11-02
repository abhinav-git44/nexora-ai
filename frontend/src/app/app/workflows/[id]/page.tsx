"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { use, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, Pause, Play, RotateCcw, Rocket, Save, ShieldAlert } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { fmtPct, timeAgo, fmtDate } from "@/lib/utils";
import type { Definition, NodeSpec } from "@/components/app/workflow-builder";
import { Badge, Button, Callout, Card, CardBody, CardHeader, CodeBlock, EmptyState, Input, LoadingBlock, Modal, Stat, StatusBadge, Table, Tabs, Td, Textarea, Th } from "@/components/ui";

const WorkflowCanvas = dynamic(() => import("@/components/app/workflow-builder").then((m) => m.WorkflowCanvas), { ssr: false, loading: () => <LoadingBlock rows={6} /> });

type Issue = { node_id?: string; field?: string; message: string };
type Validation = { valid: boolean; errors: Issue[]; warnings: Issue[] };
type Wf = { id: string; name: string; description: string; status: string; published_version: number | null; trigger_type: string; schedule_cron: string | null; next_run_at: string | null;
  definition: Definition; webhook_url?: string; form_url?: string | null; webhook_secret?: string; versions: { version: number; created_at: string }[]; validation: Validation };
type Exec = { id: string; version: number; trigger: string; status: string; input: any; output: any; error: string | null; attempt: number; created_at: string; duration_ms: number | null;
  logs?: { node_id: string; node_type: string; status: string; input: any; output: any; error: string | null; duration_ms: number }[] };

export default function WorkflowDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const sp = useSearchParams();
  const { can } = useAuth();
  const wf = useOrgSWR<Wf>(`/workflows/${id}`);
  const specs = useOrgSWR<NodeSpec[]>("/workflows/nodes");
  const execs = useOrgSWR<Exec[]>(`/workflows/${id}/executions`, { refreshInterval: (d) => (d?.some((e) => ["queued", "running", "waiting"].includes(e.status)) ? 2000 : 10000) });
  const [tab, setTab] = useState<"builder" | "executions" | "analytics" | "trigger">(sp.get("execution") ? "executions" : "builder");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [runInput, setRunInput] = useState("{}");
  const [execId, setExecId] = useState<string | null>(sp.get("execution"));
  const def = useRef<Definition | null>(null);
  const editable = can("workflows.write");
  const errors = useMemo(() => Object.fromEntries((validation ?? wf.data?.validation)?.errors.filter((e) => e.node_id).map((e) => [e.node_id!, e.message]) ?? []), [validation, wf.data]);

  if (!wf.data || !specs.data) return <LoadingBlock rows={6} />;
  const w = wf.data;
  const v = validation ?? w.validation;

  const save = async () => {
    if (!def.current) return;
    setBusy("save");
    try { const r = await api<Wf>(`/workflows/${id}`, { method: "PUT", body: { definition: def.current } }); setValidation(r.validation); setDirty(false); toast.success("Draft saved"); wf.mutate(); }
    catch (e) { toastError(e); } finally { setBusy(null); }
  };
  const publish = async () => {
    setBusy("publish");
    try { if (dirty) await save(); await api(`/workflows/${id}/publish`, { method: "POST" }); toast.success("Published"); wf.mutate(); setValidation(null); }
    catch (e: any) { if (e?.details?.errors) setValidation(e.details); toastError(e); } finally { setBusy(null); }
  };

  return (
    <div className="animate-in">
      <Link href="/app/workflows" className="mb-3 inline-flex items-center gap-1 text-[13px] text-subtle hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />Workflows</Link>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <EditableTitle value={w.name} disabled={!editable} onSave={async (name) => { await api(`/workflows/${id}`, { method: "PUT", body: { name } }); wf.mutate(); }} />
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12.5px] text-subtle"><StatusBadge status={w.status} />{w.published_version && <span>live: v{w.published_version}</span>}<span className="capitalize">trigger: {w.trigger_type.replace("_", " ")}</span>{dirty && <Badge tone="warning">unsaved changes</Badge>}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {editable && <Button variant="outline" size="sm" onClick={save} loading={busy === "save"} disabled={!dirty}><Save className="h-4 w-4" />Save draft</Button>}
          {editable && <Button variant="outline" size="sm" onClick={async () => { if (dirty) await save(); setValidation(await api<Validation>(`/workflows/${id}/validate`, { method: "POST" })); }}><CheckCircle2 className="h-4 w-4" />Validate</Button>}
          {editable && <Button size="sm" onClick={publish} loading={busy === "publish"}><Rocket className="h-4 w-4" />Publish</Button>}
          {w.status === "published" && can("workflows.run") && w.trigger_type === "manual" && <Button size="sm" variant="secondary" onClick={() => setRunOpen(true)}><Play className="h-4 w-4" />Run</Button>}
          {editable && ["published", "paused"].includes(w.status) && <Button size="sm" variant="ghost" onClick={async () => { await api(`/workflows/${id}/pause`, { method: "POST" }); wf.mutate(); }}><Pause className="h-4 w-4" />{w.status === "paused" ? "Resume" : "Pause"}</Button>}
        </div>
      </div>
      {(v.errors.length > 0 || v.warnings.length > 0) && (
        <div className="mb-4 space-y-2">
          {v.errors.length > 0 && <Callout tone="danger" icon={ShieldAlert} title={`${v.errors.length} issue(s) block publishing`}><ul className="list-disc pl-4">{v.errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul></Callout>}
          {v.warnings.length > 0 && <Callout tone="warning" title="Warnings"><ul className="list-disc pl-4">{v.warnings.map((e, i) => <li key={i}>{e.message}</li>)}</ul></Callout>}
        </div>
      )}
      <Tabs className="mb-4" value={tab} onChange={setTab} tabs={[{ value: "builder", label: "Builder" }, { value: "executions", label: "Executions", count: execs.data?.length }, { value: "analytics", label: "Analytics" }, { value: "trigger", label: "Trigger & versions" }]} />
      {tab === "builder" && (
        <Card className="h-[70vh] overflow-hidden">
          <WorkflowCanvas initial={w.definition} specs={specs.data} readOnly={!editable} errors={errors}
            onChange={(d) => { if (def.current && JSON.stringify(d) !== JSON.stringify(def.current)) setDirty(true); def.current = d; }} />
        </Card>
      )}
      {tab === "executions" && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="lg:col-span-2">{!execs.data?.length ? <CardBody><EmptyState icon={Play} title="No executions yet" description={w.status === "published" ? "Trigger the workflow to see runs here." : "Publish the workflow first."} /></CardBody> : (
            <ul className="divide-y divide-line">{execs.data.map((e) => (
              <li key={e.id}><button onClick={() => setExecId(e.id)} className={`flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] hover:bg-panel-2 ${execId === e.id ? "bg-panel-2" : ""}`}>
                <StatusBadge status={e.status} /><span className="capitalize text-muted">{e.trigger}</span>{e.attempt > 1 && <Badge>retry #{e.attempt - 1}</Badge>}
                <span className="ml-auto text-[12px] text-subtle">{timeAgo(e.created_at)}</span></button></li>
            ))}</ul>
          )}</Card>
          <div className="lg:col-span-3">{execId ? <ExecutionView id={execId} onRetry={(nid) => { setExecId(nid); execs.mutate(); }} /> : <EmptyState title="Select an execution" description="Inspect per-node inputs, outputs and errors." />}</div>
        </div>
      )}
      {tab === "analytics" && <WfAnalytics id={id} />}
      {tab === "trigger" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card><CardHeader title="Trigger" />
            <CardBody className="space-y-3 text-[13px]">
              <p className="capitalize">Type: <b>{w.trigger_type.replace("_", " ")}</b></p>
              {w.schedule_cron && <p>Schedule: <code className="font-mono">{w.schedule_cron}</code> (UTC) · next run {fmtDate(w.next_run_at, true)}</p>}
              {w.webhook_url && w.trigger_type === "webhook" && (<>
                <div><div className="mb-1 text-subtle">Webhook URL</div><CodeBlock>{w.webhook_url}</CodeBlock></div>
                {w.webhook_secret && <div><div className="mb-1 text-subtle">Signing secret (HMAC-SHA256 of the raw body, header <code>X-Nexora-Signature: sha256=…</code>)</div><CodeBlock>{w.webhook_secret}</CodeBlock></div>}
                <div><div className="mb-1 text-subtle">Example</div><CodeBlock>{`BODY='{"kind":"signup"}'\nSIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)\ncurl -X POST "${w.webhook_url}" -H "Content-Type: application/json" -H "X-Nexora-Signature: sha256=$SIG" -d "$BODY"`}</CodeBlock></div>
              </>)}
              {w.form_url && <div><div className="mb-1 text-subtle">Hosted form</div><a className="text-brand-text underline" href={w.form_url.replace(/^https?:\/\/[^/]+/, "")} target="_blank" rel="noreferrer">{w.form_url}</a></div>}
              {w.trigger_type === "document_uploaded" && <p className="text-subtle">Runs automatically whenever a document finishes indexing.</p>}
              {w.status !== "published" && <p className="text-subtle">Publish to activate this trigger.</p>}
            </CardBody></Card>
          <Card><CardHeader title="Published versions" description="Executions always run the version that was live when they started." />
            <CardBody>{!w.versions.length ? <p className="text-sm text-subtle">Not published yet.</p> : (
              <ul className="divide-y divide-line">{w.versions.map((ver) => (
                <li key={ver.version} className="flex items-center justify-between py-2 text-[13px]"><span>v{ver.version} {ver.version === w.published_version && <Badge tone="success">live</Badge>}</span>
                  <span className="flex items-center gap-2 text-subtle">{fmtDate(ver.created_at, true)}{editable && <Button size="sm" variant="ghost" onClick={async () => { await api(`/workflows/${id}/versions/${ver.version}/restore`, { method: "POST" }); toast.success(`Draft restored from v${ver.version}`); wf.mutate(); }}>Restore to draft</Button>}</span></li>
              ))}</ul>
            )}</CardBody></Card>
        </div>
      )}
      <Modal open={runOpen} onClose={() => setRunOpen(false)} title="Run workflow" description="Provide the trigger payload as JSON. It's available as {{trigger.*}}."
        footer={<><Button variant="ghost" onClick={() => setRunOpen(false)}>Cancel</Button><Button loading={busy === "run"} onClick={async () => {
          let input; try { input = JSON.parse(runInput || "{}"); } catch { toast.error("Invalid JSON"); return; }
          setBusy("run"); try { const e = await api<Exec>(`/workflows/${id}/run`, { body: { input } }); setRunOpen(false); setExecId(e.id); setTab("executions"); execs.mutate(); } catch (er) { toastError(er); } finally { setBusy(null); }
        }}>Run</Button></>}>
        <Textarea rows={8} className="font-mono text-[12px]" value={runInput} onChange={(e) => setRunInput(e.target.value)} aria-label="Trigger payload JSON" />
      </Modal>
    </div>
  );
}

function EditableTitle({ value, onSave, disabled }: { value: string; onSave: (v: string) => Promise<void>; disabled: boolean }) {
  const [v, setV] = useState(value);
  return <Input value={v} disabled={disabled} onChange={(e) => setV(e.target.value)} onBlur={() => v !== value && v.trim() && onSave(v.trim())} className="h-9 border-transparent bg-transparent px-0 text-xl font-semibold tracking-tight hover:border-line focus:px-2" aria-label="Workflow name" />;
}

function ExecutionView({ id, onRetry }: { id: string; onRetry: (newId: string) => void }) {
  const { can } = useAuth();
  const ex = useOrgSWR<Exec>(`/workflows/executions/${id}`, { refreshInterval: (d) => (d && ["queued", "running", "waiting"].includes(d.status) ? 1500 : 0) });
  if (!ex.data) return <LoadingBlock />;
  const e = ex.data;
  return (
    <Card><CardHeader title={<span className="flex items-center gap-2"><StatusBadge status={e.status} /> Execution · v{e.version}</span>} description={`${fmtDate(e.created_at, true)}${e.duration_ms !== null ? ` · ${e.duration_ms} ms` : ""}`}
      action={e.status === "failed" && can("workflows.run") && <Button size="sm" variant="outline" onClick={async () => { try { const n = await api<Exec>(`/workflows/executions/${id}/retry`, { method: "POST" }); toast.success("Retry queued"); onRetry(n.id); } catch (er) { toastError(er); } }}><RotateCcw className="h-4 w-4" />Retry</Button>} />
      <CardBody className="space-y-3">
        {e.error && <Callout tone="danger" title="Failed">{e.error}</Callout>}
        {e.status === "waiting_approval" && <Callout tone="warning" title="Waiting for approval">Decide in <Link href="/app/approvals" className="underline">Approvals</Link>.</Callout>}
        <details><summary className="cursor-pointer text-[12.5px] text-subtle">Trigger input</summary><CodeBlock className="mt-1">{JSON.stringify(e.input, null, 2)}</CodeBlock></details>
        <ol className="space-y-2">{e.logs?.map((l, i) => (
          <li key={i} className="rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center gap-2 text-[12.5px]"><StatusBadge status={l.status} /><span className="font-medium">{l.node_id}</span><Badge>{l.node_type}</Badge><span className="ml-auto text-subtle">{l.duration_ms} ms</span></div>
            {l.error && <p className="mt-1.5 text-[12.5px] text-danger">{l.error}</p>}
            <details className="mt-1"><summary className="cursor-pointer text-[12px] text-subtle">input / output</summary><CodeBlock className="mt-1 max-h-56">{JSON.stringify({ input: l.input, output: l.output }, null, 2)}</CodeBlock></details>
          </li>
        ))}</ol>
      </CardBody></Card>
  );
}

function WfAnalytics({ id }: { id: string }) {
  const a = useOrgSWR<{ total: number; succeeded: number; failed: number; success_rate: number | null; avg_duration_ms: number | null; daily: { date: string; succeeded: number; failed: number; other: number }[]; failing_nodes: { node_id: string; node_type: string; failures: number }[] }>(`/workflows/${id}/analytics?days=30`);
  if (!a.data) return <LoadingBlock />;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Executions (30d)" value={a.data.total} /><Stat label="Success rate" value={fmtPct(a.data.success_rate)} />
        <Stat label="Failed" value={a.data.failed} /><Stat label="Avg duration" value={a.data.avg_duration_ms !== null ? `${a.data.avg_duration_ms} ms` : "—"} />
      </div>
      <Card><CardHeader title="Daily executions" /><CardBody className="h-64">
        {a.data.daily.length ? <ResponsiveContainer><BarChart data={a.data.daily}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--subtle)" }} /><YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--subtle)" }} width={30} />
          <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }} /><Bar dataKey="succeeded" stackId="a" fill="var(--chart-2)" /><Bar dataKey="failed" stackId="a" fill="var(--chart-4)" /><Bar dataKey="other" stackId="a" fill="var(--chart-5)" /></BarChart></ResponsiveContainer>
          : <EmptyState title="No executions in this period" />}
      </CardBody></Card>
      <Card><CardHeader title="Failing nodes" />{a.data.failing_nodes.length ? <Table><thead><tr><Th>Node</Th><Th>Type</Th><Th>Failures</Th></tr></thead><tbody>{a.data.failing_nodes.map((n) => <tr key={n.node_id}><Td>{n.node_id}</Td><Td>{n.node_type}</Td><Td className="text-danger">{n.failures}</Td></tr>)}</tbody></Table> : <CardBody><p className="text-sm text-subtle">No node failures. 🎉</p></CardBody>}</Card>
    </div>
  );
}
