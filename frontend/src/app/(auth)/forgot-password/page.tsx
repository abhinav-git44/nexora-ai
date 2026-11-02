"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Forgot() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <h1 className="text-lg font-semibold">Reset your password</h1>
      {sent ? <p className="mt-3 text-sm text-muted">If an account exists for <b>{email}</b>, a reset link is on its way. It expires in 1 hour.</p> : (
        <form className="mt-5 space-y-3.5" onSubmit={async (e) => { e.preventDefault(); setBusy(true); await api("/auth/forgot-password", { body: { email }, noOrg: true }).catch(() => undefined); setBusy(false); setSent(true); }}>
          <Field label="Email" htmlFor="email"><Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></Field>
          <Button type="submit" className="w-full" loading={busy}>Send reset link</Button>
        </form>
      )}
      <p className="mt-5 text-center text-[13px]"><Link href="/login" className="text-brand-text">Back to sign in</Link></p>
    </>
  );
}
