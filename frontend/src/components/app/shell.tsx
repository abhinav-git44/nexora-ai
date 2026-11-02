"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Bell, Bot, BarChart3, BookOpen, CheckSquare, ChevronsUpDown, CreditCard, Database, Home, LogOut, Menu as MenuIcon, MessageSquare,
  Moon, Plug, Settings, Shield, ShieldCheck, Sun, Workflow, X, Laptop,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { api } from "@/lib/api";
import { useOrgSWR } from "@/lib/hooks";
import { cn, timeAgo } from "@/lib/utils";
import { Avatar, Badge, Button, Menu, MenuItem } from "@/components/ui";
import { Logo } from "./logo";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; perm?: string };
const NAV: { group: string; items: NavItem[] }[] = [
  { group: "", items: [{ href: "/app", label: "Home", icon: Home }] },
  { group: "Work", items: [
    { href: "/app/assistant", label: "Assistant", icon: MessageSquare, perm: "chat.use" },
    { href: "/app/knowledge", label: "Knowledge", icon: BookOpen, perm: "documents.read" },
    { href: "/app/agents", label: "Agents", icon: Bot, perm: "agents.read" },
    { href: "/app/workflows", label: "Workflows", icon: Workflow, perm: "workflows.read" },
    { href: "/app/data", label: "Data", icon: Database, perm: "datasets.read" },
    { href: "/app/tasks", label: "Tasks", icon: CheckSquare, perm: "tasks.read" },
  ] },
  { group: "Insights", items: [
    { href: "/app/analytics", label: "Analytics", icon: BarChart3, perm: "analytics.read" },
    { href: "/app/approvals", label: "Approvals", icon: ShieldCheck, perm: "agents.read" },
  ] },
  { group: "Workspace", items: [
    { href: "/app/integrations", label: "Integrations", icon: Plug, perm: "integrations.read" },
    { href: "/app/billing", label: "Billing", icon: CreditCard, perm: "billing.read" },
    { href: "/app/settings", label: "Settings", icon: Settings },
  ] },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const { can, org, orgs, switchOrg } = useAuth();
  const { data: approvals } = useOrgSWR<{ id: string }[]>(can("agents.read") ? "/approvals?status=pending" : null, { refreshInterval: 30000 });
  return (
    <nav className="flex h-full flex-col gap-1 px-3 py-4" aria-label="Main">
      <div className="mb-3 px-2"><Link href="/app" onClick={onNavigate}><Logo /></Link></div>
      <Menu align="left" trigger={({ toggle }) => (
        <button onClick={toggle} className="mb-3 flex w-full items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-2 text-left hover:bg-panel-2" aria-label="Switch organisation">
          <Avatar name={org?.name} size={22} className="rounded-md" />
          <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium">{org?.name}</span>
            <span className="block text-[11px] capitalize text-subtle">{org?.role} · {org?.plan.name}</span></span>
          <ChevronsUpDown className="h-3.5 w-3.5 text-subtle" />
        </button>
      )}>
        <div className="px-2.5 py-1 text-[11px] font-medium uppercase text-subtle">Organisations</div>
        {orgs.map((o) => <MenuItem key={o.id} onClick={() => switchOrg(o.id)}><span className="flex-1 truncate">{o.name}</span>{o.id === org?.id && <Badge tone="brand">current</Badge>}</MenuItem>)}
        <div className="my-1 border-t border-line" />
        <MenuItem href="/app/settings/organisation?new=1">Create organisation</MenuItem>
      </Menu>
      {NAV.map((g) => {
        const items = g.items.filter((i) => !i.perm || can(i.perm));
        if (!items.length) return null;
        return (
          <div key={g.group} className="mb-2">
            {g.group && <div className="px-2.5 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-subtle">{g.group}</div>}
            {items.map((i) => {
              const active = i.href === "/app" ? path === "/app" : path.startsWith(i.href);
              return (
                <Link key={i.href} href={i.href} onClick={onNavigate} aria-current={active ? "page" : undefined}
                  className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13.5px] transition-colors", active ? "bg-panel-2 font-medium text-fg" : "text-muted hover:bg-panel-2 hover:text-fg")}>
                  <i.icon className={cn("h-4 w-4", active ? "text-brand" : "text-subtle")} />
                  <span className="flex-1">{i.label}</span>
                  {i.href === "/app/approvals" && approvals && approvals.length > 0 && <Badge tone="warning">{approvals.length}</Badge>}
                </Link>
              );
            })}
          </div>
        );
      })}
      <div className="mt-auto rounded-xl border border-line bg-panel p-3 text-[12px] text-subtle">
        {org?.plan.status === "trialing" && org.plan.trial_ends_at ? (
          <>Professional trial ends <b className="text-fg">{new Date(org.plan.trial_ends_at).toLocaleDateString()}</b>.{" "}
            {can("billing.read") && <Link href="/app/billing" className="text-brand-text underline">Choose a plan</Link>}</>
        ) : <>Plan: <b className="text-fg">{org?.plan.name}</b></>}
      </div>
    </nav>
  );
}

type Notif = { id: string; type: string; title: string; body: string | null; link: string | null; read: boolean; created_at: string };

function Notifications() {
  const router = useRouter();
  const { data, mutate } = useOrgSWR<{ unread: number; items: Notif[] }>("/notifications?limit=12", { refreshInterval: 30000 });
  return (
    <Menu trigger={({ toggle }) => (
      <button onClick={toggle} className="relative rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-fg" aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ""}`}>
        <Bell className="h-4 w-4" />
        {!!data?.unread && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-danger" />}
      </button>
    )}>
      <div className="w-[min(360px,calc(100vw-2rem))]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-2.5 py-1.5">
          <span className="text-[13px] font-semibold">Notifications</span>
          {!!data?.unread && <button className="text-[12px] text-brand-text" onClick={async () => { await api("/notifications/read-all", { method: "POST" }); mutate(); }}>Mark all read</button>}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {!data?.items.length && <p className="px-2.5 py-6 text-center text-[13px] text-subtle">You're all caught up.</p>}
          {data?.items.map((n) => (
            <button key={n.id} className="flex w-full gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-panel-2"
              onClick={async () => { await api(`/notifications/${n.id}/read`, { method: "POST" }); mutate(); if (n.link) router.push(n.link); }}>
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-brand")} />
              <span className="min-w-0 flex-1"><span className="block text-[13px] text-fg">{n.title}</span>
                {n.body && <span className="block truncate text-[12px] text-subtle">{n.body}</span>}
                <span className="text-[11px] text-subtle">{timeAgo(n.created_at)}</span></span>
            </button>
          ))}
        </div>
        <div className="border-t border-line px-2.5 py-1.5"><Link href="/app/notifications" className="text-[12px] text-brand-text">View all & preferences</Link></div>
      </div>
    </Menu>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Laptop;
  return <button onClick={() => setTheme(next)} className="rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-fg" aria-label={`Theme: ${theme}. Switch to ${next}`}><Icon className="h-4 w-4" /></button>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, org, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setOpen(false), [path]);
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 overflow-y-auto border-r border-line bg-canvas lg:block"><Sidebar /></aside>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="animate-in absolute inset-y-0 left-0 w-72 overflow-y-auto border-r border-line bg-canvas">
            <button className="absolute right-3 top-4 rounded-md p-1 text-subtle" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-4 w-4" /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-line bg-canvas/85 px-4 backdrop-blur sm:px-6">
          <button className="rounded-lg p-2 text-muted hover:bg-panel-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><MenuIcon className="h-5 w-5" /></button>
          <div className="lg:hidden"><Logo withText={false} /></div>
          <div className="flex-1" />
          <ThemeToggle />
          <Notifications />
          <Menu trigger={({ toggle }) => (
            <button onClick={toggle} className="flex items-center gap-2 rounded-lg p-1 hover:bg-panel-2" aria-label="Account menu"><Avatar name={user?.full_name} size={28} /></button>
          )}>
            <div className="px-2.5 py-2"><div className="text-[13px] font-medium">{user?.full_name}</div><div className="text-[12px] text-subtle">{user?.email}</div></div>
            <div className="my-1 border-t border-line" />
            <MenuItem href="/app/settings" icon={Settings}>Settings</MenuItem>
            {user?.is_super_admin && <MenuItem href="/admin" icon={Shield}>Admin console</MenuItem>}
            <MenuItem onClick={logout} icon={LogOut}>Sign out</MenuItem>
          </Menu>
        </header>
        {user && !user.email_verified && <VerifyBanner />}
        {org?.deletion_requested_at && (
          <div className="border-b border-danger/30 bg-danger-soft px-6 py-2 text-[13px] text-danger">This organisation is scheduled for permanent deletion. An owner can cancel in Settings → Organisation.</div>
        )}
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

function VerifyBanner() {
  const [sent, setSent] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-brand-soft px-6 py-2 text-[13px] text-brand-text">
      Verify your email to invite teammates.
      <Button size="sm" variant="ghost" disabled={sent} onClick={async () => { await api("/auth/verify-email/request", { method: "POST", noOrg: true }); setSent(true); toast.success("Verification email sent"); }}>
        {sent ? "Email sent" : "Resend link"}
      </Button>
    </div>
  );
}
