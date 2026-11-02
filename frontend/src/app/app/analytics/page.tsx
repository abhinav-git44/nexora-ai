"use client";
import { useState } from "react";
import { Download, Info } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { download } from "@/lib/api";
import { useOrgSWR } from "@/lib/hooks";
import { fmtNumber, fmtPct, fmtUSD, titleCase } from "@/lib/utils";
import { tooltipStyle } from "@/components/app/charts";
import { Badge, Button, Callout, Card, CardBody, CardHeader, EmptyState, LoadingBlock, Modal, PageHeader, Progress, Segmented, Select, Stat, Table, Td, Th } from "@/components/ui";

const axis = { tick: { fontSize: 11, fill: "var(--subtle)" }, axisLine: { stroke: "var(--line)" }, tickLine: false };
const fmtBucket = (b: string, g: string) => { const d = new Date(b); return g === "month" ? d.toLocaleDateString(undefined, { month: "short", year: "2-digit" }) : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); };

export default function Analytics() {
  const [days, setDays] = useState("30");
  const [gran, setGran] = useState<"day" | "week" | "month">("day");
  const dash = useOrgSWR<any>(`/analytics/dashboard?days=${days}`);
  const ts = useOrgSWR<{ series: any[] }>(`/analytics/timeseries?days=${days}&granularity=${gran}`);
  const ai = useOrgSWR<any>(`/analytics/ai-usage?days=${days}`);
  const [drill, setDrill] = useState<{ metric: string; group: string } | null>(null);
  const k = dash.data?.kpis;
  const series = (ts.data?.series || []).map((r) => ({ ...r, label: fmtBucket(r.bucket, gran) }));
  return (
    <div className="animate-in">
      <PageHeader title="Analytics" description="Executive view of adoption, AI usage, automation reliability and outcomes. All figures are computed from recorded activity; estimates are labelled."
        actions={<>
          <Select value={days} onChange={(e) => setDays(e.target.value)} className="w-44" aria-label="Time range">{[["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["365", "Last 12 months"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
          <Button variant="outline" size="sm" onClick={() => download(`/analytics/export?days=${days}`, `nexora-analytics-${days}d.csv`)}><Download className="h-4 w-4" />Export CSV</Button>
        </>} />
      {!k ? <LoadingBlock rows={6} /> : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="AI-assisted outcomes" value={fmtNumber(k.outcomes.value)} delta={k.outcomes.delta} sub="vs previous period" onClick={() => setDrill({ metric: "events", group: "event" })} />
            <Stat label="Active users" value={`${fmtNumber(k.active_users.value)} / ${dash.data.totals.total_users}`} delta={k.active_users.delta} />
            <Stat label="AI interactions" value={fmtNumber(k.ai_interactions.value)} delta={k.ai_interactions.delta} sub={`${fmtNumber(k.ai_requests.value)} model calls`} onClick={() => setDrill({ metric: "ai_requests", group: "feature" })} />
            <Stat label="AI spend" value={fmtUSD(k.ai_cost_usd.value)} delta={k.ai_cost_usd.delta} sub={ai.data?.cost_per_outcome_usd != null ? `${fmtUSD(ai.data.cost_per_outcome_usd, 4)} / outcome` : undefined} onClick={() => setDrill({ metric: "ai_cost", group: "model" })} />
            <Stat label="Documents processed" value={fmtNumber(k.documents_processed.value)} delta={k.documents_processed.delta} />
            <Stat label="Agent runs" value={fmtNumber(k.agents_executed.value)} delta={k.agents_executed.delta} />
            <Stat label="Workflow success" value={fmtPct(dash.data.totals.workflow_success_rate)} sub={`${k.workflows_succeeded.value} ok · ${k.workflows_failed.value} failed`} />
            <Stat label="Estimated time saved" value={`${dash.data.estimates.time_saved_hours.value} h`} estimate sub="see method below" />
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2"><CardHeader title="Activity trend" action={<Segmented value={gran} onChange={setGran} options={[{ value: "day", label: "Daily" }, { value: "week", label: "Weekly" }, { value: "month", label: "Monthly" }]} />} />
              <CardBody className="h-72">{series.length ? (
                <ResponsiveContainer><AreaChart data={series} margin={{ left: 0, right: 8, top: 8 }}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="label" {...axis} /><YAxis {...axis} allowDecimals={false} width={32} />
                  <Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
                  <Area type="monotone" dataKey="ai_query_completed" name="AI interactions" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.15} />
                  <Area type="monotone" dataKey="outcome_achieved" name="Outcomes" stroke="var(--chart-2)" fill="var(--chart-2)" fillOpacity={0.15} />
                  <Area type="monotone" dataKey="task_completed" name="Tasks done" stroke="var(--chart-3)" fill="var(--chart-3)" fillOpacity={0.1} /></AreaChart></ResponsiveContainer>
              ) : <EmptyState title="No activity yet" />}</CardBody></Card>
            <Card><CardHeader title="Feature adoption" description="Share of active users who used each module." />
              <CardBody className="space-y-3">{Object.entries(dash.data.feature_adoption as Record<string, { users: number; rate: number }>).map(([f, v]) => (
                <div key={f}><div className="mb-1 flex justify-between text-[12.5px]"><span className="capitalize">{f}</span><span className="tabular-nums text-subtle">{fmtPct(v.rate)} · {v.users}</span></div><Progress value={v.rate * 100} max={100} /></div>
              ))}</CardBody></Card>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card><CardHeader title="Workflow executions" /><CardBody className="h-64">
              <ResponsiveContainer><BarChart data={series}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="label" {...axis} /><YAxis {...axis} allowDecimals={false} width={32} /><Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--panel-2)" }} />
                <Bar dataKey="workflow_completed" name="Succeeded" stackId="w" fill="var(--chart-2)" /><Bar dataKey="workflow_failed" name="Failed" stackId="w" fill="var(--chart-4)" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></CardBody></Card>
            <Card><CardHeader title="Tokens & AI spend" /><CardBody className="h-64">
              <ResponsiveContainer><AreaChart data={series}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="label" {...axis} /><YAxis yAxisId="t" {...axis} width={44} /><YAxis yAxisId="c" orientation="right" {...axis} width={44} tickFormatter={(v) => `$${v}`} /><Tooltip contentStyle={tooltipStyle} />
                <Area yAxisId="t" dataKey="tokens" name="Tokens" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.12} /><Area yAxisId="c" dataKey="ai_cost_usd" name="Cost (USD)" stroke="var(--chart-3)" fill="var(--chart-3)" fillOpacity={0.12} /></AreaChart></ResponsiveContainer></CardBody></Card>
          </div>
          <Card><CardHeader title="AI usage by model" description="Measured from every gateway call, including failures and fallbacks." />
            {ai.data?.by_model.length ? (<Table><thead><tr><Th>Provider / model</Th><Th>Requests</Th><Th>Input</Th><Th>Output</Th><Th>Cached</Th><Th>Cost</Th><Th>Avg latency</Th><Th>Errors</Th><Th>Fallbacks</Th></tr></thead>
              <tbody>{ai.data.by_model.map((m: any) => <tr key={m.model}><Td>{m.provider} / <span className="font-mono text-[12px]">{m.model}</span>{m.provider === "demo" && <Badge tone="warning" className="ml-1.5">demo</Badge>}</Td><Td>{fmtNumber(m.requests)}</Td><Td>{fmtNumber(m.input_tokens)}</Td><Td>{fmtNumber(m.output_tokens)}</Td><Td>{fmtNumber(m.cached_tokens)}</Td><Td>{fmtUSD(m.cost_usd, 4)}</Td><Td>{m.avg_latency_ms} ms</Td><Td className={m.errors ? "text-danger" : ""}>{m.errors}</Td><Td>{m.fallbacks}</Td></tr>)}</tbody></Table>)
              : <CardBody><EmptyState title="No AI calls in this period" /></CardBody>}</Card>
          <Card><CardHeader title="Outcomes by type" description="The North Star counts completed, user-valuable actions — not raw AI responses." />
            <CardBody>{Object.keys(dash.data.outcomes_by_type).length ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(dash.data.outcomes_by_type as Record<string, number>).map(([t, n]) => (
                <div key={t} className="rounded-lg border border-line p-3"><div className="text-[12px] text-subtle">{titleCase(t)}</div><div className="text-lg font-semibold tabular-nums">{n}</div>
                  <div className="text-[11.5px] text-subtle">≈ {dash.data.estimates.time_saved_hours.assumptions_minutes[t] ?? 0} min each (assumed)</div></div>
              ))}</div>) : <p className="text-sm text-subtle">No outcomes recorded in this period.</p>}
              <div className="mt-4"><Callout tone="warning" icon={Info} title="How 'time saved' is estimated">{dash.data.estimates.time_saved_hours.method}. Per-outcome minutes are planning assumptions (see ANALYTICS_FRAMEWORK.md), not measurements. Validate with time-and-motion sampling before using them in external claims.</Callout></div>
            </CardBody></Card>
        </div>
      )}
      <Modal open={!!drill} onClose={() => setDrill(null)} title="Drill-down" wide>{drill && <Drill {...drill} days={days} onGroup={(group) => setDrill({ ...drill, group })} />}</Modal>
    </div>
  );
}

function Drill({ metric, group, days, onGroup }: { metric: string; group: string; days: string; onGroup: (g: string) => void }) {
  const d = useOrgSWR<{ rows: { key: string; value: number; label?: string }[] }>(`/analytics/drilldown?metric=${metric}&group=${group}&days=${days}`);
  const groups = metric === "events" ? ["event", "user"] : ["model", "feature", "provider", "task_type", "user"];
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-[13px]"><span className="text-subtle">{titleCase(metric)} by</span><Select className="w-40" value={group} onChange={(e) => onGroup(e.target.value)} aria-label="Group by">{groups.map((g) => <option key={g} value={g}>{titleCase(g)}</option>)}</Select></div>
      {!d.data ? <LoadingBlock /> : <Table><thead><tr><Th>{titleCase(group)}</Th><Th className="text-right">Value</Th></tr></thead><tbody>{d.data.rows.map((r) => <tr key={r.key}><Td>{r.label || r.key}</Td><Td className="text-right tabular-nums">{metric === "ai_cost" ? fmtUSD(r.value, 4) : fmtNumber(r.value)}</Td></tr>)}</tbody></Table>}
    </div>
  );
}
