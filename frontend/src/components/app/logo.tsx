export function Logo({ className = "", withText = true }: { className?: string; withText?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#013d5a" />
        <rect x="4" y="25" width="24" height="3" rx="1.5" fill="#f4a258" />
        <path d="M9 21V9l14 12V9" stroke="#fcf3e3" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {withText && <span className="text-[15px] font-semibold tracking-tight">NEXORA<span className="text-brand"> AI</span></span>}
    </span>
  );
}
