"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CodeBlock, EmptyState, Input, LoadingBlock, PageHeader, Segmented, StatusBadge } from "@/components/ui";

type Approval = { id: string; source_type: string; source_id: string; title: string; details: any; status: string; required_role: string; requested_by: { full_name: string } | null; decision_note: string | null; decided_at: string | null; created_at: string };

export default function Approvals() {
  const { can } = useAuth();
  const [status, setStatus] = useState<"pending" | "all">("pending");
  const list = useOrgSWR<Approval[]>(`/approvals?status=${status}`, { refreshInterval: 10000 });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const decide = async (a: Approval, decision: "approved" | "rejected") => {
    try { await api(`/approvals/${a.id}/decide`, { body: { decision, note: notes[a.id] } }); toast.success(decision === "approved" ? "Approved — execution resumed" : "Rejected"); list.mutate(); }
    catch (e) { toastError(e); }
  };
  return (
    <div className="animate-in">
      <PageHeader title="Approvals" description="Human-in-the-loop checkpoints for sensitive agent actions and workflow approval steps."
        actions={<Segmented value={status} onChange={setStatus} options={[{ value: "pending", label: "Pending" }, { value: "all", label: "History" }]} />} />
      {list.isLoading ? <LoadingBlock /> : !list.data?.length ? <EmptyState icon={ShieldCheck} title={status === "pending" ? "Nothing awaiting approval" : "No approvals yet"} /> : (
        <div className="space-y-3">{list.data.map((a) => (
          <Card key={a.id}><CardBody>
            <div className="flex flex-wrap items-center gap-2"><StatusBadge status={a.status} /><Badge>{a.source_type === "agent_run" ? "Agent" : "Workflow"}</Badge>
              <span className="font-medium">{a.title}</span><span className="ml-auto text-[12px] text-subtle">{a.requested_by?.full_name ? `requested by ${a.requested_by.full_name} · ` : ""}{timeAgo(a.created_at)}</span></div>
            <CodeBlock className="mt-3 max-h-48">{JSON.stringify(a.details, null, 2)}</CodeBlock>
            {a.status === "pending" ? (can("approvals.decide") ? (
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <Input placeholder="Optional note for the audit log" value={notes[a.id] || ""} onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })} aria-label="Decision note" />
                <Button onClick={() => decide(a, "approved")}>Approve</Button><Button variant="outline" onClick={() => decide(a, "rejected")}>Reject</Button>
              </div>
            ) : <p className="mt-3 text-[12.5px] text-subtle">Requires a {a.required_role} or above to decide.</p>)
              : <p className="mt-3 text-[12.5px] text-subtle">{a.decision_note ? `Note: ${a.decision_note} · ` : ""}decided {timeAgo(a.decided_at)}</p>}
            <div className="mt-2 text-[12px]"><Link className="text-brand-text" href={a.source_type === "agent_run" ? `/app/agents/${a.details?.agent_id}?run=${a.source_id}` : `/app/workflows/${a.details?.workflow_id}?execution=${a.source_id}`}>View {a.source_type === "agent_run" ? "run" : "execution"} →</Link></div>
          </CardBody></Card>
        ))}</div>
      )}
    </div>
  );
}
