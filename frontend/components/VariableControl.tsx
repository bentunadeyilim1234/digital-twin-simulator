"use client";

import { RotateCcw } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { Badge, Button, EvidenceBadge, NumberField, Slider, Switch, cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { DOMAIN_COLOR, fmt } from "@/lib/format";
import type { Scenario, Series, Variable } from "@/lib/types";

/** One model variable: definition, slider + numeric input, model/manual switch, metadata and history. */
export function VariableControl({ v, draft, onChange, raw, history, compact, templateValue }: {
  v: Variable;
  draft: Scenario;
  onChange: (fn: (d: Scenario) => void) => void;
  raw?: { raw: number | null; unit: string } | null;
  history?: Series | null;
  compact?: boolean;
  templateValue: number;
}) {
  const { t, pick } = useI18n();
  const sym = v.symbol;
  const value = draft.initial_state[sym] ?? v.initial;
  const manual = draft.variable_modes?.[sym] === "manual";
  const derived = v.role === "derived";

  const setValue = (x: number) =>
    onChange((d) => {
      d.initial_state[sym] = Math.round(x * 1000) / 1000;
      if (d.variable_modes?.[sym] === "manual") d.overrides = { ...d.overrides, [sym]: { value: d.initial_state[sym] } };
    });
  const setManual = (m: boolean) =>
    onChange((d) => {
      d.variable_modes = { ...d.variable_modes };
      d.overrides = { ...d.overrides };
      if (m) {
        d.variable_modes[sym] = "manual";
        d.overrides[sym] = { value: d.initial_state[sym] ?? v.initial };
      } else {
        delete d.variable_modes[sym];
        delete d.overrides[sym];
      }
    });

  const hist = (history ?? []).map((y, i) => ({ i, y }));
  const hasHist = hist.some((p) => p.y !== null);

  return (
    <div
      data-testid={`var-${sym}`}
      className={cn("rounded-lg border bg-panel p-3", manual ? "border-[#7a5a1e] shadow-[inset_3px_0_0_#e0a040]" : "border-line")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: DOMAIN_COLOR[v.domain] }} aria-hidden />
            <span className="font-mono text-sm font-semibold text-ink">{sym}</span>
            <span className="text-[11px] text-muted">{v.id}</span>
            <span className="truncate text-sm text-ink">{pick(v.labels)}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <Badge tone="outline">{t(`roles.${v.role}`)}</Badge>
            <EvidenceBadge e={v.measurement_evidence} />
            {manual && <Badge tone="warm">{t("variables.manualActive")}</Badge>}
          </div>
        </div>
        <Button variant="ghost" size="icon" title={t("variables.resetVar")} aria-label={`${t("variables.resetVar")} ${sym}`}
          onClick={() => setValue(templateValue)}>
          <RotateCcw size={13} />
        </Button>
      </div>

      {!compact && <p className="mt-2 text-xs leading-relaxed text-ink-2">{pick(v.definition)}</p>}

      <div className="mt-3 flex items-center gap-2">
        <Slider value={value} onChange={setValue} label={`${sym} slider`} />
        <NumberField value={value} onChange={setValue} label={`${sym} value`} />
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>{t("variables.validRange")}</span>
        {raw && raw.raw !== null && <span className="tabular" data-testid={`raw-${sym}`}>{t("variables.raw")}: <span className="text-ink-2">{fmt(raw.raw, 2)} {raw.unit}</span></span>}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 border-t border-line pt-2 text-xs">
        <span className="text-ink-2">{manual ? t("variables.modeManual") : t("variables.modeModel")}</span>
        <Switch checked={manual} onChange={setManual} label={`${sym} manual override`} />
      </div>
      {derived && !manual && <p className="mt-1 text-[11px] text-muted">{t("variables.derivedNote")}</p>}
      {manual && <p className="mt-1 text-[11px] text-[#d9b46a]">{t("variables.holdNote")}</p>}

      {!compact && (
        <>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px]">
            <dt className="text-muted">{t("variables.measurement")}</dt>
            <dd className="text-ink-2">{v.measurement.unit} · [{v.measurement.lower}, {v.measurement.upper}] · {t(`common.${v.measurement.direction}`)}</dd>
            <dt className="text-muted">{t("variables.sources")}</dt>
            <dd className="text-ink-2">{v.measurement.sources.join("; ")}</dd>
            {v.references.length > 0 && <><dt className="text-muted">{t("common.references")}</dt><dd className="text-ink-2">{v.references.join(", ")}</dd></>}
          </dl>
          <div className="mt-2">
            <div className="text-[11px] text-muted">{t("variables.history")}</div>
            {hasHist ? (
              <div className="h-10">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={hist} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
                    <YAxis hide domain={["dataMin - 0.02", "dataMax + 0.02"]} />
                    <Line dataKey="y" stroke={DOMAIN_COLOR[v.domain]} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="text-[11px] text-muted">{t("variables.noHistory")}</div>}
          </div>
        </>
      )}
    </div>
  );
}
