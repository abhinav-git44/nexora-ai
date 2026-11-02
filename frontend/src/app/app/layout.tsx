"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/app/shell";
import { Spinner } from "@/components/ui";
import { CreateOrgScreen } from "@/components/app/create-org";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { ready, user, org } = useAuth();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [ready, user, router, path]);
  if (!ready || !user) return <div className="flex min-h-screen items-center justify-center"><Spinner className="h-6 w-6" /></div>;
  if (!org) return <CreateOrgScreen />;
  return <AppShell>{children}</AppShell>;
}
