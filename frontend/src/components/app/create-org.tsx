"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { session } from "@/lib/api";
import { toastError } from "@/lib/hooks";
import { Button, Card, CardBody, Field, Input } from "@/components/ui";
import { Logo } from "./logo";

export function CreateOrgScreen() {
  const { reload, logout } = useAuth();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md"><CardBody className="space-y-4">
        <Logo />
        <h1 className="text-lg font-semibold">Create an organisation</h1>
        <p className="text-sm text-muted">You're not a member of any active organisation. Create one to get started.</p>
        <form className="space-y-3" onSubmit={async (e) => {
          e.preventDefault(); setBusy(true);
          try { const o = await api<{ id: string }>("/orgs", { body: { name }, noOrg: true }); session.setOrg(o.id); await reload(); }
          catch (err) { toastError(err); } finally { setBusy(false); }
        }}>
          <Field label="Organisation name"><Input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></Field>
          <div className="flex gap-2"><Button type="submit" loading={busy}>Create</Button><Button type="button" variant="ghost" onClick={logout}>Sign out</Button></div>
        </form>
      </CardBody></Card>
    </div>
  );
}
