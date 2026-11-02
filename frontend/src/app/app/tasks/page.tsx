"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { CalendarDays, ChevronLeft, ChevronRight, Kanban, List, Paperclip, Plus, Sparkles, Wand2 } from "lucide-react";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, fmtDate, timeAgo } from "@/lib/utils";
import type { Member, Task } from "@/lib/types";
import { Avatar, Badge, Button, EmptyState, Field, Input, LoadingBlock, Markdown, Modal, PageHeader, Segmented, Select, StatusBadge, Table, Td, Textarea, Th } from "@/components/ui";

const COLUMNS = [{ key: "todo", label: "To do" }, { key: "in_progress", label: "In progress" }, { key: "in_review", label: "In review" }, { key: "done", label: "Done" }];
type Detail = Task & { comments: { id: string; user: { full_name: string }; body: string; created_at: string }[]; activity: { action: string; user: { full_name: string } | null; details: any; created_at: string }[]; attachments: { id: string; filename: string; size_bytes: number }[] };

function TasksInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const { can } = useAuth();
  const [view, setView] = useState<"board" | "list" | "calendar">("board");
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState("");
  const tasks = useOrgSWR<Task[]>(`/tasks?${mine ? "assignee=me&" : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`);
  const members = useOrgSWR<Member[]>("/orgs/current/members");
  const [newOpen, setNewOpen] = useState(false);
  const [extractOpen, setExtractOpen] = useState(sp.get("extract") === "1");
  const [summary, setSummary] = useState<string | null>(null);
  const openId = sp.get("task");
  const setOpenId = (id: string | null) => router.replace(id ? `/app/tasks?task=${id}` : "/app/tasks");
  const [dragId, setDragId] = useState<string | null>(null);

  const move = async (t: Task, status: string) => {
    if (t.status === status) return;
    tasks.mutate((ts) => ts?.map((x) => (x.id === t.id ? { ...x, status } : x)), false);
    try { await api(`/tasks/${t.id}`, { method: "PATCH", body: { status } }); } catch (e) { toastError(e); } finally { tasks.mutate(); }
  };

  return (
    <div className="animate-in">
      <PageHeader title="Tasks" description="Lightweight project tracking — with AI that turns meeting notes into owned, dated tasks."
        actions={<>
          <Button variant="outline" size="sm" onClick={async () => { setSummary(""); try { setSummary((await api<{ summary: string }>("/tasks/ai/summary", { method: "POST" })).summary); } catch (e) { toastError(e); setSummary(null); } }}><Sparkles className="h-4 w-4" />AI status summary</Button>
          {can("tasks.write") && <Button variant="outline" size="sm" onClick={() => setExtractOpen(true)}><Wand2 className="h-4 w-4" />Notes → tasks</Button>}
          {can("tasks.write") && <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="h-4 w-4" />New task</Button>}
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Segmented value={view} onChange={setView} options={[{ value: "board", label: <span className="inline-flex items-center gap-1"><Kanban className="h-3.5 w-3.5" />Board</span> }, { value: "list", label: <span className="inline-flex items-center gap-1"><List className="h-3.5 w-3.5" />List</span> }, { value: "calendar", label: <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />Calendar</span> }]} />
        <Segmented value={mine ? "mine" : "all"} onChange={(v) => setMine(v === "mine")} options={[{ value: "all", label: "All" }, { value: "mine", label: "Assigned to me" }]} />
        <Input className="w-56" placeholder="Search tasks" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search tasks" />
      </div>
      {tasks.isLoading ? <LoadingBlock rows={5} /> : !tasks.data?.length && !q ? (
        <EmptyState title="No tasks yet" description="Create one, or paste meeting notes and let AI extract the action items." action={can("tasks.write") ? <Button size="sm" onClick={() => setExtractOpen(true)}><Wand2 className="h-4 w-4" />Extract from notes</Button> : undefined} />
      ) : view === "board" ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((c) => {
            const items = tasks.data!.filter((t) => t.status === c.key);
            return (
              <div key={c.key} className="flex min-h-[200px] flex-col rounded-xl border border-line bg-panel-2/60 p-2" onDragOver={(e) => e.preventDefault()}
                onDrop={() => { const t = tasks.data!.find((x) => x.id === dragId); if (t) move(t, c.key); setDragId(null); }} aria-label={`${c.label} column`}>
                <div className="mb-2 flex items-center justify-between px-1.5 pt-1 text-[12.5px] font-medium"><span>{c.label}</span><span className="text-subtle">{items.length}</span></div>
                <div className="space-y-2">{items.map((t) => (
                  <button key={t.id} draggable={can("tasks.write")} onDragStart={() => setDragId(t.id)} onClick={() => setOpenId(t.id)}
                    className="block w-full rounded-lg border border-line bg-panel p-3 text-left shadow-card hover:border-line-strong">
                    <div className="text-[13px] font-medium leading-snug">{t.title}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={t.priority} />{t.source !== "manual" && <Badge tone="brand">{t.source === "ai" ? "AI" : t.source}</Badge>}
                      {t.due_date && <span className={cn("text-[11.5px]", t.overdue ? "text-danger" : "text-subtle")}>{fmtDate(t.due_date)}</span>}
                      <span className="ml-auto">{t.assignee && <Avatar name={t.assignee.full_name} size={20} />}</span>
                    </div>
                    <label className="sr-only" htmlFor={`mv-${t.id}`}>Move</label>
                  </button>
                ))}</div>
              </div>
            );
          })}
        </div>
      ) : view === "list" ? (
        <div className="rounded-xl border border-line bg-panel"><Table><thead><tr><Th>Title</Th><Th>Status</Th><Th>Priority</Th><Th className="hidden md:table-cell">Assignee</Th><Th className="hidden sm:table-cell">Due</Th></tr></thead>
          <tbody>{tasks.data!.map((t) => (
            <tr key={t.id} className="cursor-pointer hover:bg-panel-2" onClick={() => setOpenId(t.id)}>
              <Td className="font-medium">{t.title}</Td>
              <Td onClick={(e) => e.stopPropagation()}><Select className="h-7 w-32 text-[12px]" value={t.status} onChange={(e) => move(t, e.target.value)} disabled={!can("tasks.write")} aria-label="Status">{COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Select></Td>
              <Td><StatusBadge status={t.priority} /></Td><Td className="hidden md:table-cell">{t.assignee?.full_name || <span className="text-subtle">Unassigned</span>}</Td>
              <Td className={cn("hidden sm:table-cell", t.overdue && "text-danger")}>{t.due_date ? fmtDate(t.due_date) : "—"}</Td></tr>
          ))}</tbody></Table></div>
      ) : <CalendarView tasks={tasks.data!} onOpen={setOpenId} />}
      <NewTaskModal open={newOpen} onClose={() => setNewOpen(false)} members={members.data || []} onCreated={() => tasks.mutate()} />
      <ExtractModal open={extractOpen} onClose={() => setExtractOpen(false)} onCreated={() => tasks.mutate()} />
      {openId && <TaskDrawer id={openId} members={members.data || []} onClose={() => setOpenId(null)} onChanged={() => tasks.mutate()} />}
      <Modal open={summary !== null} onClose={() => setSummary(null)} title="AI status summary" wide>{summary === "" ? <LoadingBlock rows={4} /> : <Markdown>{summary || ""}</Markdown>}</Modal>
    </div>
  );
}

export default function TasksPage() { return <Suspense><TasksInner /></Suspense>; }

function CalendarView({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void }) {
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const days = useMemo(() => {
    const start = new Date(cursor); start.setDate(1 - ((start.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  }, [cursor]);
  const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const today = key(new Date());
  const undated = tasks.filter((t) => !t.due_date).length;
  return (
    <div className="rounded-xl border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <Button size="icon" variant="ghost" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))} aria-label="Previous month"><ChevronLeft className="h-4 w-4" /></Button>
        <span className="min-w-36 text-center text-sm font-medium">{cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</span>
        <Button size="icon" variant="ghost" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))} aria-label="Next month"><ChevronRight className="h-4 w-4" /></Button>
        {undated > 0 && <span className="ml-auto text-[12px] text-subtle">{undated} task(s) without a due date not shown</span>}
      </div>
      <div className="grid grid-cols-7 text-[11px] font-medium uppercase text-subtle">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="px-2 py-1.5">{d}</div>)}</div>
      <div className="grid grid-cols-7 border-t border-line">{days.map((d) => {
        const k = key(d); const items = tasks.filter((t) => t.due_date === k);
        return (
          <div key={k} className={cn("min-h-24 border-b border-r border-line p-1.5", d.getMonth() !== cursor.getMonth() && "bg-panel-2/50")}>
            <div className={cn("mb-1 text-[11.5px]", k === today ? "inline-flex h-5 w-5 items-center justify-center rounded-full bg-brand text-brand-fg" : "text-subtle")}>{d.getDate()}</div>
            {items.slice(0, 3).map((t) => <button key={t.id} onClick={() => onOpen(t.id)} className={cn("mb-0.5 block w-full truncate rounded px-1 py-0.5 text-left text-[11.5px]", t.status === "done" ? "bg-success-soft text-success line-through" : t.overdue ? "bg-danger-soft text-danger" : "bg-brand-soft text-brand-text")}>{t.title}</button>)}
            {items.length > 3 && <span className="text-[11px] text-subtle">+{items.length - 3} more</span>}
          </div>
        );
      })}</div>
    </div>
  );
}

function NewTaskModal({ open, onClose, members, onCreated }: { open: boolean; onClose: () => void; members: Member[]; onCreated: () => void }) {
  const empty = { title: "", description: "", priority: "medium", assignee_id: "", due_date: "", labels: "" };
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  return (
    <Modal open={open} onClose={onClose} title="New task" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!f.title.trim()} onClick={async () => {
      setBusy(true);
      try { await api("/tasks", { body: { ...f, assignee_id: f.assignee_id || null, due_date: f.due_date || null, labels: f.labels.split(",").map((l) => l.trim()).filter(Boolean) } }); toast.success("Task created"); setF(empty); onCreated(); onClose(); }
      catch (e) { toastError(e); } finally { setBusy(false); }
    }}>Create</Button></>}>
      <div className="space-y-3">
        <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus /></Field>
        <Field label="Description"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Priority"><Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["low", "medium", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
          <Field label="Assignee"><Select value={f.assignee_id} onChange={(e) => setF({ ...f, assignee_id: e.target.value })}><option value="">Unassigned</option>{members.filter((m) => m.status === "active").map((m) => <option key={m.user.id} value={m.user.id}>{m.user.full_name}</option>)}</Select></Field>
          <Field label="Due date"><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
        </div>
        <Field label="Labels"><Input value={f.labels} onChange={(e) => setF({ ...f, labels: e.target.value })} placeholder="ops, q4" /></Field>
      </div>
    </Modal>
  );
}

type Sug = { title: string; description: string; owner_name: string | null; due_date: string | null; priority: string; assignee_id: string | null };
function ExtractModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [text, setText] = useState("");
  const [sugs, setSugs] = useState<(Sug & { keep: boolean })[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) { setSugs(null); } }, [open]);
  return (
    <Modal open={open} onClose={onClose} wide title="Turn notes into tasks" description="Paste meeting notes, an email thread or a chat transcript. Review the suggestions before anything is created."
      footer={sugs ? <><Button variant="ghost" onClick={() => setSugs(null)}>Back</Button><Button loading={busy} disabled={!sugs.some((s) => s.keep)} onClick={async () => {
        setBusy(true);
        try { for (const s of sugs.filter((x) => x.keep)) await api("/tasks", { body: { title: s.title, description: s.description, priority: s.priority, due_date: s.due_date, assignee_id: s.assignee_id, labels: ["ai-extracted"], source: "ai" } }); toast.success("Tasks created"); onCreated(); onClose(); setText(""); }
        catch (e) { toastError(e); } finally { setBusy(false); }
      }}>Create {sugs.filter((s) => s.keep).length} task(s)</Button></>
        : <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={text.trim().length < 10} onClick={async () => {
          setBusy(true);
          try { const r = await api<{ suggestions: Sug[] }>("/tasks/ai/extract", { body: { text, create: false } }); setSugs(r.suggestions.map((s) => ({ ...s, keep: true }))); }
          catch (e) { toastError(e); } finally { setBusy(false); }
        }}><Sparkles className="h-4 w-4" />Extract action items</Button></>}>
      {!sugs ? <Textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Weekly sync\n- Priya to send the vendor proposal by Friday\n- Action: review churn numbers (urgent)"} aria-label="Notes" />
        : sugs.length === 0 ? <EmptyState title="No action items found" description="Try notes with explicit owners or verbs like 'send', 'review', 'schedule'." /> : (
          <ul className="space-y-2">{sugs.map((s, i) => (
            <li key={i} className="flex items-start gap-3 rounded-lg border border-line p-3">
              <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--brand)]" checked={s.keep} onChange={(e) => setSugs(sugs.map((x, j) => j === i ? { ...x, keep: e.target.checked } : x))} aria-label={`Include ${s.title}`} />
              <div className="flex-1 text-[13px]"><Input className="h-8 font-medium" value={s.title} onChange={(e) => setSugs(sugs.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} aria-label="Task title" />
                <div className="mt-1.5 flex flex-wrap gap-2 text-[12px] text-subtle"><StatusBadge status={s.priority} />{s.owner_name && <span>Owner: {s.owner_name}{s.assignee_id ? " ✓ matched" : " (no matching member)"}</span>}{s.due_date && <span>Due {s.due_date}</span>}</div></div>
            </li>
          ))}</ul>
        )}
    </Modal>
  );
}

function TaskDrawer({ id, members, onClose, onChanged }: { id: string; members: Member[]; onClose: () => void; onChanged: () => void }) {
  const { can } = useAuth();
  const t = useOrgSWR<Detail>(`/tasks/${id}`);
  const [comment, setComment] = useState("");
  const patch = async (body: Record<string, unknown>) => { try { await api(`/tasks/${id}`, { method: "PATCH", body }); t.mutate(); onChanged(); } catch (e) { toastError(e); } };
  const d = t.data;
  return (
    <Modal open onClose={onClose} title={d?.title || "Task"} wide>
      {!d ? <LoadingBlock rows={5} /> : (
        <div className="grid gap-6 md:grid-cols-3">
          <div className="space-y-4 md:col-span-2">
            <Field label="Title"><Input defaultValue={d.title} onBlur={(e) => e.target.value !== d.title && patch({ title: e.target.value })} disabled={!can("tasks.write")} /></Field>
            <Field label="Description"><Textarea rows={5} defaultValue={d.description} onBlur={(e) => e.target.value !== d.description && patch({ description: e.target.value })} disabled={!can("tasks.write")} /></Field>
            <div>
              <h4 className="mb-2 text-[13px] font-semibold">Comments</h4>
              <div className="space-y-2">{d.comments.map((c) => <div key={c.id} className="rounded-lg bg-panel-2 p-2.5 text-[13px]"><div className="mb-0.5 text-[12px] text-subtle">{c.user?.full_name} · {timeAgo(c.created_at)}</div>{c.body}</div>)}</div>
              {can("tasks.write") && <form className="mt-2 flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!comment.trim()) return; await api(`/tasks/${id}/comments`, { body: { body: comment } }); setComment(""); t.mutate(); }}>
                <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment" aria-label="Comment" /><Button type="submit" size="sm">Post</Button></form>}
            </div>
            <div>
              <h4 className="mb-2 text-[13px] font-semibold">Activity</h4>
              <ul className="space-y-1 text-[12px] text-subtle">{d.activity.map((a, i) => <li key={i}>{a.user?.full_name || "System"} {a.action}{a.details?.status ? ` status ${a.details.status[0]} → ${a.details.status[1]}` : ""} · {timeAgo(a.created_at)}</li>)}</ul>
            </div>
          </div>
          <div className="space-y-3">
            <Field label="Status"><Select value={d.status} onChange={(e) => patch({ status: e.target.value })} disabled={!can("tasks.write")}>{COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Select></Field>
            <Field label="Priority"><Select value={d.priority} onChange={(e) => patch({ priority: e.target.value })} disabled={!can("tasks.write")}>{["low", "medium", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
            <Field label="Assignee"><Select value={d.assignee_id || ""} onChange={(e) => patch(e.target.value ? { assignee_id: e.target.value } : { clear_assignee: true })} disabled={!can("tasks.write")}><option value="">Unassigned</option>{members.filter((m) => m.status === "active").map((m) => <option key={m.user.id} value={m.user.id}>{m.user.full_name}</option>)}</Select></Field>
            <Field label="Due date"><Input type="date" value={d.due_date || ""} onChange={(e) => patch(e.target.value ? { due_date: e.target.value } : { clear_due_date: true })} disabled={!can("tasks.write")} /></Field>
            <div className="flex flex-wrap gap-1">{d.labels.map((l) => <Badge key={l} tone="brand">{l}</Badge>)}{d.source !== "manual" && <Badge>source: {d.source}</Badge>}</div>
            <div>
              <h4 className="mb-1.5 text-[13px] font-semibold">Attachments</h4>
              {d.attachments.map((a) => <button key={a.id} className="flex items-center gap-1.5 text-[12.5px] text-brand-text" onClick={() => download(`/tasks/${id}/attachments/${a.id}`, a.filename)}><Paperclip className="h-3.5 w-3.5" />{a.filename}</button>)}
              {can("tasks.write") && <label className="mt-1 inline-flex cursor-pointer items-center gap-1 text-[12.5px] text-subtle hover:text-fg"><Plus className="h-3.5 w-3.5" />Attach file
                <input type="file" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); try { await api(`/tasks/${id}/attachments`, { form: fd }); t.mutate(); } catch (er) { toastError(er); } }} /></label>}
            </div>
            {can("tasks.write") && <Button variant="ghost" size="sm" className="text-danger" onClick={async () => { if (!confirm("Delete task?")) return; try { await api(`/tasks/${id}`, { method: "DELETE" }); onChanged(); onClose(); } catch (e) { toastError(e); } }}>Delete task</Button>}
          </div>
        </div>
      )}
    </Modal>
  );
}
