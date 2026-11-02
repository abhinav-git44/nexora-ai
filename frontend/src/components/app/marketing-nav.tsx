"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { ButtonLink } from "@/components/ui";
import { Logo } from "./logo";

export function MarketingNav() {
  const { user } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" aria-label="NEXORA AI home"><Logo /></Link>
        <nav className="hidden gap-5 text-[13.5px] text-muted md:flex" aria-label="Marketing">
          <Link href="/#product" className="hover:text-fg">Product</Link>
          <Link href="/#security" className="hover:text-fg">Security</Link>
          <Link href="/pricing" className="hover:text-fg">Pricing</Link>
          <Link href="/#faq" className="hover:text-fg">FAQ</Link>
        </nav>
        <div className="flex-1" />
        {user ? <ButtonLink href="/app" size="sm">Open workspace</ButtonLink> : (
          <div className="flex items-center gap-2">
            <ButtonLink href="/login" variant="ghost" size="sm">Sign in</ButtonLink>
            <ButtonLink href="/register" size="sm">Start free</ButtonLink>
          </div>
        )}
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-10 text-[13px] text-subtle sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <Logo />
        <p>NEXORA AI is an independently designed and developed product. © {new Date().getFullYear()}</p>
        <div className="flex gap-4"><Link href="/pricing" className="hover:text-fg">Pricing</Link><Link href="/login" className="hover:text-fg">Sign in</Link></div>
      </div>
    </footer>
  );
}
