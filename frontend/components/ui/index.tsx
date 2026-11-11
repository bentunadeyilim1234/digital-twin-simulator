"use client";

// Compact shadcn-style primitives built on Radix, styled for the dark console theme.
import * as SliderPrimitive from "@radix-ui/react-slider";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { X } from "lucide-react";
import { forwardRef, useEffect, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" | "icon" }>(
  function Button({ className, variant = "secondary", size = "md", ...props }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-45 whitespace-nowrap",
          size === "sm" && "h-7 px-2.5 text-xs",
          size === "md" && "h-8 px-3 text-sm",
          size === "icon" && "h-7 w-7 text-xs",
          variant === "primary" && "bg-accent text-white hover:bg-accent-strong",
          variant === "secondary" && "bg-panel-3 text-ink hover:bg-[#262d37] border border-line",
          variant === "outline" && "border border-line-strong text-ink-2 hover:text-ink hover:bg-panel-2",
          variant === "ghost" && "text-ink-2 hover:text-ink hover:bg-panel-2",
          variant === "danger" && "border border-[#5a2a2a] text-[#f09a9a] hover:bg-[#2a1717]",
          className,
        )}
        {...props}
      />
    );
  },
);

export function Panel({ title, actions, children, className, bodyClassName, id, subtitle }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string; id?: string; subtitle?: ReactNode;
}) {
  return (
    <section id={id} className={cn("rounded-lg border border-line bg-panel", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
          <div className="min-w-0">
            {title && <h2 className="truncate text-[13px] font-semibold tracking-wide text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "neutral", className, title }: {
  children: ReactNode; tone?: "neutral" | "accent" | "warm" | "good" | "bad" | "outline"; className?: string; title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap",
        tone === "neutral" && "bg-panel-3 text-ink-2",
        tone === "accent" && "bg-[#13294a] text-[#9ec5f4]",
        tone === "warm" && "bg-[#3a2a0f] text-[#f0c070]",
        tone === "good" && "bg-[#0f2a14] text-[#7fd47f]",
        tone === "bad" && "bg-[#3a1616] text-[#f09a9a]",
        tone === "outline" && "border border-line-strong text-ink-2",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function EvidenceBadge({ e }: { e: string }) {
  const tone = e === "E1" ? "good" : e === "E2" ? "accent" : e === "L" ? "good" : "warm";
  return <Badge tone={tone} title={e}>{e}</Badge>;
}

export function Field({ label, children, hint, className }: { label: ReactNode; children: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1 text-xs", className)}>
      <span className="text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted">{hint}</span>}
    </label>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={cn("h-8 w-full rounded-md border border-line bg-panel-2 px-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none tabular", className)}
      {...props}
    />
  );
});

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("h-8 w-full rounded-md border border-line bg-panel-2 px-2 text-sm text-ink focus:border-accent focus:outline-none", className)} {...props}>
      {children}
    </select>
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn("min-h-16 w-full rounded-md border border-line bg-panel-2 p-2 text-sm text-ink focus:border-accent focus:outline-none", props.className)} />;
}

export function Slider({ value, onChange, min = 0, max = 1, step = 0.01, disabled, label, className }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; disabled?: boolean; label?: string; className?: string;
}) {
  return (
    <SliderPrimitive.Root
      className={cn("relative flex h-5 w-full touch-none select-none items-center", disabled && "opacity-50", className)}
      value={[value]} min={min} max={max} step={step} disabled={disabled}
      onValueChange={(v) => onChange(v[0])}
    >
      <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-panel-3">
        <SliderPrimitive.Range className="absolute h-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb aria-label={label} className="block h-3.5 w-3.5 rounded-full border-2 border-accent bg-plane focus-visible:outline-2 focus-visible:outline-accent" />
    </SliderPrimitive.Root>
  );
}

/** Numeric input that commits on blur/Enter and clamps to [min, max]. */
export function NumberField({ value, onChange, min = 0, max = 1, step = 0.01, digits = 3, className, label, disabled }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; digits?: number; className?: string; label?: string; disabled?: boolean;
}) {
  const [text, setText] = useState(value.toFixed(digits));
  useEffect(() => setText(value.toFixed(digits)), [value, digits]);
  const commit = () => {
    const v = Number(text.replace(",", "."));
    if (Number.isFinite(v)) onChange(Math.min(max, Math.max(min, v)));
    else setText(value.toFixed(digits));
  };
  return (
    <Input
      aria-label={label} inputMode="decimal" disabled={disabled}
      className={cn("h-7 w-20 px-1.5 text-right text-xs", className)}
      value={text} step={step}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
    />
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <SwitchPrimitive.Root
      checked={checked} onCheckedChange={onChange} aria-label={label} disabled={disabled}
      className="relative h-4.5 w-8 shrink-0 rounded-full border border-line-strong bg-panel-3 data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:opacity-50"
    >
      <SwitchPrimitive.Thumb className="block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-ink transition-transform data-[state=checked]:translate-x-[14px]" />
    </SwitchPrimitive.Root>
  );
}

export const Tabs = TabsPrimitive.Root;
export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return <TabsPrimitive.List className={cn("flex flex-wrap gap-1 border-b border-line", className)}>{children}</TabsPrimitive.List>;
}
export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-ink-2 hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink"
    >
      {children}
    </TabsPrimitive.Trigger>
  );
}
export const TabsContent = TabsPrimitive.Content;

export function Dialog({ open, onOpenChange, title, children, footer, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <DialogPrimitive.Content className={cn("fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border border-line bg-panel shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")}>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <DialogPrimitive.Title className="text-sm font-semibold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="text-ink-2 hover:text-ink" aria-label="Close"><X size={16} /></DialogPrimitive.Close>
          </div>
          <DialogPrimitive.Description className="sr-only">{typeof title === "string" ? title : "dialog"}</DialogPrimitive.Description>
          <div className="p-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-4 py-3">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Stat({ label, value, sub, accent, testId }: { label: ReactNode; value: ReactNode; sub?: ReactNode; accent?: string; testId?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3" data-testid={testId}>
      <div className="flex items-center gap-1.5 text-xs text-ink-2">
        {accent && <span className="h-2.5 w-2.5 rounded-sm" style={{ background: accent }} aria-hidden />}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Meter({ value, color = "#3987e5", label }: { value: number | null | undefined; color?: string; label?: string }) {
  const v = value ?? 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-panel-3" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={v} aria-label={label}>
      <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%`, background: color }} />
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string | null | undefined; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-md border border-[#5a2a2a] bg-[#1d1213] px-3 py-2 text-sm text-[#f3b0b0]">
      <span className="min-w-0 break-words">{error}</span>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>↻</Button>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span className={cn("inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-2 border-t-transparent", className)} aria-hidden />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-line px-3 py-6 text-center text-sm text-muted">{children}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Table({ head, rows, className, testId, dense }: { head: ReactNode[]; rows: ReactNode[][]; className?: string; testId?: string; dense?: boolean }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-xs tabular" data-testid={testId}>
        <thead>
          <tr className="border-b border-line text-ink-2">
            {head.map((h, i) => <th key={i} className={cn("whitespace-nowrap px-2 font-medium", dense ? "py-1" : "py-1.5")}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/60 hover:bg-panel-2">
              {r.map((c, j) => <td key={j} className={cn("px-2 align-top text-ink", dense ? "py-1" : "py-1.5")}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const id = setTimeout(onDone, 2600);
    return () => clearTimeout(id);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <div role="status" className="fixed bottom-4 right-4 z-50 rounded-md border border-line bg-panel-3 px-3 py-2 text-sm text-ink shadow-xl">
      {message}
    </div>
  );
}
