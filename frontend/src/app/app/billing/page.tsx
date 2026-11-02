"use client";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";
import { Check, Info } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { cn, fmtDate, titleCase } from "@/lib/utils";
import { Badge, Button, Callout, Card, CardBody, CardHeader, LoadingBlock, PageHeader, Progress, Segmented, StatusBadge, Table, Td, Th } from "@/components/ui";

type PlanRow = { key: string; name: string; price_usd: number | null; price_inr: number | null; seats_included: number | null };
type Sub = { plan: string; plan_name: string; status: string; provider: string; trial_ends_at: string | null; current_period_end: string | null; cancel_at_period_end: boolean; billing_mode: string; usage: Record<string, { used: number; limit: number }> };

export default function Billing() {
  const { can, reload } = useAuth();
  const sub = useOrgSWR<Sub>("/billing/subscription");
  const plans = useSWR<{ plans: PlanRow[] }>("/billing/plans");
  const invoices = useOrgSWR<{ id: string; number: string; amount: number; currency: string; status: string; description: string; created_at: string; hosted_url: string | null }[]>("/billing/invoices");
  const [cur, setCur] = useState<"usd" | "inr">("usd");
  const [busy, setBusy] = useState<string | null>(null);
  if (!sub.data || !plans.data) return <LoadingBlock rows={6} />;
  const s = sub.data;
  const change = async (plan: string) => {
    setBusy(plan);
    try {
      const r = await api<{ checkout_url?: string }>("/billing/change-plan", { body: { plan, currency: cur } });
      if (r.checkout_url) { window.location.href = r.checkout_url; return; }
      toast.success(`Plan changed to ${titleCase(plan)}`); sub.mutate(); invoices.mutate(); reload();
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <div className="animate-in">
      <PageHeader title="Billing & usage" description="Plan, metered usage and invoices for this organisation." />
      {s.billing_mode === "demo" && <div className="mb-5"><Callout tone="warning" icon={Info} title="Demo billing mode">No payment provider is configured on this server, so plan changes take effect immediately and generate demo invoices. No card is charged. Configure STRIPE_SECRET_KEY to enable real checkout.</Callout></div>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card><CardHeader title="Current plan" />
          <CardBody className="space-y-2 text-[13px]">
            <div className="flex items-center gap-2"><span className="text-xl font-semibold">{s.plan_name}</span><StatusBadge status={s.status} /></div>
            {s.trial_ends_at && <p className="text-subtle">Trial ends {fmtDate(s.trial_ends_at)} — then the workspace moves to Free unless you choose a plan.</p>}
            {s.current_period_end && <p className="text-subtle">{s.cancel_at_period_end ? "Cancels" : "Renews"} {fmtDate(s.current_period_end)}</p>}
            <p className="text-subtle">Billing: {s.provider === "none" ? "—" : s.provider}</p>
            {can("billing.manage") && s.plan !== "free" && s.status !== "trialing" && (s.cancel_at_period_end
              ? <Button size="sm" variant="outline" onClick={async () => { await api("/billing/resume", { method: "POST" }); sub.mutate(); }}>Resume subscription</Button>
              : <Button size="sm" variant="ghost" className="text-danger" onClick={async () => { if (!confirm("Cancel at the end of the period?")) return; await api("/billing/cancel", { method: "POST" }); sub.mutate(); }}>Cancel subscription</Button>)}
            {s.billing_mode === "stripe" && can("billing.manage") && <Button size="sm" variant="outline" onClick={async () => { const r = await api<{ url: string }>("/billing/portal", { method: "POST" }); window.location.href = r.url; }}>Manage payment method</Button>}
          </CardBody></Card>
        <Card className="lg:col-span-2"><CardHeader title="Usage this period" description="Monthly metrics reset on the 1st (UTC). Hitting a limit blocks the action — it never creates overage charges." />
          <CardBody className="grid gap-4 sm:grid-cols-2">{Object.entries(s.usage).map(([m, u]) => (
            <div key={m}><div className="mb-1 flex justify-between text-[12.5px]"><span>{titleCase(m)}</span><span className="tabular-nums text-subtle">{u.used.toLocaleString()} / {u.limit === -1 ? "∞" : u.limit.toLocaleString()}</span></div>
              {u.limit !== -1 && <Progress value={u.used} max={u.limit} />}</div>
          ))}</CardBody></Card>
      </div>
      <div className="mb-3 mt-8 flex items-center justify-between"><h2 className="text-sm font-semibold">Plans</h2><Segmented value={cur} onChange={setCur} options={[{ value: "usd", label: "USD" }, { value: "inr", label: "INR" }]} /></div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">{plans.data.plans.map((p) => {
        const price = cur === "usd" ? p.price_usd : p.price_inr; const current = p.key === s.plan && s.status !== "trialing";
        return (
          <Card key={p.key} className={cn(current && "ring-1 ring-brand")}><CardBody>
            <div className="flex items-center justify-between"><span className="font-semibold">{p.name}</span>{current && <Badge tone="brand">current</Badge>}</div>
            <div className="mt-2 text-2xl font-semibold">{price === null ? "Custom" : `${cur === "usd" ? "$" : "₹"}${price.toLocaleString()}`}<span className="text-[12px] font-normal text-subtle">{price ? " /mo" : ""}</span></div>
            {can("billing.manage") ? (p.key === "enterprise" ? <Button size="sm" variant="outline" className="mt-3 w-full" onClick={() => (window.location.href = "mailto:sales@example.com")}>Contact sales</Button>
              : <Button size="sm" variant={current ? "secondary" : "primary"} className="mt-3 w-full" disabled={current} loading={busy === p.key} onClick={() => change(p.key)}>{current ? <><Check className="h-4 w-4" />Current plan</> : "Switch"}</Button>)
              : <p className="mt-3 text-[12px] text-subtle">Only owners can change plans.</p>}
          </CardBody></Card>
        );
      })}</div>
      <Card className="mt-8"><CardHeader title="Invoices" />
        {!invoices.data?.length ? <CardBody><p className="text-sm text-subtle">No invoices yet.</p></CardBody> : (
          <Table><thead><tr><Th>Number</Th><Th>Description</Th><Th>Amount</Th><Th>Status</Th><Th>Date</Th></tr></thead>
            <tbody>{invoices.data.map((i) => <tr key={i.id}><Td className="font-mono text-[12px]">{i.hosted_url ? <a href={i.hosted_url} className="text-brand-text underline" target="_blank" rel="noreferrer">{i.number}</a> : i.number}</Td><Td>{i.description}</Td>
              <Td className="tabular-nums">{i.currency === "inr" ? "₹" : "$"}{i.amount.toLocaleString()}</Td><Td><StatusBadge status={i.status} /></Td><Td className="text-subtle">{fmtDate(i.created_at)}</Td></tr>)}</tbody></Table>
        )}</Card>
    </div>
  );
}
