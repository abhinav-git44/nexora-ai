"use client";
import useSWR, { type SWRConfiguration } from "swr";
import { toast } from "sonner";
import { ApiError } from "./api";
import { useAuth } from "./auth";

/** Org-scoped SWR: the key includes the org id so switching organisations never shows stale tenant data. */
export function useOrgSWR<T>(path: string | null, cfg?: SWRConfiguration<T>) {
  const { org } = useAuth();
  return useSWR<T>(path && org ? [path, org.id] : null, ([p]: [string]) => import("./api").then((m) => m.api<T>(p)), cfg);
}

export function toastError(e: unknown, fallback = "Something went wrong") {
  if (e instanceof ApiError) {
    if (e.code === "plan_limit_reached") {
      toast.error(e.message, { action: { label: "Upgrade", onClick: () => (window.location.href = "/app/billing") } });
      return;
    }
    toast.error(e.message);
  } else toast.error(fallback);
}
