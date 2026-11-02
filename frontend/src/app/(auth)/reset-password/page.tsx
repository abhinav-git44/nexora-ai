"use client";
import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Reset() {
  const token = useSearchParams().get("token") || "";
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <h1 className="text-lg font-semibold">Choose a new password</h1>
      {done ? <p className="mt-3 text-sm text-muted">Password updated. All other sessions were signed out. <Link href="/login" className="text-brand-text">Sign in</Link></p> : (
        <form className="mt-5 space-y-3.5" onSubmit={async (e) => {
          e.preventDefault(); setBusy(true); setErr(null);
          try { await api("/auth/reset-password", { body: { token, password }, noOrg: true }); setDone(true); }
          catch (e) { setErr(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); }
        }}>
          <Field label="New password" htmlFor="pw" hint="10+ characters with upper, lower case and a number"><Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} /></Field>
          {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>Update password</Button>
        </form>
      )}
    </>
  );
}
