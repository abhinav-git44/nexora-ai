"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"pending" | "ok" | "error">("pending");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!token) { setState("error"); setMsg("Missing verification token."); return; }
    api("/auth/verify-email/confirm", { body: { token }, noOrg: true }).then(() => setState("ok")).catch((e) => { setState("error"); setMsg(e instanceof ApiError ? e.message : "Verification failed"); });
  }, [token]);
  return (
    <div className="text-center">
      {state === "pending" && <><Spinner className="mx-auto h-6 w-6" /><p className="mt-3 text-sm text-muted">Verifying your email…</p></>}
      {state === "ok" && <><h1 className="text-lg font-semibold">Email verified</h1><p className="mt-2 text-sm text-muted">You can now invite teammates.</p><Link href="/app" className="mt-4 inline-block text-brand-text">Go to workspace →</Link></>}
      {state === "error" && <><h1 className="text-lg font-semibold">Couldn't verify</h1><p className="mt-2 text-sm text-danger">{msg}</p><Link href="/app" className="mt-4 inline-block text-brand-text">Go to workspace</Link></>}
    </div>
  );
}
