"use client";
import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Download, FileBarChart, Play, Sparkles, Trash2, Code2 } from "lucide-react";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { fmtNumber, timeAgo } from "@/lib/utils";
import { ResultChart } from "@/components/app/charts";
import { Badge, Button, Callout, Card, CardBody, CardHeader, CodeBlock, EmptyState, Input, LoadingBlock, Markdown, Modal, PageHeader, Segmented, Table, Tabs, Td, Textarea, Th } from "@/components/ui";

type Col = { name: string; label: string; type: string; kind: string };
type Ds = { id: string; name: string; filename: string; row_count: number; columns: Col[]; profile: Record<string, any>; recommendations: { severity: string; column: string | null; issue: string; suggestion: string }[] };
type QRes = { id: string; question: string; sql: string; status: string; error: string | null; explanation: string; columns: string[]; rows: unknown[][]; row_count: number; chart: { type: string; x: string; y: string } | null; demo?: boolean; latency_ms?: number };

const SUGGESTED = ["Which customers generated the most revenue?", "What is the monthly revenue trend?", "Which category has the highest growth?", "Top 5 products by revenue"];

export default function DatasetDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { can } = useAuth();
  const ds = useOrgSWR<Ds>(`/datasets/${id}`);
  const history = useOrgSWR<{ id: string; question: string; status: string; row_count: number; created_at: string }[]>(`/datasets/${id}/queries`);
  const [q, setQ] = useState("");
  const [res, setRes] = useState<QRes | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"chart" | "table">("chart");
  const [tab, setTab] = useState<"ask" | "profile" | "quality">("ask");
  const [sqlEdit, setSqlEdit] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [pbi, setPbi] = useState<Record<string, string> | null>(null);

  const ask = async (question: string) => {
    setBusy(true); setQ(question);
    try { const r = await api<QRes>(`/datasets/${id}/query`, { body: { question } }); setRes(r); setView(r.chart ? "chart" : "table"); history.mutate(); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  if (!ds.data) return <LoadingBlock rows={6} />;
  const d = ds.data;
  const rowsAsObjects = res ? res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]]))) : [];
  return (
    <div className="animate-in">
      <Link href="/app/data" className="mb-3 inline-flex items-center gap-1 text-[13px] text-subtle hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />Datasets</Link>
      <PageHeader title={d.name} description={`${fmtNumber(d.row_count)} rows · ${d.columns.length} columns · ${d.filename}`}
        actions={<>
          <Button size="sm" variant="outline" onClick={async () => { setReport(""); try { setReport((await api<{ report: string }>(`/datasets/${id}/report`, { method: "POST" })).report); } catch (e) { toastError(e); setReport(null); } }}><FileBarChart className="h-4 w-4" />Generate report</Button>
          <Button size="sm" variant="outline" onClick={async () => setPbi(await api(`/datasets/${id}/powerbi`))}>Power BI</Button>
          {can("datasets.write") && <Button size="sm" variant="ghost" className="text-danger" onClick={async () => { if (!confirm("Delete dataset?")) return; await api(`/datasets/${id}`, { method: "DELETE" }); router.push("/app/data"); }}><Trash2 className="h-4 w-4" /></Button>}
        </>} />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: "ask", label: "Ask" }, { value: "profile", label: "Schema & profile" }, { value: "quality", label: "Data quality", count: d.recommendations.length }]} />
      {tab === "ask" && (
        <div className="grid gap-6 xl:grid-cols-4">
          <div className="space-y-4 xl:col-span-3">
            <Card><CardBody>
              <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask(q.trim()); }}>
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question about this data…" aria-label="Question" />
                <Button type="submit" loading={busy}><Sparkles className="h-4 w-4" />Ask</Button>
              </form>
              <div className="mt-3 flex flex-wrap gap-1.5">{SUGGESTED.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-2.5 py-1 text-[12px] text-muted hover:border-brand hover:text-fg">{s}</button>)}</div>
            </CardBody></Card>
            {res && (
              <Card>
                <CardHeader title={res.question} description={res.explanation} action={<div className="flex items-center gap-2">{res.demo && <Badge tone="warning">Demo NL→SQL engine</Badge>}<Badge tone={res.status === "succeeded" ? "success" : "danger"}>{res.status}</Badge></div>} />
                <CardBody className="space-y-4">
                  <div>
                    <div className="mb-1 flex items-center justify-between text-[12px] text-subtle"><span>Validated SQL (executed read-only)</span>
                      <button className="inline-flex items-center gap-1 text-brand-text" onClick={() => setSqlEdit(res.sql)}><Code2 className="h-3.5 w-3.5" />Edit SQL</button></div>
                    <CodeBlock>{res.sql}</CodeBlock>
                  </div>
                  {res.error && <Callout tone="danger" title={res.status === "rejected" ? "Rejected by the SQL safety guard" : "Query failed"}>{res.error}</Callout>}
                  {res.status === "succeeded" && (<>
                    <div className="flex items-center justify-between"><span className="text-[12.5px] text-subtle">{res.row_count} rows{res.latency_ms ? ` · ${res.latency_ms} ms` : ""}</span>
                      <div className="flex gap-2">{res.chart && <Segmented value={view} onChange={setView} options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />}
                        <Button size="sm" variant="outline" onClick={() => download(`/datasets/queries/${res.id}/export?format=csv`, "results.csv")}><Download className="h-4 w-4" />CSV</Button>
                        <Button size="sm" variant="outline" onClick={() => download(`/datasets/queries/${res.id}/export?format=xlsx`, "results.xlsx")}><Download className="h-4 w-4" />XLSX</Button></div></div>
                    {view === "chart" && res.chart ? <div className="h-72"><ResultChart type={res.chart.type} data={rowsAsObjects} x={res.chart.x} y={res.chart.y} /></div> : (
                      <Table className="max-h-96 overflow-y-auto rounded-lg border border-line"><thead><tr>{res.columns.map((c) => <Th key={c}>{c}</Th>)}</tr></thead>
                        <tbody>{res.rows.slice(0, 200).map((r, i) => <tr key={i}>{r.map((v, j) => <Td key={j} className="tabular-nums">{typeof v === "number" ? fmtNumber(v) : String(v ?? "—")}</Td>)}</tr>)}</tbody></Table>
                    )}
                  </>)}
                </CardBody>
              </Card>
            )}
            {!res && !busy && <EmptyState icon={Play} title="Ask your first question" description="Try one of the suggestions above. The SQL is shown so analysts can verify or refine it." />}
          </div>
          <Card className="self-start"><CardHeader title="History" />
            <CardBody className="space-y-1">{history.data?.length ? history.data.slice(0, 15).map((h) => (
              <button key={h.id} onClick={() => ask(h.question === "(manual SQL)" ? q : h.question)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-[12.5px] text-muted hover:bg-panel-2" title={h.question}>
                <span className={h.status === "succeeded" ? "text-success" : "text-danger"}>●</span> {h.question} <span className="text-subtle">· {timeAgo(h.created_at)}</span></button>
            )) : <p className="text-[12.5px] text-subtle">No queries yet.</p>}</CardBody></Card>
        </div>
      )}
      {tab === "profile" && (
        <Card><Table><thead><tr><Th>Column</Th><Th>Type</Th><Th>Role</Th><Th>Missing</Th><Th>Distinct</Th><Th className="hidden md:table-cell">Range / top values</Th></tr></thead>
          <tbody>{d.columns.map((c) => { const p = d.profile[c.name] || {}; return (
            <tr key={c.name}><Td><span className="font-mono text-[12.5px]">{c.name}</span>{c.label !== c.name && <div className="text-[11.5px] text-subtle">{c.label}</div>}</Td><Td><Badge>{c.type}</Badge></Td>
              <Td><Badge tone={c.kind === "measure" ? "brand" : c.kind === "pii" ? "danger" : "neutral"}>{c.kind}</Badge></Td><Td className={p.null_pct > 20 ? "text-warning" : ""}>{p.null_pct}%</Td><Td>{fmtNumber(p.distinct)}</Td>
              <Td className="hidden max-w-sm truncate text-[12px] text-subtle md:table-cell">{p.min !== undefined ? `${p.min} → ${p.max}${p.mean !== undefined ? ` · mean ${fmtNumber(p.mean)}` : ""}` : (p.top_values || []).slice(0, 4).map((t: [string, number]) => `${t[0]} (${t[1]})`).join(", ")}</Td></tr>); })}</tbody></Table></Card>
      )}
      {tab === "quality" && (
        <div className="space-y-2">{d.recommendations.length === 0 ? <EmptyState title="No data-quality issues detected" /> : d.recommendations.map((r, i) => (
          <Callout key={i} tone={r.severity === "high" ? "danger" : r.severity === "medium" ? "warning" : "info"} title={`${r.column ? `${r.column}: ` : ""}${r.issue}`}>{r.suggestion}</Callout>
        ))}</div>
      )}
      <Modal open={sqlEdit !== null} onClose={() => setSqlEdit(null)} title="Edit SQL" description="Query the table named data. The same safety guard applies: SELECT only, known columns, 1,000 row limit, 5s timeout." wide
        footer={<><Button variant="ghost" onClick={() => setSqlEdit(null)}>Cancel</Button><Button onClick={async () => {
          try { const r = await api<QRes>(`/datasets/${id}/sql`, { body: { sql: sqlEdit } }); setRes({ ...r, question: "Custom SQL", explanation: "Edited by analyst", error: null }); setSqlEdit(null); } catch (e) { toastError(e); }
        }}>Run</Button></>}>
        <Textarea rows={8} className="font-mono text-[12.5px]" value={sqlEdit || ""} onChange={(e) => setSqlEdit(e.target.value)} aria-label="SQL" />
      </Modal>
      <Modal open={report !== null} onClose={() => setReport(null)} title="Data analysis report" wide footer={report ? <Button variant="outline" onClick={() => { navigator.clipboard.writeText(report); toast.success("Copied"); }}>Copy</Button> : undefined}>
        {report === "" ? <LoadingBlock rows={5} /> : <Markdown>{report || ""}</Markdown>}
      </Modal>
      <Modal open={!!pbi} onClose={() => setPbi(null)} title="Connect Power BI" description="Live dashboards via the PostgreSQL connector with a SELECT-only role.">
        <dl className="space-y-2 text-[13px]">{pbi && Object.entries(pbi).map(([k, v]) => <div key={k}><dt className="capitalize text-subtle">{k}</dt><dd className="font-mono text-[12px]">{v}</dd></div>)}</dl>
      </Modal>
    </div>
  );
}
