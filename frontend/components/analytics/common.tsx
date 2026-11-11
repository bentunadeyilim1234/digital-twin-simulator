"use client";

import { useMemo, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Badge, Button, Input } from "@/components/ui";

/** Compact multi-select for parameter ids, grouped by prefix. */
export function ParamPicker({ all, selected, onChange, defaultLabel }: { all: string[]; selected: string[] | null; onChange: (v: string[] | null) => void; defaultLabel: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const cur = selected ?? all;
  const shown = useMemo(() => all.filter((p) => p.toLowerCase().includes(q.toLowerCase())), [all, q]);
  return (
    <div className="text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={selected ? "warm" : "neutral"}>{selected ? `${selected.length} / ${all.length}` : defaultLabel}</Badge>
        <Button size="sm" variant="outline" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{t("analytics.paramsSel")}</Button>
        {selected && <Button size="sm" variant="ghost" onClick={() => onChange(null)}>{t("common.reset")}</Button>}
      </div>
      {open && (
        <div className="mt-2 rounded-md border border-line bg-panel-2 p-2">
          <div className="mb-2 flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("common.search")} className="h-7 text-xs" />
            <Button size="sm" variant="ghost" onClick={() => onChange([...all])}>{t("common.selectAll")}</Button>
            <Button size="sm" variant="ghost" onClick={() => onChange([])}>{t("common.clear")}</Button>
          </div>
          <div className="grid max-h-56 grid-cols-1 gap-x-3 overflow-auto sm:grid-cols-2">
            {shown.map((p) => (
              <label key={p} className="flex items-center gap-1.5 py-0.5 font-mono text-[11px] text-ink-2">
                <input type="checkbox" className="accent-[#3987e5]" checked={cur.includes(p)}
                  onChange={(e) => onChange(e.target.checked ? [...cur, p] : cur.filter((x) => x !== p))} />
                {p}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function useBusy() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const wrap = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setErr(null);
    try { return await fn(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); return undefined; } finally { setBusy(false); }
  };
  return { busy, err, wrap, setErr };
}
