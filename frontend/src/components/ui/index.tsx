"use client";
import { cloneElement, forwardRef, isValidElement, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Inbox, Loader2, X } from "lucide-react";
import { cn, initials } from "@/lib/utils";

/* ---------------- Button ---------------- */
type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type BtnSize = "sm" | "md" | "lg" | "icon";
const btnBase = "inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap select-none";
const btnVariants: Record<BtnVariant, string> = {
  primary: "bg-brand text-brand-fg hover:bg-brand-hover shadow-card",
  secondary: "bg-panel-2 text-fg hover:bg-line border border-line",
  outline: "border border-line-strong bg-panel text-fg hover:bg-panel-2",
  ghost: "text-muted hover:text-fg hover:bg-panel-2",
  danger: "bg-danger text-white hover:opacity-90",
};
const btnSizes: Record<BtnSize, string> = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-4 text-sm", lg: "h-11 px-5 text-[15px]", icon: "h-8 w-8" };

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: BtnSize; loading?: boolean };
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...p }, ref) {
  return (
    <button ref={ref} className={cn(btnBase, btnVariants[variant], btnSizes[size], className)} disabled={disabled || loading} {...p}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function ButtonLink({ href, variant = "primary", size = "md", className, children, ...p }: { href: string; variant?: BtnVariant; size?: BtnSize; className?: string; children: React.ReactNode } & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return <Link href={href} className={cn(btnBase, btnVariants[variant], btnSizes[size], className)} {...p}>{children}</Link>;
}

/* ---------------- Form controls ---------------- */
const fieldCls = "w-full rounded-lg border border-line-strong bg-panel px-3 text-sm text-fg placeholder:text-subtle focus:border-brand focus:outline-none focus:ring-2 focus:ring-[var(--ring)] disabled:opacity-60";
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(fieldCls, "h-9", className)} {...p} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={cn(fieldCls, "py-2 min-h-[80px] resize-y", className)} {...p} />;
});
export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...p }, ref) {
  return <select ref={ref} className={cn(fieldCls, "h-9 pr-8", className)} {...p}>{children}</select>;
});

export function Field({ label, hint, error, children, htmlFor, className }: { label?: string; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; htmlFor?: string; className?: string }) {
  const auto = useId();
  // Associate the label with its control automatically (a11y + testability) unless an explicit id is supplied.
  const childId = isValidElement<{ id?: string }>(children) ? children.props.id : undefined;
  const id = htmlFor || childId || auto;
  const control = isValidElement<{ id?: string }>(children) && !childId && !htmlFor ? cloneElement(children, { id }) : children;
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && <label htmlFor={id} className="block text-[13px] font-medium text-fg">{label}</label>}
      {control}
      {error ? <p className="text-xs text-danger" role="alert">{error}</p> : hint ? <p className="text-xs text-subtle">{hint}</p> : null}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  const id = useId();
  return (
    <label htmlFor={id} className={cn("inline-flex items-center gap-2.5 cursor-pointer select-none", disabled && "opacity-50 cursor-not-allowed")}>
      <button id={id} type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
        className={cn("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-brand" : "bg-line-strong")}>
        <span className={cn("absolute left-0 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-4" : "translate-x-0.5")} />
      </button>
      {label && <span className="text-sm text-fg">{label}</span>}
    </label>
  );
}

export function Checkbox({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" className="h-4 w-4 accent-[var(--brand)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/* ---------------- Surfaces ---------------- */
export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-panel shadow-card", className)} {...p} />;
}
export function CardHeader({ title, description, action, className }: { title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b border-line px-5 py-4", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold text-fg">{title}</h3>
        {description && <p className="mt-0.5 text-[13px] text-subtle">{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function CardBody({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...p} />;
}

export function PageHeader({ title, description, actions, eyebrow }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight text-fg sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ---------------- Badges & status ---------------- */
type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";
const toneCls: Record<Tone, string> = {
  neutral: "bg-panel-2 text-muted border-line", brand: "bg-brand-soft text-brand-text border-transparent",
  success: "bg-success-soft text-success border-transparent", warning: "bg-warning-soft text-warning border-transparent",
  danger: "bg-danger-soft text-danger border-transparent", info: "bg-info-soft text-info border-transparent",
};
export function Badge({ tone = "neutral", children, className, dot }: { tone?: Tone; children: React.ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11.5px] font-medium leading-4", toneCls[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  indexed: "success", succeeded: "success", active: "success", connected: "success", done: "success", published: "success", approved: "success", paid: "success", trialing: "brand",
  processing: "info", running: "info", queued: "neutral", in_progress: "info", in_review: "brand", waiting: "warning", waiting_approval: "warning", awaiting_approval: "warning", pending: "warning",
  draft: "neutral", paused: "warning", todo: "neutral", demo: "brand", disconnected: "neutral",
  failed: "danger", error: "danger", rejected: "danger", cancelled: "neutral", past_due: "danger", deactivated: "neutral", blocked: "danger",
  low: "neutral", medium: "info", high: "warning", urgent: "danger",
};
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <Badge tone={STATUS_TONES[status] || "neutral"} dot>{label || status.replace(/_/g, " ")}</Badge>;
}

/* ---------------- Feedback states ---------------- */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-subtle", className)} aria-label="Loading" />;
}
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-panel-2", className)} aria-hidden />;
}
export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-1" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  );
}
export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: { icon?: React.ComponentType<{ className?: string }>; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-dashed border-line-strong px-6 py-12 text-center", className)}>
      <div className="mb-3 rounded-xl bg-panel-2 p-3"><Icon className="h-5 w-5 text-subtle" /></div>
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-[13px] text-subtle">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">{msg}</div>
      {retry && <Button size="sm" variant="outline" onClick={retry}>Retry</Button>}
    </div>
  );
}
export function Callout({ tone = "info", title, children, icon: Icon }: { tone?: Tone; title?: string; children: React.ReactNode; icon?: React.ComponentType<{ className?: string }> }) {
  return (
    <div className={cn("flex gap-3 rounded-xl border p-3.5 text-[13px]", toneCls[tone])}>
      {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0" />}
      <div>{title && <div className="mb-0.5 font-semibold">{title}</div>}<div className="opacity-90">{children}</div></div>
    </div>
  );
}

/* ---------------- Modal (native <dialog>: focus trap + Esc for free) ---------------- */
export function Modal({ open, onClose, title, description, children, footer, wide }: { open: boolean; onClose: () => void; title: string; description?: string; children: React.ReactNode; footer?: React.ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      className={cn("m-auto w-[calc(100%-2rem)] rounded-2xl border border-line bg-panel p-0 text-fg shadow-pop backdrop:bg-black/40 backdrop:backdrop-blur-[2px]", wide ? "max-w-3xl" : "max-w-lg")}>
      {open && (
        <div className="animate-in">
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">{title}</h2>
              {description && <p className="mt-0.5 text-[13px] text-subtle">{description}</p>}
            </div>
            <button onClick={onClose} className="rounded-md p-1 text-subtle hover:bg-panel-2 hover:text-fg" aria-label="Close"><X className="h-4 w-4" /></button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/* ---------------- Menu ---------------- */
export function Menu({ trigger, children, align = "right" }: { trigger: (p: { open: boolean; toggle: () => void }) => React.ReactNode; children: React.ReactNode; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, []);
  return (
    <div className="relative" ref={ref}>
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div role="menu" onClick={() => setOpen(false)} className={cn("animate-in absolute z-50 mt-1.5 min-w-[200px] rounded-xl border border-line bg-panel p-1 shadow-pop", align === "right" ? "right-0" : "left-0")}>
          {children}
        </div>
      )}
    </div>
  );
}
export function MenuItem({ onClick, href, children, danger, icon: Icon }: { onClick?: () => void; href?: string; children: React.ReactNode; danger?: boolean; icon?: React.ComponentType<{ className?: string }> }) {
  const cls = cn("flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-panel-2", danger ? "text-danger" : "text-fg");
  const inner = <>{Icon && <Icon className="h-4 w-4 text-subtle" />}{children}</>;
  return href ? <Link role="menuitem" href={href} className={cls}>{inner}</Link> : <button role="menuitem" className={cls} onClick={onClick}>{inner}</button>;
}

/* ---------------- Tabs ---------------- */
export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: { value: T; label: React.ReactNode; count?: number }[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="tablist" className={cn("flex gap-1 overflow-x-auto border-b border-line", className)}>
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
          className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium transition-colors", value === t.value ? "border-brand text-fg" : "border-transparent text-subtle hover:text-fg")}>
          {t.label}{t.count !== undefined && <span className="ml-1.5 rounded bg-panel-2 px-1.5 text-[11px] text-subtle">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: { options: { value: T; label: React.ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-panel-2 p-0.5" role="radiogroup">
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cn("rounded-md px-2.5 py-1 text-[12.5px] font-medium", value === o.value ? "bg-panel text-fg shadow-card" : "text-subtle hover:text-fg")}>{o.label}</button>
      ))}
    </div>
  );
}

/* ---------------- Table ---------------- */
export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("overflow-x-auto", className)}><table className="w-full text-left text-[13px]">{children}</table></div>;
}
export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn("whitespace-nowrap border-b border-line px-4 py-2.5 text-[11.5px] font-medium uppercase tracking-wide text-subtle", className)}>{children}</th>;
}
export function Td({ children, className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-line px-4 py-3 align-middle text-fg", className)} {...p}>{children}</td>;
}

/* ---------------- Misc ---------------- */
export function Avatar({ name, size = 28, className }: { name?: string | null; size?: number; className?: string }) {
  const hue = Array.from(name || "?").reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white", className)} title={name || undefined}
      style={{ width: size, height: size, fontSize: size * 0.38, background: `hsl(${hue} 45% 48%)` }}>{initials(name)}</span>
  );
}

export function Progress({ value, max, tone = "brand" }: { value: number; max: number; tone?: "brand" | "warning" | "danger" }) {
  const pct = max <= 0 ? 0 : Math.min(100, (value / max) * 100);
  const color = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : tone === "brand" ? "bg-brand" : `bg-${tone}`;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-panel-2" role="progressbar" aria-valuenow={value} aria-valuemax={max}>
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("prose-nx", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer noopener" /> }}>{children}</ReactMarkdown>
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line bg-panel-2 px-1.5 py-0.5 font-mono text-[11px] text-subtle">{children}</kbd>;
}

export function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  return <pre className={cn("overflow-x-auto rounded-lg border border-line bg-panel-2 p-3 font-mono text-[12px] leading-relaxed text-fg", className)}>{children}</pre>;
}

export function Stat({ label, value, sub, delta, estimate, onClick }: { label: string; value: React.ReactNode; sub?: React.ReactNode; delta?: number | null; estimate?: boolean; onClick?: () => void }) {
  const up = (delta ?? 0) >= 0;
  const Comp = onClick ? "button" : "div";
  return (
    <Comp onClick={onClick} className={cn("rounded-xl border border-line bg-panel p-4 text-left shadow-card", onClick && "transition-colors hover:border-line-strong")}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12.5px] font-medium text-subtle">{label}</span>
        {estimate && <Badge tone="warning">Estimate</Badge>}
      </div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight text-fg tabular-nums">{value}</div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px]">
        {delta !== undefined && delta !== null && <span className={up ? "text-success" : "text-danger"}>{up ? "▲" : "▼"} {Math.abs(delta * 100).toFixed(0)}%</span>}
        {sub && <span className="text-subtle">{sub}</span>}
      </div>
    </Comp>
  );
}
