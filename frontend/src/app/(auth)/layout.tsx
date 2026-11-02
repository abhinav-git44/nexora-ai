import Link from "next/link";
import { Suspense } from "react";
import { Logo } from "@/components/app/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[radial-gradient(ellipse_60%_40%_at_50%_0%,var(--brand-soft),transparent)] px-4 py-10">
      <Link href="/" className="mb-8" aria-label="NEXORA AI home"><Logo /></Link>
      <div className="w-full max-w-[400px] rounded-2xl border border-line bg-panel p-6 shadow-pop sm:p-7"><Suspense>{children}</Suspense></div>
    </div>
  );
}
