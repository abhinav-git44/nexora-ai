"use client";
import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Logo } from "@/components/app/logo";
import { Badge, Spinner } from "@/components/ui";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { ready, user } = useAuth();
  const router = useRouter();
  useEffect(() => { if (ready && !user) router.replace("/login?next=/admin"); }, [ready, user, router]);
  if (!ready || !user) return <div className="flex min-h-screen items-center justify-center"><Spinner className="h-6 w-6" /></div>;
  if (!user.is_super_admin) return <div className="flex min-h-screen flex-col items-center justify-center gap-2"><h1 className="text-lg font-semibold">404 — Not found</h1><Link href="/app" className="text-brand-text">Back to workspace</Link></div>;
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-6 backdrop-blur"><Logo /><Badge tone="danger">Platform admin</Badge><span className="flex-1" /><Link href="/app" className="text-[13px] text-subtle hover:text-fg">Exit to workspace</Link></header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>
    </div>
  );
}
