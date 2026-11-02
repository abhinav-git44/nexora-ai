"use client";
import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Plug, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toastError, useOrgSWR } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";
import { Badge, Button, Callout, Card, CardBody, Field, Input, LoadingBlock, Modal, PageHeader, StatusBadge } from "@/components/ui";

type Integration = { key: string; name: string; category: string; auth: string; description: string; status: string; scopes: string[]; oauth?: string; fields: { key: string; label: string; secret?: boolean }[];
  connection: { status: string; last_tested_at: string | null; last_error: string | null; credentials: Record<string, string>; scopes: string[] } | null };

export default function Integrations() {
  const { can } = useAuth();
  const list = useOrgSWR<Integration[]>("/integrations");
  const [sel, setSel] = useState<Integration | null>(null);
  const cats = Array.from(new Set(list.data?.map((i) => i.category) || []));
  return (
    <div className="animate-in">
      <PageHeader title="Integrations" description="An integration shows as connected only after a real, successful test call to the provider. Credentials are encrypted at rest and never returned to the browser." />
      {!list.data ? <LoadingBlock rows={6} /> : cats.map((c) => (
        <section key={c} className="mb-8">
          <h2 className="mb-3 text-sm font-semibold">{c}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{list.data!.filter((i) => i.category === c).map((i) => (
            <Card key={i.key}><CardBody>
              <div className="flex items-center gap-2"><div className="rounded-lg bg-panel-2 p-1.5"><Plug className="h-4 w-4 text-subtle" /></div><span className="flex-1 font-medium">{i.name}</span>
                {i.connection ? <StatusBadge status={i.connection.status} /> : i.status === "coming_soon" ? <Badge>coming soon</Badge> : i.status === "requires_config" ? <Badge tone="warning">needs server config</Badge> : i.status === "beta" ? <Badge tone="info">beta</Badge> : null}</div>
              <p className="mt-2 min-h-10 text-[12.5px] text-subtle">{i.description}</p>
              {i.connection?.last_error && <p className="mt-1 text-[12px] text-danger">{i.connection.last_error}</p>}
              <div className="mt-3 flex items-center gap-2">
                {can("integrations.manage") && i.status !== "coming_soon" && <Button size="sm" variant={i.connection?.status === "connected" ? "outline" : "primary"} onClick={() => setSel(i)}>{i.connection?.status === "connected" ? "Manage" : "Connect"}</Button>}
                {i.connection?.last_tested_at && <span className="text-[11.5px] text-subtle">tested {timeAgo(i.connection.last_tested_at)}</span>}
              </div>
            </CardBody></Card>
          ))}</div>
        </section>
      ))}
      {sel && <ConnectModal i={sel} onClose={() => setSel(null)} onDone={() => list.mutate()} />}
    </div>
  );
}

function ConnectModal({ i, onClose, onDone }: { i: Integration; onClose: () => void; onDone: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [logs, setLogs] = useState<{ action: string; status: string; message: string; created_at: string }[] | null>(null);
  const conn = i.connection;
  const act = async (name: string, fn: () => Promise<Integration>) => {
    setBusy(name);
    try { const r = await fn(); onDone(); r.connection?.status === "connected" ? toast.success(`${i.name}: connection verified`) : toast.error(`${i.name}: ${r.connection?.last_error || "not connected"}`); if (name !== "test") onClose(); }
    catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <Modal open onClose={onClose} title={`${i.name} integration`} description={`Scopes: ${i.scopes.join(", ")}`}
      footer={<>
        {conn && conn.status !== "disconnected" && <Button variant="ghost" className="mr-auto text-danger" loading={busy === "dc"} onClick={() => act("dc", () => api(`/integrations/${i.key}`, { method: "DELETE" }))}>Disconnect & revoke</Button>}
        {conn && conn.status !== "disconnected" && <Button variant="outline" loading={busy === "test"} onClick={() => act("test", () => api(`/integrations/${i.key}/test`, { method: "POST" }))}>Test connection</Button>}
        {i.auth === "oauth" || i.oauth ? <Button onClick={async () => { try { const r = await api<{ url: string }>(`/integrations/${i.key}/oauth/start`); window.location.href = r.url; } catch (e) { toastError(e); } }}>Connect with OAuth</Button> : null}
        {i.fields.length > 0 && <Button loading={busy === "save"} onClick={() => act("save", () => api(`/integrations/${i.key}/connect`, { body: { credentials: vals } }))}>Save & verify</Button>}
      </>}>
      <div className="space-y-3">
        {conn && <div className="flex items-center gap-2 text-[13px]">{conn.status === "connected" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-danger" />}<span className="capitalize">{conn.status}</span>
          {Object.entries(conn.credentials).map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}</div>}
        {i.fields.map((f) => <Field key={f.key} label={f.label}><Input type={f.secret ? "password" : "text"} autoComplete="off" value={vals[f.key] || ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} placeholder={conn ? "Leave blank to keep current" : ""} /></Field>)}
        {i.key === "n8n" && <Callout tone="info" title="How NEXORA uses n8n">NEXORA owns workflow definitions, permissions and run history. The “Run n8n workflow” node calls your n8n webhook (base URL + /webhook/&lt;path&gt;) so you can reuse n8n’s connector library.</Callout>}
        {(i.key === "openai" || i.key === "anthropic") && <Callout tone="info" title="Bring your own key">Workspace keys are stored encrypted. Server-level keys configured by the operator are used when no workspace key exists.</Callout>}
        <button className="text-[12px] text-brand-text" onClick={async () => setLogs(await api(`/integrations/${i.key}/logs`))}>View integration logs</button>
        {logs && <ul className="max-h-40 space-y-1 overflow-y-auto text-[12px]">{logs.length ? logs.map((l, j) => <li key={j}><StatusBadge status={l.status === "success" ? "succeeded" : "failed"} label={l.action} /> <span className="text-subtle">{l.message} · {timeAgo(l.created_at)}</span></li>) : <li className="text-subtle">No logs.</li>}</ul>}
      </div>
    </Modal>
  );
}
