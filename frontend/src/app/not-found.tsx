import Link from "next/link";
export default function NotFound() {
  return <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center"><h1 className="text-xl font-semibold">Page not found</h1><p className="text-sm text-muted">The page you're looking for doesn't exist or you don't have access.</p><Link href="/app" className="mt-2 text-brand-text">Go to workspace →</Link></div>;
}
