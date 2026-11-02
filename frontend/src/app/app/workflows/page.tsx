"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Plus, Workflow as WfIcon, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";
import { Badge, Button, Card, CardBody, EmptyState, LoadingBlock, PageHeader, StatusBadge, Table, Td, Th } from "@/components/ui";

type WfRow = { id: string; name: string; description: string; status: string; trigger_type: string; published_version: number | null; executions: number; succeeded: number; failed: number; last_run_at: string | null; updated_at: string };
type Tpl = { key: string; name: string; description: string };

export default function Workflows() {
  const router = useRouter();
  const { can } = useAuth();
  const list = useOrgSWR<WfRow[]>("/workflows");
  const tpls = useOrgSWR<Tpl[]>("/workflows/templates");
  const [busy, setBusy] = useState<string | null>(null);
  const create = async (key?: string) => {
    setBusy(key || "blank");
    try {
      const w = key ? await api<{ id: string }>(`/workflows/from-template/${key}`, { method: "POST" }) : await api<{ id: string }>("/workflows", { body: { name: "Untitled workflow" } });
      router.push(`/app/workflows/${w.id}`);
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <div className="animate-in">
      <PageHeader title="Workflows" description="Visual automations owned by NEXORA: versioned definitions, permissioned runs and full execution history. Call n8n from any workflow when you need its connector library."
        actions={can("workflows.write") && <Button onClick={() => create()} loading={busy === "blank"}><Plus className="h-4 w-4" />New workflow</Button>} />
      <Card className="mb-8">
        {list.isLoading ? <CardBody><LoadingBlock /></CardBody> : !list.data?.length ? <CardBody><EmptyState icon={WfIcon} title="No workflows yet" description="Start from a recipe below or build from scratch." /></CardBody> : (
          <Table><thead><tr><Th>Name</Th><Th>Status</Th><Th className="hidden sm:table-cell">Trigger</Th><Th className="hidden md:table-cell">Runs</Th><Th className="hidden md:table-cell">Success</Th><Th className="hidden lg:table-cell">Last run</Th></tr></thead>
            <tbody>{list.data.map((w) => (
              <tr key={w.id} className="hover:bg-panel-2">
                <Td><Link href={`/app/workflows/${w.id}`} className="font-medium hover:text-brand-text">{w.name}</Link>{w.published_version && <span className="ml-2 text-[11.5px] text-subtle">v{w.published_version}</span>}</Td>
                <Td><StatusBadge status={w.status} /></Td><Td className="hidden capitalize sm:table-cell">{w.trigger_type.replace("_", " ")}</Td>
                <Td className="hidden tabular-nums md:table-cell">{w.executions}</Td>
                <Td className="hidden md:table-cell">{w.executions ? <span className={w.failed ? "text-warning" : "text-success"}>{w.succeeded}/{w.succeeded + w.failed}</span> : "—"}</Td>
                <Td className="hidden text-subtle lg:table-cell">{w.last_run_at ? timeAgo(w.last_run_at) : "never"}</Td>
              </tr>))}</tbody></Table>
        )}
      </Card>
      {can("workflows.write") && <>
        <h2 className="mb-3 text-sm font-semibold">Recipes</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{tpls.data?.map((t) => (
          <Card key={t.key} className="flex flex-col"><CardBody className="flex flex-1 flex-col">
            <div className="flex items-center gap-2"><Zap className="h-4 w-4 text-brand" /><span className="font-medium">{t.name}</span></div>
            <p className="mt-2 flex-1 text-[12.5px] text-subtle">{t.description}</p>
            <Button size="sm" variant="outline" className="mt-4" loading={busy === t.key} onClick={() => create(t.key)}>Use recipe</Button>
          </CardBody></Card>
        ))}</div>
        <p className="mt-4 text-[12px] text-subtle"><Badge>Tip</Badge> Workflows run with the permissions of the person who triggers them (or the creator for automatic triggers).</p>
      </>}
    </div>
  );
}
