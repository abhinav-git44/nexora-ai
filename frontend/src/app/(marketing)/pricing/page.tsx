"use client";
import { useState } from "react";
import useSWR from "swr";
import { Check } from "lucide-react";
import { Badge, ButtonLink, LoadingBlock, Segmented } from "@/components/ui";
import { cn } from "@/lib/utils";

type PlanRow = { key: string; name: string; price_usd: number | null; price_inr: number | null; seats_included: number | null; limits: Record<string, number>; features: string[] };
const HIGHLIGHTS: Record<string, string[]> = {
  free: ["150 AI messages / month", "10 documents", "1 agent · 1 workflow", "2 members · 1 workspace", "Basic analytics"],
  starter: ["2,000 AI messages / month", "200 documents · 5 GB", "5 agents · 10 workflows", "5 members · 3 workspaces", "Team collaboration"],
  professional: ["10,000 AI messages / month", "2,000 documents · 50 GB", "Advanced agents & workflow nodes", "Data intelligence (NL → SQL)", "Audit logs · team administration"],
  enterprise: ["Custom limits & SLAs", "Advanced permissions & SSO (roadmap)", "Audit export", "Custom integrations", "Priority support"],
};

export default function Pricing() {
  const [cur, setCur] = useState<"usd" | "inr">("usd");
  const { data } = useSWR<{ plans: PlanRow[] }>("/billing/plans");
  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Simple, usage-aware pricing</h1>
        <p className="mx-auto mt-3 max-w-xl text-muted">Every new workspace starts with a 14-day Professional trial, then continues on Free unless you choose a plan.</p>
        <div className="mt-6"><Segmented value={cur} onChange={setCur} options={[{ value: "usd", label: "USD" }, { value: "inr", label: "INR" }]} /></div>
      </div>
      {!data ? <div className="mt-10"><LoadingBlock rows={4} /></div> : (
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {data.plans.map((p) => {
            const price = cur === "usd" ? p.price_usd : p.price_inr;
            const featured = p.key === "professional";
            return (
              <div key={p.key} className={cn("flex flex-col rounded-2xl border bg-panel p-6 shadow-card", featured ? "border-brand ring-1 ring-brand" : "border-line")}>
                <div className="flex items-center justify-between"><h2 className="font-semibold">{p.name}</h2>{featured && <Badge tone="brand">Most popular</Badge>}</div>
                <div className="mt-4 text-3xl font-semibold tracking-tight">
                  {price === null ? "Custom" : price === 0 ? (cur === "usd" ? "$0" : "₹0") : `${cur === "usd" ? "$" : "₹"}${price.toLocaleString()}`}
                  {price ? <span className="text-sm font-normal text-subtle"> / month</span> : null}
                </div>
                {p.seats_included && <p className="mt-1 text-[12px] text-subtle">Up to {p.seats_included} members</p>}
                <ul className="mt-5 flex-1 space-y-2 text-[13.5px]">
                  {HIGHLIGHTS[p.key].map((h) => <li key={h} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-brand" />{h}</li>)}
                </ul>
                <ButtonLink href={p.key === "enterprise" ? "mailto:sales@example.com" : "/register"} variant={featured ? "primary" : "outline"} className="mt-6">
                  {p.key === "enterprise" ? "Contact sales" : p.key === "free" ? "Start free" : `Start with ${p.name}`}
                </ButtonLink>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-8 text-center text-[12px] text-subtle">Prices exclude taxes. AI usage beyond plan limits is blocked rather than billed, so there are no surprise invoices.</p>
    </div>
  );
}
