"use client";
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center"><h1 className="text-lg font-semibold">Something went wrong</h1><p className="max-w-md text-sm text-muted">{error.message || "An unexpected error occurred."}{error.digest ? ` (ref ${error.digest})` : ""}</p><button onClick={reset} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-panel-2">Try again</button></div>;
}
