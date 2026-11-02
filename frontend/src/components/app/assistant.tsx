"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { BookOpen, Copy, Download, FileUp, ListChecks, MessageSquarePlus, MoreHorizontal, Pencil, Send, Share2, Sparkles, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, timeAgo, fmtUSD } from "@/lib/utils";
import type { Citation, Conversation, Member, Message } from "@/lib/types";
import { Badge, Button, Checkbox, EmptyState, LoadingBlock, Markdown, Menu, MenuItem, Modal, Select, Spinner, Switch, Textarea, Input } from "@/components/ui";

const STARTERS: Record<string, string[]> = {
  default: ["Summarise our expense approval rules", "What are the steps in customer onboarding?", "Draft a weekly operations update template", "How quickly must Severity 1 incidents be acknowledged?"],
};

function CitationChip({ c }: { c: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button onClick={() => setOpen((o) => !o)} className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11.5px]", c.verified === false ? "border-warning/40 text-warning" : "border-line text-muted hover:border-brand hover:text-brand-text")}
        aria-expanded={open} title={c.verified === false ? "Low lexical support — verify against the source" : "Source"}>
        <BookOpen className="h-3 w-3" />[{c.n}] {c.title}{c.page ? ` · p.${c.page}` : ""}
      </button>
      {open && (
        <span className="animate-in absolute bottom-full left-0 z-30 mb-1.5 block w-80 max-w-[80vw] rounded-xl border border-line bg-panel p-3 text-[12.5px] text-muted shadow-pop">
          {c.section && <span className="mb-1 block font-medium text-fg">{c.section}</span>}
          <span className="block">{c.snippet}{c.snippet.length >= 300 ? "…" : ""}</span>
          <Link href={`/app/knowledge/${c.document_id}`} className="mt-2 block text-brand-text">Open document →</Link>
        </span>
      )}
    </span>
  );
}

function MessageView({ m, onFeedback }: { m: Message; onFeedback: (v: number) => void }) {
  if (m.role === "user") {
    return <div className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[14px] text-brand-fg">{m.content}</div></div>;
  }
  const meta = m.meta || {};
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-soft"><Sparkles className="h-4 w-4 text-brand" /></div>
      <div className="min-w-0 flex-1">
        <Markdown>{m.content}</Markdown>
        {m.citations?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{m.citations.map((c) => <CitationChip key={c.n} c={c} />)}</div>}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-subtle">
          {meta.demo ? <Badge tone="warning">Demo engine</Badge> : <span>{meta.model}</span>}
          {meta.fallback_used && <Badge tone="info">fallback</Badge>}
          {meta.refusal && <Badge tone="danger">declined</Badge>}
          <span>{(meta.input_tokens ?? 0) + (meta.output_tokens ?? 0)} tokens</span>
          {meta.cost_usd !== undefined && <span>{fmtUSD(meta.cost_usd, 4)}</span>}
          {meta.latency_ms !== undefined && <span>{(meta.latency_ms / 1000).toFixed(1)}s</span>}
          <span className="flex-1" />
          <button className="rounded p-1 hover:bg-panel-2" aria-label="Copy answer" onClick={() => { navigator.clipboard.writeText(m.content); toast.success("Copied"); }}><Copy className="h-3.5 w-3.5" /></button>
          <button className={cn("rounded p-1 hover:bg-panel-2", m.feedback === 1 && "text-success")} aria-label="Helpful" onClick={() => onFeedback(m.feedback === 1 ? 0 : 1)}><ThumbsUp className="h-3.5 w-3.5" /></button>
          <button className={cn("rounded p-1 hover:bg-panel-2", m.feedback === -1 && "text-danger")} aria-label="Not helpful" onClick={() => onFeedback(m.feedback === -1 ? 0 : -1)}><ThumbsDown className="h-3.5 w-3.5" /></button>
        </div>
      </div>
    </div>
  );
}

export function AssistantView({ id }: { id?: string }) {
  const router = useRouter();
  const { can, user } = useAuth();
  const list = useOrgSWR<Conversation[]>("/conversations");
  const conv = useOrgSWR<Conversation & { messages: Message[]; shares: { user: Member["user"]; permission: string }[] }>(id ? `/conversations/${id}` : null);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("auto");
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [attached, setAttached] = useState<{ id: string; title: string }[]>([]);
  const [shareOpen, setShareOpen] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const readOnly = !!conv.data && !conv.data.is_owner;

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conv.data?.messages.length, pending]);

  async function ensureConversation(): Promise<string> {
    if (id) return id;
    const c = await api<Conversation>("/conversations", { body: {} });
    list.mutate();
    return c.id;
  }

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setSending(true); setPending(content); setInput("");
    try {
      const cid = await ensureConversation();
      await api(`/conversations/${cid}/messages`, { body: { content, mode, document_ids: attached.length ? attached.map((a) => a.id) : undefined } });
      setAttached([]);
      if (!id) router.push(`/app/assistant/${cid}`);
      else await conv.mutate();
      list.mutate();
    } catch (e) { toastError(e); setInput(content); } finally { setSending(false); setPending(null); }
  }

  async function upload(f: File) {
    try {
      const cid = await ensureConversation();
      const fd = new FormData(); fd.append("file", f);
      const d = await api<{ id: string; title: string }>(`/conversations/${cid}/attachments`, { form: fd });
      setAttached((a) => [...a, { id: d.id, title: d.title }]);
      toast.success(`${f.name} uploaded — indexing in the background`);
      if (!id) router.push(`/app/assistant/${cid}`);
    } catch (e) { toastError(e); }
  }

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100vh-3.5rem)] sm:-mx-6 lg:-mx-8">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line md:flex">
        <div className="p-3"><Button className="w-full" variant="outline" onClick={() => router.push("/app/assistant")}><MessageSquarePlus className="h-4 w-4" />New conversation</Button></div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {list.isLoading && <LoadingBlock rows={4} />}
          {list.data?.map((c) => (
            <Link key={c.id} href={`/app/assistant/${c.id}`} className={cn("block truncate rounded-lg px-2.5 py-2 text-[13px]", c.id === id ? "bg-panel-2 font-medium text-fg" : "text-muted hover:bg-panel-2")}>
              {c.title}{!c.is_owner && <span className="ml-1 text-[11px] text-subtle">(shared)</span>}
              <span className="block text-[11px] font-normal text-subtle">{timeAgo(c.updated_at)}</span>
            </Link>
          ))}
        </div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-2 border-b border-line px-4">
          {renaming !== null ? (
            <form className="flex flex-1 gap-2" onSubmit={async (e) => { e.preventDefault(); await api(`/conversations/${id}`, { method: "PATCH", body: { title: renaming } }); setRenaming(null); conv.mutate(); list.mutate(); }}>
              <Input value={renaming} onChange={(e) => setRenaming(e.target.value)} autoFocus className="h-8" /><Button size="sm" type="submit">Save</Button>
            </form>
          ) : <h1 className="flex-1 truncate text-[14px] font-medium">{conv.data?.title || "New conversation"}</h1>}
          {readOnly && <Badge>Shared with you · read-only</Badge>}
          {id && conv.data && (
            <Menu trigger={({ toggle }) => <Button variant="ghost" size="icon" onClick={toggle} aria-label="Conversation options"><MoreHorizontal className="h-4 w-4" /></Button>}>
              {!readOnly && <MenuItem icon={Pencil} onClick={() => setRenaming(conv.data!.title)}>Rename</MenuItem>}
              {!readOnly && <MenuItem icon={Share2} onClick={() => setShareOpen(true)}>Share with team</MenuItem>}
              <MenuItem icon={ListChecks} onClick={() => setTasksOpen(true)}>Suggest tasks</MenuItem>
              <MenuItem icon={Download} onClick={() => download(`/conversations/${id}/export?format=md`, `${conv.data!.title}.md`)}>Export Markdown</MenuItem>
              <MenuItem icon={Download} onClick={() => download(`/conversations/${id}/export?format=json`, `${conv.data!.title}.json`)}>Export JSON</MenuItem>
              {!readOnly && <MenuItem icon={Trash2} danger onClick={async () => { if (!confirm("Delete this conversation?")) return; await api(`/conversations/${id}`, { method: "DELETE" }); list.mutate(); router.push("/app/assistant"); }}>Delete</MenuItem>}
            </Menu>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {id && conv.isLoading && <LoadingBlock rows={3} />}
            {!id || conv.data?.messages.length === 0 ? (
              <div className="pt-10 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft"><Sparkles className="h-6 w-6 text-brand" /></div>
                <h2 className="text-lg font-semibold">How can I help, {user?.full_name.split(" ")[0]}?</h2>
                <p className="mt-1 text-sm text-subtle">Answers are grounded in the knowledge you can access, with sources.</p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                  {STARTERS.default.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-line bg-panel p-3 text-left text-[13px] text-muted hover:border-brand hover:text-fg">{s}</button>)}
                </div>
              </div>
            ) : conv.data?.messages.map((m) => (
              <MessageView key={m.id} m={m} onFeedback={async (v) => { await api(`/conversations/messages/${m.id}/feedback`, { body: { value: v } }); conv.mutate(); }} />
            ))}
            {pending && (
              <>
                <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[14px] text-brand-fg opacity-80">{pending}</div></div>
                <div className="flex items-center gap-2 text-[13px] text-subtle"><Spinner />Searching knowledge and drafting an answer…</div>
              </>
            )}
            <div ref={endRef} />
          </div>
        </div>
        {!readOnly && can("chat.use") && (
          <div className="border-t border-line bg-canvas p-3">
            <div className="mx-auto max-w-3xl">
              {attached.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{attached.map((a) => <Badge key={a.id} tone="brand">📎 {a.title} <button onClick={() => setAttached(attached.filter((x) => x.id !== a.id))} aria-label="Remove attachment">×</button></Badge>)}<span className="text-[11.5px] text-subtle">Answers will be limited to attached files.</span></div>}
              <div className="rounded-2xl border border-line-strong bg-panel p-2 shadow-card focus-within:border-brand">
                <Textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about your business…" aria-label="Message"
                  className="min-h-[52px] border-0 bg-transparent focus:ring-0" rows={2}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
                <div className="flex flex-wrap items-center gap-2 px-1">
                  <input ref={fileRef} type="file" className="hidden" accept=".pdf,.docx,.txt,.csv,.xlsx,.md" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
                  <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()} disabled={!can("documents.write")}><FileUp className="h-4 w-4" />Attach</Button>
                  <Select value={mode} onChange={(e) => setMode(e.target.value)} className="h-8 w-auto text-[12.5px]" aria-label="Response mode">
                    <option value="auto">Answer</option><option value="analysis">Deep analysis</option><option value="report">Business report</option>
                  </Select>
                  {conv.data && <Switch checked={conv.data.use_knowledge} label="Use knowledge" onChange={async (v) => { await api(`/conversations/${id}`, { method: "PATCH", body: { use_knowledge: v } }); conv.mutate(); }} />}
                  <span className="flex-1" />
                  <Button size="sm" onClick={() => send()} loading={sending} disabled={!input.trim()} aria-label="Send"><Send className="h-4 w-4" /></Button>
                </div>
              </div>
              <p className="mt-1.5 text-center text-[11px] text-subtle">AI can make mistakes. Check important answers against the cited sources.</p>
            </div>
          </div>
        )}
      </section>
      {id && <ShareModal open={shareOpen} onClose={() => setShareOpen(false)} convId={id} onDone={() => conv.mutate()} />}
      {id && <SuggestTasksModal open={tasksOpen} onClose={() => setTasksOpen(false)} convId={id} />}
    </div>
  );
}

function ShareModal({ open, onClose, convId, onDone }: { open: boolean; onClose: () => void; convId: string; onDone: () => void }) {
  const { user } = useAuth();
  const members = useOrgSWR<Member[]>(open ? "/orgs/current/members" : null);
  const [sel, setSel] = useState<string[]>([]);
  return (
    <Modal open={open} onClose={onClose} title="Share conversation" description="Teammates get read-only access. Shared answers only include sources they could already see in the conversation."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={!sel.length} onClick={async () => { try { await api(`/conversations/${convId}/share`, { body: { user_ids: sel } }); toast.success("Shared"); onDone(); onClose(); } catch (e) { toastError(e); } }}>Share</Button></>}>
      <div className="space-y-2">
        {members.data?.filter((m) => m.user.id !== user?.id && m.status === "active").map((m) => (
          <div key={m.id}><Checkbox checked={sel.includes(m.user.id)} onChange={(v) => setSel(v ? [...sel, m.user.id] : sel.filter((x) => x !== m.user.id))} label={<span>{m.user.full_name} <span className="text-subtle">· {m.role}</span></span>} /></div>
        ))}
        {members.data && members.data.length <= 1 && <EmptyState title="No teammates yet" description="Invite people from Settings → Members." />}
      </div>
    </Modal>
  );
}

type Suggestion = { title: string; description: string; priority: string; due_date: string | null; owner_name: string | null };
function SuggestTasksModal({ open, onClose, convId }: { open: boolean; onClose: () => void; convId: string }) {
  const [items, setItems] = useState<(Suggestion & { keep: boolean })[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setItems(null);
    api<{ suggestions: Suggestion[] }>("/assistant/recommend-tasks", { body: { conversation_id: convId } }).then((r) => setItems(r.suggestions.map((s) => ({ ...s, keep: true })))).catch((e) => { toastError(e); onClose(); });
  }, [open, convId, onClose]);
  return (
    <Modal open={open} onClose={onClose} title="Suggested tasks" description="Review before creating — nothing is created automatically." wide
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!items?.some((i) => i.keep)} onClick={async () => {
        setBusy(true);
        try { for (const i of items!.filter((x) => x.keep)) await api("/tasks", { body: { title: i.title, description: i.description, priority: i.priority, due_date: i.due_date, source: "ai", labels: ["from-assistant"] } }); toast.success("Tasks created"); onClose(); }
        catch (e) { toastError(e); } finally { setBusy(false); }
      }}>Create selected</Button></>}>
      {!items ? <LoadingBlock rows={3} /> : items.length === 0 ? <EmptyState title="No action items found" description="The conversation doesn't contain explicit next steps." /> : (
        <ul className="space-y-2">{items.map((i, idx) => (
          <li key={idx} className="flex items-start gap-3 rounded-lg border border-line p-3">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--brand)]" checked={i.keep} onChange={(e) => setItems(items.map((x, j) => j === idx ? { ...x, keep: e.target.checked } : x))} aria-label={`Include ${i.title}`} />
            <div className="flex-1 text-[13px]"><div className="font-medium">{i.title}</div><div className="text-subtle">{i.owner_name ? `Owner: ${i.owner_name} · ` : ""}{i.due_date ? `Due ${i.due_date} · ` : ""}{i.priority}</div></div>
          </li>
        ))}</ul>
      )}
    </Modal>
  );
}
