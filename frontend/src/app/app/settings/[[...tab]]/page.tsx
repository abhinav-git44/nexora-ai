"use client";
import Link from "next/link";
import { use, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api, session } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, fmtDate, timeAgo } from "@/lib/utils";
import type { Member } from "@/lib/types";
import { Avatar, Badge, Button, ButtonLink, Callout, Card, CardBody, CardHeader, CodeBlock, EmptyState, Field, Input, LoadingBlock, Modal, PageHeader, Select, StatusBadge, Table, Td, Textarea, Th } from "@/components/ui";

const TABS = [
  { key: "profile", label: "Profile" }, { key: "security", label: "Security" }, { key: "organisation", label: "Organisation", perm: "org.read" },
  { key: "members", label: "Members", perm: "members.read" }, { key: "workspaces", label: "Workspaces" }, { key: "audit", label: "Audit log", perm: "audit.read" },
  { key: "support", label: "Support" }, { key: "privacy", label: "Privacy & data" },
];

export default function Settings({ params }: { params: Promise<{ tab?: string[] }> }) {
  const { tab } = use(params);
  const current = tab?.[0] || "profile";
  const { can } = useAuth();
  return (
    <div className="animate-in">
      <PageHeader title="Settings" />
      <div className="flex flex-col gap-6 md:flex-row">
        <nav className="flex gap-1 overflow-x-auto md:w-48 md:flex-col" aria-label="Settings sections">
          {TABS.filter((t) => !t.perm || can(t.perm)).map((t) => (
            <Link key={t.key} href={`/app/settings/${t.key}`} className={cn("whitespace-nowrap rounded-lg px-3 py-1.5 text-[13.5px]", current === t.key ? "bg-panel-2 font-medium text-fg" : "text-muted hover:bg-panel-2")}>{t.label}</Link>
          ))}
        </nav>
        <div className="min-w-0 flex-1">
          {current === "profile" && <Profile />}{current === "security" && <Security />}{current === "organisation" && <Organisation />}
          {current === "members" && <Members />}{current === "workspaces" && <Workspaces />}{current === "audit" && <Audit />}
          {current === "support" && <Support />}{current === "privacy" && <Privacy />}
        </div>
      </div>
    </div>
  );
}

function Profile() {
  const { user, reload } = useAuth();
  const [f, setF] = useState({ full_name: user?.full_name || "", job_title: user?.job_title || "" });
  return (
    <Card><CardHeader title="Profile" />
      <CardBody className="max-w-lg space-y-4">
        <div className="flex items-center gap-3"><Avatar name={user?.full_name} size={44} /><div><div className="font-medium">{user?.email}</div><div className="text-[12px] text-subtle">{user?.email_verified ? "Email verified" : "Email not verified"}</div></div></div>
        <Field label="Full name"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label="Job title"><Input value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} placeholder="Operations Manager" /></Field>
        <Button onClick={async () => { try { await api("/auth/me", { method: "PATCH", body: f, noOrg: true }); await reload(); toast.success("Profile saved"); } catch (e) { toastError(e); } }}>Save</Button>
      </CardBody></Card>
  );
}

function Security() {
  const sessions = useOrgSWR<{ id: string; user_agent: string; ip: string; created_at: string; last_used_at: string; current: boolean }[]>("/auth/sessions");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  return (
    <div className="space-y-6">
      <Card><CardHeader title="Change password" description="Changing your password signs out all other sessions." />
        <CardBody><form className="max-w-sm space-y-3" onSubmit={async (e) => { e.preventDefault(); try { await api("/auth/change-password", { body: pw, noOrg: true }); toast.success("Password updated"); setPw({ current_password: "", new_password: "" }); sessions.mutate(); } catch (er) { toastError(er); } }}>
          <Field label="Current password"><Input type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></Field>
          <Field label="New password" hint="10+ characters with upper, lower case and a number"><Input type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={10} /></Field>
          <Button type="submit">Update password</Button></form></CardBody></Card>
      <Card><CardHeader title="Active sessions" />
        {!sessions.data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>Device</Th><Th>IP</Th><Th>Last active</Th><Th /></tr></thead><tbody>{sessions.data.map((s) => (
          <tr key={s.id}><Td className="max-w-xs truncate text-[12.5px]">{s.user_agent || "Unknown"} {s.current && <Badge tone="brand">this device</Badge>}</Td><Td className="text-subtle">{s.ip}</Td><Td className="text-subtle">{timeAgo(s.last_used_at)}</Td>
            <Td>{!s.current && <Button size="sm" variant="ghost" onClick={async () => { await api(`/auth/sessions/${s.id}`, { method: "DELETE", noOrg: true }); sessions.mutate(); toast.success("Session revoked"); }}>Revoke</Button>}</Td></tr>
        ))}</tbody></Table>}</Card>
    </div>
  );
}

function Organisation() {
  const { org, can, reload, switchOrg } = useAuth();
  const sp = useSearchParams();
  const [f, setF] = useState({ name: org?.name || "", industry: org?.industry || "", size: org?.size || "" });
  const [newName, setNewName] = useState("");
  const [del, setDel] = useState({ open: false, confirm_name: "", password: "" });
  return (
    <div className="space-y-6">
      <Card><CardHeader title="Organisation details" />
        <CardBody className="max-w-lg space-y-3">
          <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} disabled={!can("org.update")} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Industry"><Input value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} disabled={!can("org.update")} /></Field>
            <Field label="Company size"><Select value={f.size} onChange={(e) => setF({ ...f, size: e.target.value })} disabled={!can("org.update")}><option value="">—</option>{["1-10", "11-50", "51-200", "201-1000", "1000+"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          </div>
          {can("org.update") && <Button onClick={async () => { try { await api("/orgs/current", { method: "PATCH", body: f }); await reload(); toast.success("Saved"); } catch (e) { toastError(e); } }}>Save</Button>}
        </CardBody></Card>
      <Card><CardHeader title="Create another organisation" description="Each organisation has separate data, members and billing." />
        <CardBody><form className="flex max-w-lg gap-2" onSubmit={async (e) => { e.preventDefault(); try { const o = await api<{ id: string }>("/orgs", { body: { name: newName }, noOrg: true }); await reload(); await switchOrg(o.id); toast.success("Organisation created"); } catch (er) { toastError(er); } }}>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New organisation name" required minLength={2} autoFocus={sp.get("new") === "1"} /><Button type="submit">Create</Button></form></CardBody></Card>
      {can("org.delete") && (
        <Card className="border-danger/40"><CardHeader title="Danger zone" />
          <CardBody className="space-y-3 text-[13px]">
            {org?.deletion_requested_at ? (<><Callout tone="danger">Deletion requested {fmtDate(org.deletion_requested_at, true)}. All data will be purged 7 days after the request.</Callout>
              <Button variant="outline" onClick={async () => { await api("/orgs/current/delete/cancel", { method: "POST" }); await reload(); toast.success("Deletion cancelled"); }}>Cancel deletion</Button></>)
              : (<><p className="text-muted">Deleting an organisation removes all documents, conversations, agents, workflows, datasets and tasks after a 7-day grace period.</p>
                <Button variant="danger" onClick={() => setDel({ ...del, open: true })}>Delete organisation</Button></>)}
          </CardBody></Card>
      )}
      <Modal open={del.open} onClose={() => setDel({ ...del, open: false })} title="Delete organisation" description={`Type "${org?.name}" and your password to confirm.`}
        footer={<><Button variant="ghost" onClick={() => setDel({ ...del, open: false })}>Cancel</Button><Button variant="danger" onClick={async () => { try { await api("/orgs/current/delete", { body: { confirm_name: del.confirm_name, password: del.password } }); await reload(); setDel({ open: false, confirm_name: "", password: "" }); toast.success("Deletion scheduled"); } catch (e) { toastError(e); } }}>Schedule deletion</Button></>}>
        <div className="space-y-3"><Field label="Organisation name"><Input value={del.confirm_name} onChange={(e) => setDel({ ...del, confirm_name: e.target.value })} /></Field>
          <Field label="Password"><Input type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} /></Field></div>
      </Modal>
    </div>
  );
}

function Members() {
  const { can, user, org } = useAuth();
  const members = useOrgSWR<Member[]>("/orgs/current/members");
  const invites = useOrgSWR<{ id: string; email: string; role: string; expires_at: string; expired: boolean }[]>(can("members.invite") ? "/orgs/current/invitations" : null);
  const [inv, setInv] = useState({ email: "", role: "member" });
  const act = async (fn: () => Promise<unknown>, msg: string) => { try { await fn(); members.mutate(); toast.success(msg); } catch (e) { toastError(e); } };
  return (
    <div className="space-y-6">
      {can("members.invite") && (
        <Card><CardHeader title="Invite teammates" description="Invitations expire after 7 days. You can only grant roles up to your own." />
          <CardBody><form className="flex flex-col gap-2 sm:flex-row" onSubmit={async (e) => { e.preventDefault(); try { await api("/orgs/current/invitations", { body: inv }); toast.success(`Invitation sent to ${inv.email}`); setInv({ ...inv, email: "" }); invites.mutate(); } catch (er) { toastError(er); } }}>
            <Input type="email" placeholder="name@company.com" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} required aria-label="Email" />
            <Select className="sm:w-40" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })} aria-label="Role">{["viewer", "member", "manager", "admin", ...(org?.role === "owner" ? ["owner"] : [])].map((r) => <option key={r}>{r}</option>)}</Select>
            <Button type="submit">Send invite</Button></form>
            {invites.data && invites.data.length > 0 && <ul className="mt-4 divide-y divide-line text-[13px]">{invites.data.map((i) => (
              <li key={i.id} className="flex items-center gap-2 py-2"><span className="flex-1">{i.email}</span><Badge>{i.role}</Badge>{i.expired ? <Badge tone="danger">expired</Badge> : <span className="text-[12px] text-subtle">expires {fmtDate(i.expires_at)}</span>}
                <Button size="sm" variant="ghost" onClick={async () => { await api(`/orgs/current/invitations/${i.id}`, { method: "DELETE" }); invites.mutate(); }}>Revoke</Button></li>
            ))}</ul>}
          </CardBody></Card>
      )}
      <Card><CardHeader title="Members" description="Roles: Owner › Admin › Manager › Member › Viewer." />
        {!members.data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>Member</Th><Th>Role</Th><Th>Status</Th><Th className="hidden sm:table-cell">Last sign-in</Th><Th /></tr></thead><tbody>{members.data.map((m) => {
          const self = m.user.id === user?.id;
          return (
            <tr key={m.id}><Td><div className="flex items-center gap-2"><Avatar name={m.user.full_name} size={26} /><div><div className="font-medium">{m.user.full_name}{self && " (you)"}</div><div className="text-[12px] text-subtle">{m.user.email}</div></div></div></Td>
              <Td>{can("members.manage") && !self ? <Select className="h-8 w-32 text-[12.5px]" value={m.role} onChange={(e) => act(() => api(`/orgs/current/members/${m.id}`, { method: "PATCH", body: { role: e.target.value } }), "Role updated")} aria-label="Role">{["viewer", "member", "manager", "admin", "owner"].map((r) => <option key={r}>{r}</option>)}</Select> : <Badge>{m.role}</Badge>}</Td>
              <Td><StatusBadge status={m.status} /></Td><Td className="hidden text-subtle sm:table-cell">{timeAgo(m.last_login_at)}</Td>
              <Td>{can("members.manage") && !self && <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => act(() => api(`/orgs/current/members/${m.id}/${m.status === "active" ? "deactivate" : "reactivate"}`, { method: "POST" }), m.status === "active" ? "Deactivated" : "Reactivated")}>{m.status === "active" ? "Deactivate" : "Reactivate"}</Button>
                <Button size="sm" variant="ghost" className="text-danger" onClick={() => confirm(`Remove ${m.user.full_name}?`) && act(() => api(`/orgs/current/members/${m.id}`, { method: "DELETE" }), "Removed")}>Remove</Button></div>}</Td></tr>
          );
        })}</tbody></Table>}</Card>
    </div>
  );
}

function Workspaces() {
  const { can } = useAuth();
  const ws = useOrgSWR<{ id: string; name: string; description: string | null; is_default: boolean; created_at: string }[]>("/orgs/current/workspaces");
  const [name, setName] = useState("");
  return (
    <Card><CardHeader title="Workspaces" description="Group knowledge and work by team or client." />
      <CardBody className="space-y-4">
        {can("workspaces.write") && <form className="flex max-w-lg gap-2" onSubmit={async (e) => { e.preventDefault(); try { await api("/orgs/current/workspaces", { body: { name } }); setName(""); ws.mutate(); } catch (er) { toastError(er); } }}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customer Success" required aria-label="Workspace name" /><Button type="submit">Add</Button></form>}
        <ul className="divide-y divide-line text-[13px]">{ws.data?.map((w) => (
          <li key={w.id} className="flex items-center gap-2 py-2.5"><span className="flex-1 font-medium">{w.name}</span>{w.is_default && <Badge tone="brand">default</Badge>}
            {can("workspaces.write") && !w.is_default && <Button size="sm" variant="ghost" className="text-danger" onClick={async () => { if (!confirm("Delete workspace?")) return; await api(`/orgs/current/workspaces/${w.id}`, { method: "DELETE" }); ws.mutate(); }}>Delete</Button>}</li>
        ))}</ul>
      </CardBody></Card>
  );
}

function Audit() {
  const { hasFeature, can } = useAuth();
  const [action, setAction] = useState("");
  const logs = useOrgSWR<{ id: string; action: string; actor: { full_name: string } | null; target_type: string | null; details: any; ip: string | null; created_at: string }[]>(hasFeature("audit_logs") ? `/orgs/current/audit-logs?limit=200${action ? `&action=${action}` : ""}` : null);
  if (!hasFeature("audit_logs")) return <EmptyState title="Audit logs are available on Professional and Enterprise" action={can("billing.read") ? <ButtonLink href="/app/billing" size="sm">View plans</ButtonLink> : undefined} />;
  return (
    <Card><CardHeader title="Audit log" description="Security-relevant actions in this organisation." action={<Select className="w-44" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter action">
      <option value="">All actions</option>{["auth", "member", "document", "agent", "workflow", "approval", "integration", "billing", "org"].map((a) => <option key={a} value={a}>{a}.*</option>)}</Select>} />
      {!logs.data ? <CardBody><LoadingBlock /></CardBody> : <Table><thead><tr><Th>When</Th><Th>Actor</Th><Th>Action</Th><Th className="hidden md:table-cell">Details</Th><Th className="hidden lg:table-cell">IP</Th></tr></thead><tbody>{logs.data.map((l) => (
        <tr key={l.id}><Td className="whitespace-nowrap text-subtle">{fmtDate(l.created_at, true)}</Td><Td>{l.actor?.full_name || "System"}</Td><Td><code className="font-mono text-[12px]">{l.action}</code></Td>
          <Td className="hidden max-w-sm truncate text-[12px] text-subtle md:table-cell">{JSON.stringify(l.details)}</Td><Td className="hidden text-subtle lg:table-cell">{l.ip}</Td></tr>
      ))}</tbody></Table>}</Card>
  );
}

function Support() {
  const tickets = useOrgSWR<{ id: string; subject: string; status: string; priority: string; admin_note: string | null; created_at: string }[]>("/support/tickets");
  const [f, setF] = useState({ subject: "", body: "", priority: "normal" });
  return (
    <div className="space-y-6">
      <Card><CardHeader title="Contact support" />
        <CardBody><form className="max-w-lg space-y-3" onSubmit={async (e) => { e.preventDefault(); try { await api("/support/tickets", { body: f }); setF({ subject: "", body: "", priority: "normal" }); tickets.mutate(); toast.success("Ticket submitted"); } catch (er) { toastError(er); } }}>
          <Field label="Subject"><Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} required minLength={3} /></Field>
          <Field label="Describe the issue"><Textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} required minLength={5} /></Field>
          <Field label="Priority"><Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["low", "normal", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
          <Button type="submit">Submit</Button></form></CardBody></Card>
      <Card><CardHeader title="Your tickets" />{tickets.data?.length ? <ul className="divide-y divide-line">{tickets.data.map((t) => (
        <li key={t.id} className="px-5 py-3 text-[13px]"><div className="flex items-center gap-2"><StatusBadge status={t.status === "resolved" ? "succeeded" : "pending"} label={t.status} /><span className="font-medium">{t.subject}</span><span className="ml-auto text-subtle">{timeAgo(t.created_at)}</span></div>
          {t.admin_note && <p className="mt-1 text-subtle">Support: {t.admin_note}</p>}</li>))}</ul> : <CardBody><p className="text-sm text-subtle">No tickets.</p></CardBody>}</Card>
    </div>
  );
}

function Privacy() {
  const router = useRouter();
  const [data, setData] = useState<string | null>(null);
  const [del, setDel] = useState({ open: false, password: "", confirm: "" });
  return (
    <div className="space-y-6">
      <Card><CardHeader title="Export my data" description="Download personal data NEXORA holds about you (profile, conversations, tasks, notifications)." />
        <CardBody><Button variant="outline" onClick={async () => { const d = await api("/auth/me/export", { noOrg: true }); setData(JSON.stringify(d, null, 2)); }}>Generate export</Button>
          {data && <><Button className="ml-2" variant="ghost" onClick={() => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type: "application/json" })); a.download = "nexora-my-data.json"; a.click(); }}>Download JSON</Button><CodeBlock className="mt-3 max-h-64">{data}</CodeBlock></>}</CardBody></Card>
      <Card className="border-danger/40"><CardHeader title="Delete my account" description="Your personal details are anonymised and you lose access to all organisations. Sole owners must transfer ownership or delete the organisation first." />
        <CardBody><Button variant="danger" onClick={() => setDel({ ...del, open: true })}>Delete account</Button></CardBody></Card>
      <Modal open={del.open} onClose={() => setDel({ ...del, open: false })} title="Delete account" description="Type DELETE and your password."
        footer={<><Button variant="ghost" onClick={() => setDel({ ...del, open: false })}>Cancel</Button><Button variant="danger" onClick={async () => { try { await api("/auth/me/delete", { body: { password: del.password, confirm: del.confirm }, noOrg: true }); session.setToken(null); router.push("/"); } catch (e) { toastError(e); } }}>Delete permanently</Button></>}>
        <div className="space-y-3"><Field label="Type DELETE"><Input value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} /></Field><Field label="Password"><Input type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} /></Field></div>
      </Modal>
    </div>
  );
}
