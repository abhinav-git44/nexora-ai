"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Login() {
  const { login, user, ready } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next") || "/app";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: providers } = useSWR<{ google: boolean }>("/auth/providers");
  useEffect(() => { if (ready && user) router.replace(next.startsWith("/") ? next : "/app"); }, [ready, user, next, router]);
  return (
    <>
      <h1 className="text-lg font-semibold">Sign in to NEXORA</h1>
      <p className="mt-1 text-[13px] text-subtle">Welcome back. Enter your work email to continue.</p>
      <form className="mt-5 space-y-3.5" onSubmit={async (e) => {
        e.preventDefault(); setErr(null); setBusy(true);
        try { await login(email, password); router.replace(next.startsWith("/") ? next : "/app"); }
        catch (e) { setErr(e instanceof ApiError ? e.message : "Unable to sign in"); } finally { setBusy(false); }
      }}>
        <Field label="Email" htmlFor="email"><Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></Field>
        <Field label="Password" htmlFor="password" hint={<Link href="/forgot-password" className="text-brand-text">Forgot password?</Link>}>
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
        <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
      </form>
      {providers?.google && (
        <Button variant="outline" className="mt-3 w-full" onClick={async () => { const r = await api<{ url: string }>("/auth/oauth/google/start", { noOrg: true }); window.location.href = r.url; }}>Continue with Google</Button>
      )}
      <p className="mt-5 text-center text-[13px] text-subtle">New to NEXORA? <Link href="/register" className="font-medium text-brand-text">Create an account</Link></p>
    </>
  );
}
