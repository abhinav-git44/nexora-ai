"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { BookOpen, FileText, Search, ShieldAlert, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, fmtBytes, timeAgo } from "@/lib/utils";
import type { Doc } from "@/lib/types";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Segmented, Select, StatusBadge, Table, Td, Th } from "@/components/ui";

type Hit = { chunk_id: string; document_id: string; title: string; page: number | null; section: string | null; content: string; scores: Record<string, number>; injection_risk: number };

export default function Knowledge() {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const docs = useOrgSWR<Doc[]>(`/documents${q ? `?q=${encodeURIComponent(q)}` : ""}`, { refreshInterval: (d) => (d?.some((x) => ["queued", "processing"].includes(x.status)) ? 2500 : 0) });
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [minRole, setMinRole] = useState("viewer");
  const [tags, setTags] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"library" | "search">("library");

  async function uploadFiles(files: FileList | File[]) {
    for (const f of Array.from(files)) {
      setUploading((n) => n + 1);
      const fd = new FormData();
      fd.append("file", f); fd.append("min_role", minRole); if (tags) fd.append("tags", tags);
      try { await api("/documents", { form: fd }); toast.success(`${f.name} uploaded — indexing…`); }
      catch (e) { toastError(e); } finally { setUploading((n) => n - 1); }
    }
    docs.mutate();
  }

  return (
    <div className="animate-in">
      <PageHeader title="Knowledge base" description="Documents your assistant, agents and workflows can draw on — searched with hybrid semantic + keyword retrieval and filtered by your permissions."
        actions={<Segmented value={tab} onChange={setTab} options={[{ value: "library", label: "Library" }, { value: "search", label: "Search playground" }]} />} />
      {tab === "search" ? <SearchPlayground /> : (
        <>
          {can("documents.write") && (
            <Card className="mb-6">
              <CardBody>
                <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); uploadFiles(e.dataTransfer.files); }}
                  className={cn("flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors", drag ? "border-brand bg-brand-soft" : "border-line-strong")}>
                  <Upload className="h-6 w-6 text-subtle" />
                  <p className="mt-2 text-sm font-medium">Drop files here or <button className="text-brand-text underline" onClick={() => fileRef.current?.click()}>browse</button></p>
                  <p className="mt-1 text-[12px] text-subtle">PDF, DOCX, XLSX, CSV, TXT, Markdown · up to 20 MB each · duplicates are detected</p>
                  {uploading > 0 && <p className="mt-2 text-[12px] text-brand-text">Uploading {uploading} file(s)…</p>}
                  <input ref={fileRef} type="file" multiple className="hidden" accept=".pdf,.docx,.txt,.csv,.xlsx,.md,.markdown" onChange={(e) => e.target.files && uploadFiles(e.target.files)} />
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Who can read new uploads"><Select value={minRole} onChange={(e) => setMinRole(e.target.value)}>
                    <option value="viewer">Everyone in the organisation</option><option value="member">Members and above</option><option value="manager">Managers and above</option><option value="admin">Admins and owners</option>
                  </Select></Field>
                  <Field label="Tags (comma separated)"><Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="policy, finance" /></Field>
                </div>
              </CardBody>
            </Card>
          )}
          <Card>
            <CardHeader title="Documents" description={docs.data ? `${docs.data.length} documents` : undefined}
              action={<div className="relative w-56"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-subtle" /><Input className="pl-8" placeholder="Filter by title" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter documents" /></div>} />
            {docs.error ? <CardBody><ErrorState error={docs.error} retry={() => docs.mutate()} /></CardBody> : docs.isLoading ? <CardBody><LoadingBlock /></CardBody> :
              !docs.data?.length ? <CardBody><EmptyState icon={BookOpen} title="No documents yet" description="Upload policies, SOPs, contracts or reports to ground AI answers in your own knowledge." /></CardBody> : (
                <Table>
                  <thead><tr><Th>Title</Th><Th>Status</Th><Th className="hidden md:table-cell">Access</Th><Th className="hidden md:table-cell">Chunks</Th><Th className="hidden lg:table-cell">Size</Th><Th className="hidden sm:table-cell">Uploaded</Th></tr></thead>
                  <tbody>{docs.data.map((d) => (
                    <tr key={d.id} className="hover:bg-panel-2">
                      <Td><Link href={`/app/knowledge/${d.id}`} className="flex items-center gap-2 font-medium hover:text-brand-text">
                        <FileText className="h-4 w-4 shrink-0 text-subtle" /><span className="truncate">{d.title}</span><Badge>{d.file_type}</Badge>
                        {d.injection_flags > 0 && <span title="Contains instruction-like text that was neutralised"><ShieldAlert className="h-4 w-4 text-warning" /></span>}
                      </Link>{d.tags.length > 0 && <div className="mt-1 flex gap-1">{d.tags.map((t) => <Badge key={t} tone="brand">{t}</Badge>)}</div>}</Td>
                      <Td><StatusBadge status={d.status} />{d.error && <div className="mt-1 max-w-xs truncate text-[11.5px] text-danger" title={d.error}>{d.error}</div>}</Td>
                      <Td className="hidden capitalize md:table-cell">{d.min_role === "viewer" ? "Everyone" : `${d.min_role}+`}</Td>
                      <Td className="hidden tabular-nums md:table-cell">{d.chunk_count}</Td>
                      <Td className="hidden text-subtle lg:table-cell">{fmtBytes(d.size_bytes)}</Td>
                      <Td className="hidden text-subtle sm:table-cell">{timeAgo(d.created_at)}</Td>
                    </tr>
                  ))}</tbody>
                </Table>
              )}
          </Card>
        </>
      )}
    </div>
  );
}

function SearchPlayground() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"hybrid" | "vector" | "keyword">("hybrid");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHeader title="Retrieval playground" description="Inspect exactly what the assistant would retrieve for a question, with per-stage scores." />
      <CardBody>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={async (e) => { e.preventDefault(); setBusy(true); try { setHits(await api<Hit[]>("/documents/search", { body: { query, mode, top_k: 8 } })); } catch (er) { toastError(er); } finally { setBusy(false); } }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. who approves expenses above 5000 USD" required aria-label="Search query" />
          <Select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className="sm:w-40" aria-label="Retrieval mode"><option value="hybrid">Hybrid (RRF)</option><option value="vector">Vector only</option><option value="keyword">Keyword only</option></Select>
          <Button type="submit" loading={busy}><Search className="h-4 w-4" />Search</Button>
        </form>
        <div className="mt-4 space-y-3">
          {hits?.length === 0 && <EmptyState title="No matching passages" description="Nothing you have access to matches this query." />}
          {hits?.map((h, i) => (
            <div key={h.chunk_id} className="rounded-xl border border-line p-3.5">
              <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
                <span className="font-mono text-subtle">#{i + 1}</span>
                <Link href={`/app/knowledge/${h.document_id}`} className="font-medium hover:text-brand-text">{h.title}</Link>
                {h.section && <span className="text-subtle">· {h.section}</span>}{h.page && <span className="text-subtle">· p.{h.page}</span>}
                <span className="flex-1" />
                {Object.entries(h.scores).map(([k, v]) => <Badge key={k} tone={k === "rerank" ? "brand" : "neutral"}>{k} {v.toFixed(3)}</Badge>)}
                {h.injection_risk > 0 && <Badge tone="warning">injection risk {h.injection_risk}</Badge>}
              </div>
              <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-[13px] text-muted">{h.content}</p>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}
