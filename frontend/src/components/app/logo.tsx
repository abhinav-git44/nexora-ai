export function Logo({ className = "", withText = true }: { className?: string; withText?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#5b5bd6" />
        <rect width="32" height="16" rx="8" fill="#7c7cf0" opacity="0.35" />
        <path d="M9 22V10l14 12V10" stroke="white" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {withText && <span className="text-[15px] font-semibold tracking-tight">NEXORA<span className="text-brand"> AI</span></span>}
    </span>
  );
}
