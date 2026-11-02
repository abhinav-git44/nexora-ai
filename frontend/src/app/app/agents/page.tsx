"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bot, Plus, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { fmtPct, timeAgo } from "@/lib/utils";
import type { Agent } from "@/lib/types";
import { Badge, Button, Card, CardBody, EmptyState, LoadingBlock, PageHeader } from "@/components/ui";

type Template = { key: string; name: string; description: string; tools: string[]; model_route: string; approval_required_tools?: string[] };

export default function Agents() {
  const router = useRouter();
  const { can } = useAuth();
  const agents = useOrgSWR<Agent[]>("/agents");
  const templates = useOrgSWR<Template[]>("/agents/templates");
  const [busy, setBusy] = useState<string | null>(null);
  const create = async (key?: string) => {
    setBusy(key || "blank");
    try {
      const a = key ? await api<Agent>(`/agents/from-template/${key}`, { method: "POST" })
        : await api<Agent>("/agents", { body: { name: "Untitled agent", instructions: "Describe what this agent should do, step by step.", tools: ["search_knowledge"] } });
      router.push(`/app/agents/${a.id}${key ? "" : "?tab=config"}`);
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <div className="animate-in">
      <PageHeader title="Agent Studio" description="Single-purpose AI agents with allow-listed tools, budgets, logs and human approval for anything with side effects."
        actions={can("agents.write") && <Button onClick={() => create()} loading={busy === "blank"}><Plus className="h-4 w-4" />New agent</Button>} />
      <h2 className="mb-3 text-sm font-semibold">Your agents</h2>
      {agents.isLoading ? <LoadingBlock /> : !agents.data?.length ? (
        <EmptyState icon={Bot} title="No agents yet" description="Start from a template below — each one comes with sensible tools and guardrails." className="mb-8" />
      ) : (
        <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.data.map((a) => (
            <Link key={a.id} href={`/app/agents/${a.id}`} className="rounded-xl border border-line bg-panel p-4 shadow-card transition-colors hover:border-line-strong">
              <div className="flex items-center gap-2"><div className="rounded-lg bg-brand-soft p-1.5"><Bot className="h-4 w-4 text-brand" /></div><span className="flex-1 truncate font-medium">{a.name}</span></div>
              <p className="mt-2 line-clamp-2 text-[12.5px] text-subtle">{a.description || a.instructions}</p>
              <div className="mt-3 flex flex-wrap gap-1.5 text-[11.5px]">
                <Badge>{a.tools.length} tools</Badge><Badge>{a.runs ?? 0} runs</Badge>
                {a.success_rate !== null && a.success_rate !== undefined && <Badge tone={a.success_rate >= 0.8 ? "success" : "warning"}>{fmtPct(a.success_rate)} success</Badge>}
                {a.approval_required_tools.length > 0 && <Badge tone="warning">approval gated</Badge>}
                <span className="ml-auto text-subtle">{a.last_run_at ? timeAgo(a.last_run_at) : "never run"}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {can("agents.write") && (
        <>
          <h2 className="mb-3 text-sm font-semibold">Templates</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {templates.data?.map((t) => (
              <Card key={t.key} className="flex flex-col"><CardBody className="flex flex-1 flex-col">
                <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-brand" /><span className="font-medium">{t.name}</span></div>
                <p className="mt-2 flex-1 text-[12.5px] text-subtle">{t.description}</p>
                <div className="mt-3 flex flex-wrap gap-1">{t.tools.map((x) => <Badge key={x}>{x}</Badge>)}</div>
                <Button size="sm" variant="outline" className="mt-4" loading={busy === t.key} onClick={() => create(t.key)}>Use template</Button>
              </CardBody></Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
