"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Database, Lock, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { fmtNumber, timeAgo } from "@/lib/utils";
import { Badge, Button, ButtonLink, Card, EmptyState, LoadingBlock, PageHeader, Table, Td, Th, CardBody } from "@/components/ui";

type Ds = { id: string; name: string; filename: string; row_count: number; columns: { name: string }[]; created_at: string; recommendation_count: number };

export default function Data() {
  const router = useRouter();
  const { can, hasFeature } = useAuth();
  const list = useOrgSWR<Ds[]>("/datasets");
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  if (!hasFeature("data_intelligence")) {
    return (<div className="animate-in"><PageHeader title="Data intelligence" />
      <EmptyState icon={Lock} title="Available on Professional" description="Ask questions of CSV/XLSX data in plain English with validated, read-only SQL, charts and exports." action={can("billing.read") ? <ButtonLink href="/app/billing">View plans</ButtonLink> : undefined} /></div>);
  }
  return (
    <div className="animate-in">
      <PageHeader title="Data intelligence" description="Upload CSV or XLSX datasets and ask business questions. Every generated query is parsed, allow-listed and executed read-only with a timeout and row limit."
        actions={can("datasets.write") && <><input ref={ref} type="file" accept=".csv,.xlsx" className="hidden" onChange={async (e) => {
          const f = e.target.files?.[0]; if (!f) return; setBusy(true);
          const fd = new FormData(); fd.append("file", f);
          try { const d = await api<{ id: string }>("/datasets", { form: fd }); router.push(`/app/data/${d.id}`); } catch (er) { toastError(er); } finally { setBusy(false); e.target.value = ""; }
        }} /><Button onClick={() => ref.current?.click()} loading={busy}><Upload className="h-4 w-4" />Upload dataset</Button></>} />
      <Card>{list.isLoading ? <CardBody><LoadingBlock /></CardBody> : !list.data?.length ? <CardBody><EmptyState icon={Database} title="No datasets yet" description="Try a sales export, ticket log or pipeline report (first sheet of XLSX is used)." /></CardBody> : (
        <Table><thead><tr><Th>Dataset</Th><Th>Rows</Th><Th className="hidden sm:table-cell">Columns</Th><Th className="hidden md:table-cell">Data quality</Th><Th className="hidden sm:table-cell">Uploaded</Th></tr></thead>
          <tbody>{list.data.map((d) => (
            <tr key={d.id} className="hover:bg-panel-2"><Td><Link href={`/app/data/${d.id}`} className="font-medium hover:text-brand-text">{d.name}</Link><div className="text-[11.5px] text-subtle">{d.filename}</div></Td>
              <Td className="tabular-nums">{fmtNumber(d.row_count)}</Td><Td className="hidden sm:table-cell">{d.columns.length}</Td>
              <Td className="hidden md:table-cell">{d.recommendation_count ? <Badge tone="warning">{d.recommendation_count} suggestions</Badge> : <Badge tone="success">clean</Badge>}</Td>
              <Td className="hidden text-subtle sm:table-cell">{timeAgo(d.created_at)}</Td></tr>
          ))}</tbody></Table>
      )}</Card>
    </div>
  );
}
