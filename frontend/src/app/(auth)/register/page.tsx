"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Register() {
  const { register } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const invite = params.get("invite");
  const [form, setForm] = useState({ full_name: "", email: params.get("email") || "", password: "", organization_name: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const strong = form.password.length >= 10 && /[a-z]/.test(form.password) && /[A-Z]/.test(form.password) && /\d/.test(form.password);
  return (
    <>
      <h1 className="text-lg font-semibold">{invite ? "Join your team" : "Create your workspace"}</h1>
      <p className="mt-1 text-[13px] text-subtle">{invite ? "Create an account to accept the invitation." : "14-day Professional trial. No card required."}</p>
      <form className="mt-5 space-y-3.5" onSubmit={async (e) => {
        e.preventDefault(); setErr(null); setBusy(true);
        try {
          await register({ ...form, organization_name: form.organization_name || undefined, invitation_token: invite || undefined });
          router.replace("/app?welcome=1");
        } catch (e) { setErr(e instanceof ApiError ? e.message : "Unable to create account"); } finally { setBusy(false); }
      }}>
        <Field label="Full name" htmlFor="name"><Input id="name" autoComplete="name" value={form.full_name} onChange={set("full_name")} required /></Field>
        <Field label="Work email" htmlFor="email"><Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} required readOnly={!!params.get("email")} /></Field>
        <Field label="Password" htmlFor="password" hint={form.password ? (strong ? "Strong password ✓" : "10+ characters with upper, lower case and a number") : "10+ characters with upper, lower case and a number"}>
          <Input id="password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} required minLength={10} />
        </Field>
        {!invite && <Field label="Company name" htmlFor="org" hint="You can change this later."><Input id="org" value={form.organization_name} onChange={set("organization_name")} placeholder="Acme Operations" /></Field>}
        {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
        <Button type="submit" className="w-full" loading={busy}>Create account</Button>
        <p className="text-[11.5px] text-subtle">By continuing you agree to processing of your account data to provide the service, as described in our privacy notice (DPDP Act 2023 / GDPR-aligned).</p>
      </form>
      <p className="mt-5 text-center text-[13px] text-subtle">Already have an account? <Link href="/login" className="font-medium text-brand-text">Sign in</Link></p>
    </>
  );
}
