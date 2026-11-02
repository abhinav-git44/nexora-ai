"use client";
import Link from "next/link";
import { toast } from "sonner";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useOrgSWR } from "@/lib/hooks";
import { cn, timeAgo, titleCase } from "@/lib/utils";
import { Button, Card, CardBody, CardHeader, EmptyState, LoadingBlock, PageHeader, Switch, Table, Td, Th } from "@/components/ui";

type N = { id: string; type: string; title: string; body: string | null; link: string | null; read: boolean; created_at: string };

export default function Notifications() {
  const list = useOrgSWR<{ unread: number; items: N[] }>("/notifications?limit=100");
  const prefs = useOrgSWR<Record<string, { in_app: boolean; email: boolean }>>("/notifications/preferences");
  return (
    <div className="animate-in">
      <PageHeader title="Notifications" actions={<Button size="sm" variant="outline" onClick={async () => { await api("/notifications/read-all", { method: "POST" }); list.mutate(); }}>Mark all read</Button>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">{!list.data ? <CardBody><LoadingBlock /></CardBody> : !list.data.items.length ? <CardBody><EmptyState icon={Bell} title="No notifications" /></CardBody> : (
          <ul className="divide-y divide-line">{list.data.items.map((n) => (
            <li key={n.id} className={cn("flex items-start gap-3 px-5 py-3", !n.read && "bg-brand-soft/40")}>
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.read ? "bg-line-strong" : "bg-brand")} />
              <div className="min-w-0 flex-1 text-[13px]"><div className="font-medium">{n.link ? <Link href={n.link} className="hover:text-brand-text">{n.title}</Link> : n.title}</div>
                {n.body && <div className="text-subtle">{n.body}</div>}<div className="text-[11.5px] text-subtle">{titleCase(n.type)} · {timeAgo(n.created_at)}</div></div>
              <button className="text-[12px] text-subtle hover:text-fg" onClick={async () => { await api(`/notifications/${n.id}/${n.read ? "unread" : "read"}`, { method: "POST" }); list.mutate(); }}>{n.read ? "Mark unread" : "Mark read"}</button>
            </li>
          ))}</ul>
        )}</Card>
        <Card className="self-start"><CardHeader title="Preferences" description="Choose where each type of notification is delivered." />
          {prefs.data && <Table><thead><tr><Th>Type</Th><Th>In-app</Th><Th>Email</Th></tr></thead><tbody>{Object.entries(prefs.data).map(([t, p]) => (
            <tr key={t}><Td>{titleCase(t)}</Td>
              {(["in_app", "email"] as const).map((ch) => <Td key={ch}><Switch checked={p[ch]} onChange={async (v) => { const next = { ...prefs.data!, [t]: { ...p, [ch]: v } }; prefs.mutate(next, false); await api("/notifications/preferences", { method: "PUT", body: { prefs: next } }); toast.success("Saved"); }} /></Td>)}</tr>
          ))}</tbody></Table>}</Card>
      </div>
    </div>
  );
}
