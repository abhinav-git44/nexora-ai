"use client";
import { use, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Download, RefreshCw, ShieldAlert, Trash2, Upload, Sparkles } from "lucide-react";
import Link from "next/link";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { fmtBytes, fmtDate } from "@/lib/utils";
import type { Doc } from "@/lib/types";
import { Badge, Button, Callout, Card, CardBody, CardHeader, ErrorState, Field, Input, LoadingBlock, Markdown, PageHeader, Select, StatusBadge, Tabs } from "@/components/ui";

type Chunk = { id: string; index: number; content: string; tokens: number; page: number | null; section: string | null; injection_risk: number };

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { can } = useAuth();
  const doc = useOrgSWR<Doc>(`/documents/${id}`, { refreshInterval: (d) => (d && ["queued", "processing"].includes(d.status) ? 2000 : 0) });
  const chunks = useOrgSWR<Chunk[]>(doc.data?.status === "indexed" ? `/documents/${id}/chunks` : null);
  const [tab, setTab] = useState<"overview" | "chunks" | "versions" | "access">("overview");
  const [strategy, setStrategy] = useState("recursive");
  const [extract, setExtract] = useState<{ fields: string; result: Record<string, unknown> | null; busy: boolean }>({ fields: "parties, effective_date, total_amount, key_obligations", result: null, busy: false });
  const verRef = useRef<HTMLInputElement>(null);

  if (doc.error) return <ErrorState error={doc.error} />;
  if (!doc.data) return <LoadingBlock rows={6} />;
  const d = doc.data;
  return (
    <div className="animate-in">
      <Link href="/app/knowledge" className="mb-3 inline-flex items-center gap-1 text-[13px] text-subtle hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />Knowledge base</Link>
      <PageHeader title={d.title} description={`${d.filename} · ${fmtBytes(d.size_bytes)} · v${d.version}${d.page_count ? ` · ${d.page_count} pages` : ""}`}
        actions={<>
          <StatusBadge status={d.status} />
          <Button variant="outline" size="sm" onClick={() => download(`/documents/${id}/download`, d.filename)}><Download className="h-4 w-4" />Download</Button>
          {can("documents.write") && <Button variant="outline" size="sm" onClick={() => verRef.current?.click()}><Upload className="h-4 w-4" />New version</Button>}
          {can("documents.write") && <Button variant="ghost" size="sm" className="text-danger" onClick={async () => { if (!confirm("Delete this document and all its versions? This cannot be undone.")) return; try { await api(`/documents/${id}`, { method: "DELETE" }); toast.success("Deleted"); router.push("/app/knowledge"); } catch (e) { toastError(e); } }}><Trash2 className="h-4 w-4" />Delete</Button>}
        </>} />
      <input ref={verRef} type="file" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); try { await api(`/documents/${id}/versions`, { form: fd }); toast.success("New version uploaded"); doc.mutate(); } catch (er) { toastError(er); } }} />
      {d.status === "failed" && <div className="mb-4"><Callout tone="danger" title="Indexing failed">{d.error}</Callout></div>}
      {d.injection_flags > 0 && <div className="mb-4"><Callout tone="warning" icon={ShieldAlert} title="Instruction-like content detected">{d.injection_flags} passage(s) contain text that resembles instructions to an AI (e.g. “ignore previous instructions”). They are neutralised before reaching any model and ranked lower in retrieval.</Callout></div>}
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Overview" }, { value: "chunks", label: "Chunks", count: d.chunk_count }, { value: "versions", label: "Versions", count: d.versions?.length }, { value: "access", label: "Access" }]} />
      {tab === "overview" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2"><CardHeader title="AI summary" />
            <CardBody>{d.summary ? <Markdown>{d.summary}</Markdown> : <p className="text-sm text-subtle">{d.status === "indexed" ? "No summary available." : "Summary appears after indexing."}</p>}</CardBody></Card>
          <Card><CardHeader title="Index details" />
            <CardBody className="space-y-2 text-[13px]">
              {[["Chunking", d.chunking_strategy], ["Embedding model", d.embedding_model || "—"], ["Chunks", d.chunk_count], ["Indexed", fmtDate(d.indexed_at, true)], ["Uploaded by", d.uploaded_by?.full_name || "—"]].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-2"><span className="text-subtle">{k}</span><span className="text-right">{v}</span></div>
              ))}
              {(d.metadata?.warnings || []).map((w: string) => <p key={w} className="text-[12px] text-warning">{w}</p>)}
              {can("documents.write") && (
                <div className="flex gap-2 border-t border-line pt-3">
                  <Select value={strategy} onChange={(e) => setStrategy(e.target.value)} aria-label="Chunking strategy"><option value="recursive">Recursive (default)</option><option value="sentence">Sentence</option><option value="fixed">Fixed window</option></Select>
                  <Button size="sm" variant="outline" onClick={async () => { await api(`/documents/${id}/reindex`, { body: { chunking_strategy: strategy } }); toast.success("Re-indexing"); doc.mutate(); }}><RefreshCw className="h-4 w-4" />Re-index</Button>
                </div>
              )}
            </CardBody></Card>
          <Card className="lg:col-span-3"><CardHeader title="Extract structured data" description="Pull named fields out of this document as JSON." />
            <CardBody className="space-y-3">
              <Field label="Fields (comma separated, snake_case)"><Input value={extract.fields} onChange={(e) => setExtract({ ...extract, fields: e.target.value })} /></Field>
              <Button size="sm" loading={extract.busy} disabled={d.status !== "indexed"} onClick={async () => {
                setExtract({ ...extract, busy: true });
                try {
                  const fields = extract.fields.split(",").map((f) => f.trim().replace(/\s+/g, "_")).filter(Boolean).map((name) => ({ name, type: /amount|total|count|price/.test(name) ? "number" : /obligations|items|risks/.test(name) ? "list" : "string" }));
                  const r = await api<{ data: Record<string, unknown> }>("/assistant/extract", { body: { document_id: id, fields } });
                  setExtract((x) => ({ ...x, result: r.data, busy: false }));
                } catch (e) { toastError(e); setExtract((x) => ({ ...x, busy: false })); }
              }}><Sparkles className="h-4 w-4" />Extract</Button>
              {extract.result && <pre className="overflow-x-auto rounded-lg bg-panel-2 p-3 font-mono text-[12px]">{JSON.stringify(extract.result, null, 2)}</pre>}
            </CardBody></Card>
        </div>
      )}
      {tab === "chunks" && (
        <div className="space-y-2">{chunks.isLoading ? <LoadingBlock /> : chunks.data?.map((c) => (
          <Card key={c.id}><CardBody className="py-3">
            <div className="mb-1.5 flex flex-wrap gap-2 text-[11.5px] text-subtle"><span className="font-mono">#{c.index}</span>{c.section && <span>{c.section}</span>}{c.page && <span>p.{c.page}</span>}<span>{c.tokens} tokens</span>
              {c.injection_risk > 0 && <Badge tone="warning">injection risk {c.injection_risk}</Badge>}</div>
            <p className="whitespace-pre-wrap text-[13px] text-muted">{c.content}</p>
          </CardBody></Card>
        ))}</div>
      )}
      {tab === "versions" && (
        <Card><CardBody className="divide-y divide-line">{d.versions?.map((v) => (
          <div key={v.version} className="flex items-center justify-between py-2.5 text-[13px]"><span><b>v{v.version}</b> · {v.filename}</span><span className="text-subtle">{fmtBytes(v.size_bytes)} · {fmtDate(v.created_at, true)}</span></div>
        ))}<p className="pt-3 text-[12px] text-subtle">Only the latest version is searchable; earlier versions are retained for audit.</p></CardBody></Card>
      )}
      {tab === "access" && <AccessEditor doc={d} onSaved={() => doc.mutate()} />}
    </div>
  );
}

function AccessEditor({ doc, onSaved }: { doc: Doc; onSaved: () => void }) {
  const [role, setRole] = useState(doc.min_role);
  const [tags, setTags] = useState(doc.tags.join(", "));
  const [busy, setBusy] = useState(false);
  return (
    <Card><CardHeader title="Access & metadata" description="Retrieval enforces these rules in the database query — the assistant can never cite a document the asker can't open." />
      <CardBody className="max-w-lg space-y-4">
        <Field label="Minimum role to read"><Select value={role} onChange={(e) => setRole(e.target.value)}><option value="viewer">Everyone (viewer+)</option><option value="member">Members+</option><option value="manager">Managers+</option><option value="admin">Admins+</option><option value="owner">Owners only</option></Select></Field>
        <Field label="Tags"><Input value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
        <Button loading={busy} onClick={async () => { setBusy(true); try { await api(`/documents/${doc.id}`, { method: "PATCH", body: { min_role: role, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) } }); toast.success("Saved"); onSaved(); } catch (e) { toastError(e); } finally { setBusy(false); } }}>Save</Button>
      </CardBody></Card>
  );
}
