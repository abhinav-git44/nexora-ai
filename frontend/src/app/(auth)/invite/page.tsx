"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, session } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, ButtonLink, Spinner } from "@/components/ui";

type Inv = { email: string; role: string; organization: string; has_account: boolean };

export default function Invite() {
  const token = useSearchParams().get("token") || "";
  const { user, ready, reload } = useAuth();
  const router = useRouter();
  const [inv, setInv] = useState<Inv | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Inv>(`/invitations/lookup?token=${encodeURIComponent(token)}`, { noOrg: true }).then(setInv).catch((e) => setErr(e instanceof ApiError ? e.message : "Invalid invitation")); }, [token]);
  if (err) return <div className="text-center"><h1 className="text-lg font-semibold">Invitation unavailable</h1><p className="mt-2 text-sm text-danger">{err}</p></div>;
  if (!inv || !ready) return <div className="flex justify-center"><Spinner className="h-6 w-6" /></div>;
  return (
    <div>
      <h1 className="text-lg font-semibold">Join {inv.organization}</h1>
      <p className="mt-1 text-sm text-muted">You've been invited as <b>{inv.role}</b> ({inv.email}).</p>
      <div className="mt-5">
        {user ? (
          user.email === inv.email ? (
            <Button className="w-full" loading={busy} onClick={async () => {
              setBusy(true);
              try { const r = await api<{ org_id: string }>("/invitations/accept", { body: { token }, noOrg: true }); session.setOrg(r.org_id); await reload(); router.push("/app"); }
              catch (e) { setErr(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); }
            }}>Accept invitation</Button>
          ) : <p className="text-sm text-danger">You're signed in as {user.email}. Sign out and use {inv.email} to accept.</p>
        ) : inv.has_account ? <ButtonLink href={`/login?next=${encodeURIComponent(`/invite?token=${token}`)}`} className="w-full">Sign in to accept</ButtonLink>
          : <ButtonLink href={`/register?invite=${token}&email=${encodeURIComponent(inv.email)}`} className="w-full">Create account & join</ButtonLink>}
      </div>
      <p className="mt-4 text-center text-[12px] text-subtle"><Link href="/">What is NEXORA?</Link></p>
    </div>
  );
}
