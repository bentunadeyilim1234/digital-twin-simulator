"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Table, cn } from "@/components/ui";
import { fmt, sequential } from "@/lib/format";
import type { Series } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

export interface LineSeries {
  id: string;
  label: string;
  color: string;
  data: Series;
  dash?: string;
  width?: number;
}

export interface BandSeries {
  id: string;
  label: string;
  color: string;
  lo: Series;
  hi: Series;
}

const AXIS = { stroke: "#39414c", fontSize: 11, tick: { fill: "#828c99" } };

export function Legend({ items }: { items: { label: string; color: string; dash?: string; band?: boolean }[] }) {
  return (
    <ul className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-2">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-1.5">
          {it.band ? (
            <span className="h-2.5 w-4 rounded-sm opacity-40" style={{ background: it.color }} aria-hidden />
          ) : (
            <svg width="16" height="6" aria-hidden><line x1="0" y1="3" x2="16" y2="3" stroke={it.color} strokeWidth="2" strokeDasharray={it.dash} /></svg>
          )}
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  );
}

function TipBox({ active, payload, label, digits, unitLabel }: {
  active?: boolean; payload?: { name: string; value: number | [number, number]; color: string; dataKey: string }[]; label?: number; digits: number; unitLabel: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line bg-panel-3 px-2.5 py-1.5 text-xs shadow-xl">
      <div className="mb-1 font-semibold text-ink">{unitLabel} {label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4 tabular">
          <span className="flex items-center gap-1.5 text-ink-2"><span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />{p.name}</span>
          <span className="text-ink">{Array.isArray(p.value) ? `${fmt(p.value[0], digits)} – ${fmt(p.value[1], digits)}` : fmt(p.value, digits)}</span>
        </div>
      ))}
    </div>
  );
}

/** Monthly trajectory chart: one y-axis, thin 2px lines, crosshair tooltip, optional P5–P95 bands, table view. */
export function TrajectoryChart({ series, bands = [], height = 220, yDomain, digits = 3, title, testId, zeroLine, xLabels, hideLegend }: {
  series: LineSeries[]; bands?: BandSeries[]; height?: number; yDomain?: [number | "auto", number | "auto"]; digits?: number;
  title?: ReactNode; testId?: string; zeroLine?: boolean; xLabels?: string[]; hideLegend?: boolean;
}) {
  const { t } = useI18n();
  const [asTable, setAsTable] = useState(false);
  const n = Math.max(0, ...series.map((s) => s.data.length), ...bands.map((b) => b.lo.length));
  const data = useMemo(() => {
    const rows: Record<string, number | null | [number, number]>[] = [];
    for (let i = 0; i < n; i++) {
      const row: Record<string, number | null | [number, number]> = { m: i };
      for (const s of series) row[s.id] = s.data[i] ?? null;
      for (const b of bands) {
        const lo = b.lo[i], hi = b.hi[i];
        row[`band_${b.id}`] = lo !== null && hi !== null && lo !== undefined && hi !== undefined ? [lo, hi] : null;
      }
      rows.push(row);
    }
    return rows;
  }, [series, bands, n]);
  const legendItems = [
    ...bands.map((b) => ({ label: b.label, color: b.color, band: true })),
    ...series.map((s) => ({ label: s.label, color: s.color, dash: s.dash })),
  ];
  return (
    <figure className="min-w-0" data-testid={testId}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {title && <figcaption className="mb-1 text-xs font-medium text-ink-2">{title}</figcaption>}
          {legendItems.length > 1 && !hideLegend && <Legend items={legendItems} />}
        </div>
        <button className="shrink-0 text-[11px] text-muted underline-offset-2 hover:text-ink hover:underline" onClick={() => setAsTable((v) => !v)}>
          {asTable ? t("common.showChart") : t("common.showTable")}
        </button>
      </div>
      {asTable ? (
        <Table
          dense
          head={[t("common.month"), ...series.map((s) => s.label)]}
          rows={data.map((r, i) => [xLabels?.[i] ?? i, ...series.map((s) => fmt(r[s.id] as number | null, digits))])}
        />
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="#222831" vertical={false} />
              <XAxis dataKey="m" {...AXIS} tickLine={false} tickFormatter={(v) => (xLabels ? xLabels[v] ?? v : v)} minTickGap={12} />
              <YAxis {...AXIS} tickLine={false} axisLine={false} domain={yDomain ?? ["auto", "auto"]} width={46} tickFormatter={(v) => fmt(v, digits > 2 ? 2 : digits)} />
              {zeroLine && <ReferenceLine y={0} stroke="#4a5360" />}
              <Tooltip content={<TipBox digits={digits} unitLabel={t("common.month")} />} cursor={{ stroke: "#4a5360", strokeWidth: 1 }} />
              {bands.map((b) => (
                <Area key={b.id} dataKey={`band_${b.id}`} name={b.label} stroke="none" fill={b.color} fillOpacity={0.22} isAnimationActive={false} connectNulls />
              ))}
              {series.map((s) => (
                <Line key={s.id} dataKey={s.id} name={s.label} stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash}
                  dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#12161c" }} isAnimationActive={false} connectNulls />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </figure>
  );
}

/** Horizontal bars for rankings (single measure, one hue). */
export function BarList({ rows, max, digits = 3, color = "#3987e5", testId, secondary }: {
  rows: { label: ReactNode; value: number; key: string; note?: ReactNode }[]; max?: number; digits?: number; color?: string; testId?: string;
  secondary?: { values: Record<string, number>; label: string };
}) {
  const m = max ?? Math.max(1e-12, ...rows.map((r) => Math.abs(r.value)), ...(secondary ? Object.values(secondary.values).map(Math.abs) : []));
  return (
    <ul className="space-y-1.5" data-testid={testId}>
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(90px,170px)_1fr_auto] items-center gap-2 text-xs" title={typeof r.label === "string" ? r.label : undefined}>
          <span className="truncate text-ink-2">{r.label}</span>
          <span className="relative h-3 rounded-sm bg-panel-3">
            <span className="absolute inset-y-0 left-0 rounded-r-[3px]" style={{ width: `${(Math.abs(r.value) / m) * 100}%`, background: color }} />
            {secondary && secondary.values[r.key] !== undefined && (
              <span className="absolute inset-y-[3px] left-0 rounded-r-[2px] bg-[#9ec5f4]/70" style={{ width: `${(Math.max(0, secondary.values[r.key]) / m) * 100}%` }} />
            )}
          </span>
          <span className="w-16 text-right tabular text-ink">{fmt(r.value, digits)}{r.note}</span>
        </li>
      ))}
    </ul>
  );
}

/** Tornado diagram: low/high swings around the nominal output. */
export function Tornado({ rows, nominal, digits = 3, lowLabel, highLabel }: {
  rows: { key: string; label: string; low: number; high: number }[]; nominal: number; digits?: number; lowLabel: string; highLabel: string;
}) {
  const span = Math.max(1e-12, ...rows.map((r) => Math.max(Math.abs(r.low - nominal), Math.abs(r.high - nominal))));
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-[#e66767]" />{lowLabel}</span>
        <span className="tabular">nominal {fmt(nominal, digits)}</span>
        <span className="flex items-center gap-1">{highLabel}<span className="h-2 w-3 rounded-sm bg-[#3987e5]" /></span>
      </div>
      <ul className="space-y-1">
        {rows.map((r) => {
          const segs = [{ v: r.low, c: "#e66767" }, { v: r.high, c: "#3987e5" }];
          return (
            <li key={r.key} className="grid grid-cols-[minmax(90px,170px)_1fr] items-center gap-2 text-xs">
              <span className="truncate text-ink-2" title={r.label}>{r.label}</span>
              <span className="relative h-3.5">
                <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                {segs.map((s, i) => {
                  const d = (s.v - nominal) / span;
                  const w = Math.abs(d) * 50;
                  return (
                    <span key={i} title={`${fmt(s.v, digits)}`}
                      className="absolute inset-y-0.5"
                      style={{ background: s.c, width: `${w}%`, left: d >= 0 ? "50%" : `${50 - w}%`, borderRadius: d >= 0 ? "0 3px 3px 0" : "3px 0 0 3px", opacity: 0.9 }} />
                  );
                })}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Heatmap with a sequential one-hue ramp; values expected in [0, 1]. */
export function Heatmap({ rows, cols, values, rowLabel, digits = 2, testId }: {
  rows: string[]; cols: string[]; values: (number | null)[][]; rowLabel?: (r: string) => string; digits?: number; testId?: string;
}) {
  return (
    <div className="overflow-x-auto" data-testid={testId}>
      <table className="border-separate border-spacing-[2px] text-[11px] tabular">
        <thead>
          <tr>
            <th />
            {cols.map((c) => <th key={c} className="px-1 font-medium text-ink-2">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r}>
              <th className="max-w-[180px] truncate pr-2 text-right font-normal text-ink-2" title={r}>{rowLabel ? rowLabel(r) : r}</th>
              {cols.map((c, j) => {
                const v = values[i]?.[j];
                return (
                  <td key={c} title={`${r} · ${c}: ${fmt(v, digits)}`} className="h-6 min-w-12 rounded-[3px] text-center"
                    style={{ background: sequential(v ?? null), color: (v ?? 0) > 0.6 ? "#0b0e12" : "#e8ebef" }}>
                    {fmt(v, digits)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Stock-and-flow diagram for the support-process block at a given month. All numbers come from the engine. */
export function StockFlowDiagram({ month, Q, Qprev, I, C, mu, pressure, labels, className }: {
  month: number; Q: number | null; Qprev: number | null; I: number | null; C: number | null; mu: number | null; pressure: number | null;
  labels: { Q: string; I: string; C: string; mu: string; Qp: string; month: string }; className?: string;
}) {
  return (
    <svg viewBox="0 0 560 170" className={cn("w-full", className)} role="img" aria-label={`${labels.Q}: ${fmt(Q, 1)}`} data-testid="stockflow">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#b4bcc7" />
        </marker>
      </defs>
      <text x="8" y="16" fill="#828c99" fontSize="11">{labels.month} {month}</text>
      {/* cloud source */}
      <circle cx="40" cy="80" r="14" fill="none" stroke="#39414c" strokeDasharray="3 3" />
      <line x1="56" y1="80" x2="196" y2="80" stroke="#b4bcc7" strokeWidth="3" markerEnd="url(#arr)" />
      <text x="126" y="68" textAnchor="middle" fill="#b4bcc7" fontSize="11">{labels.I}</text>
      <text x="126" y="100" textAnchor="middle" fill="#e8ebef" fontSize="13" className="tabular">{fmt(I, 1)}/mo</text>
      {/* stock */}
      <rect x="200" y="45" width="150" height="70" rx="4" fill="#181d24" stroke="#3987e5" strokeWidth="1.5" />
      <rect x="201" y={115 - Math.min(68, (Q ?? 0) / Math.max(1, Math.max(Q ?? 0, Qprev ?? 0, 60)) * 68)} width="148"
        height={Math.min(68, (Q ?? 0) / Math.max(1, Math.max(Q ?? 0, Qprev ?? 0, 60)) * 68)} fill="#3987e5" opacity="0.25" />
      <text x="275" y="72" textAnchor="middle" fill="#b4bcc7" fontSize="11">{labels.Q}</text>
      <text x="275" y="96" textAnchor="middle" fill="#e8ebef" fontSize="18" fontWeight="600">{fmt(Q, 1)}</text>
      {/* outflow with capacity valve */}
      <line x1="354" y1="80" x2="510" y2="80" stroke="#b4bcc7" strokeWidth="3" markerEnd="url(#arr)" />
      <path d="M420,68 L440,80 L420,92 Z M460,68 L440,80 L460,92 Z" fill="#12161c" stroke="#b4bcc7" />
      <text x="440" y="60" textAnchor="middle" fill="#b4bcc7" fontSize="11">{labels.C}</text>
      <text x="440" y="110" textAnchor="middle" fill="#e8ebef" fontSize="13" className="tabular">{fmt(C, 1)}/mo</text>
      <circle cx="524" cy="80" r="12" fill="none" stroke="#39414c" strokeDasharray="3 3" />
      {/* capacity */}
      <line x1="440" y1="150" x2="440" y2="96" stroke="#828c99" strokeDasharray="4 3" markerEnd="url(#arr)" />
      <text x="450" y="148" fill="#b4bcc7" fontSize="11">{labels.mu} = {fmt(mu, 1)}/mo</text>
      <text x="200" y="148" fill="#b4bcc7" fontSize="11">{labels.Qp} = {fmt(pressure, 2)}</text>
    </svg>
  );
}
