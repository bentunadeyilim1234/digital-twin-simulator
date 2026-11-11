"use client";

import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { scenarioName, useApp } from "@/lib/store";
import { fmt, pct, scenarioColor } from "@/lib/format";
import type { Series } from "@/lib/types";
import { Button, ErrorBox, Field, Input, Panel, Select, Spinner, Switch, Table } from "@/components/ui";
import { BarList, Heatmap, Tornado, TrajectoryChart } from "@/components/charts";
import { ParamPicker, useBusy } from "./common";

type Band = { p5: Series; p50: Series; p95: Series; nominal: Series; mean: Series };
interface UQResult {
  n_samples: number; parameters: string[]; outputs: string[]; horizon: number; note: string;
  scenarios: { scenario_id: string; scenario_name: string; bands: Record<string, Band>; difference_to_baseline?: Record<string, { p5: Series; p50: Series; p95: Series; prob_positive_end: number }> }[];
  parameter_summary: ({ id: string; nominal: number; range: [number, number] } & Record<string, number | string | null | [number, number]>)[];
}

const UQ_OUTPUTS = ["TOTAL", "MIN_DOMAIN", "ENV", "SOC", "ORG", "SUP", "Q", "T", "L", "P"];

export function UncertaintyTab() {
  const { t, lang } = useI18n();
  const { scenarios, meta } = useApp();
  const allIds = scenarios.map((s) => s.id);
  const base = scenarios.find((s) => s.is_baseline);
  const [ids, setIds] = useState<string[]>(() => [base?.id, scenarios.find((s) => s.template_id === "S4")?.id].filter(Boolean) as string[]);
  const [n, setN] = useState(200);
  const [seed, setSeed] = useState(7);
  const [params, setParams] = useState<string[] | null>(null);
  const [out, setOut] = useState("TOTAL");
  const [res, setRes] = useState<UQResult | null>(null);
  const { busy, err, wrap } = useBusy();
  const all = meta?.uncertain_parameters ?? [];

  const run = () => wrap(async () => setRes(await api.post<UQResult>("/analysis/uncertainty", { scenario_ids: ids, n_samples: n, seed, param_ids: params, outputs: UQ_OUTPUTS })));

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t("analytics.uqIntro")}</p>
      <Panel>
        <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr_auto]">
          <Field label={t("common.scenarios")}>
            <div className="flex flex-wrap gap-2 text-xs">
              {scenarios.map((s) => (
                <label key={s.id} className="flex items-center gap-1.5 text-ink-2">
                  <input type="checkbox" className="accent-[#3987e5]" checked={ids.includes(s.id)} onChange={(e) => setIds(e.target.checked ? [...ids, s.id].slice(0, 5) : ids.filter((x) => x !== s.id))} />
                  <span className="h-2 w-2 rounded-sm" style={{ background: scenarioColor(s.id, allIds) }} />{scenarioName(s, lang)}
                </label>
              ))}
            </div>
          </Field>
          <Field label={t("analytics.nSamples")}><Input type="number" min={10} max={2000} value={n} onChange={(e) => setN(Number(e.target.value))} data-testid="uq-n" /></Field>
          <Field label={t("common.seed")}><Input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></Field>
          <div className="flex items-end"><Button variant="primary" onClick={run} disabled={busy || ids.length === 0} data-testid="run-uq">{busy ? <Spinner /> : <Play size={14} />}{t("common.run")}</Button></div>
        </div>
        <div className="mt-3"><ParamPicker all={all} selected={params} onChange={setParams} defaultLabel={t("analytics.paramsDefault", { n: all.length })} /></div>
      </Panel>
      <ErrorBox error={err} />
      {res && (
        <>
          <Panel title={`${t("analytics.bandOf")} · n=${res.n_samples} · ${res.parameters.length} ${t("common.parameters").toLowerCase()}`}
            actions={<Select value={out} onChange={(e) => setOut(e.target.value)} className="h-7 w-36 text-xs" aria-label={t("common.output")}>{UQ_OUTPUTS.map((o) => <option key={o}>{o}</option>)}</Select>}>
            <TrajectoryChart testId="uq-chart" height={260}
              bands={res.scenarios.map((s) => ({ id: s.scenario_id, label: `${scenarioName(scenarios.find((x) => x.id === s.scenario_id), lang)} P5–P95`, color: scenarioColor(s.scenario_id, allIds), lo: s.bands[out].p5, hi: s.bands[out].p95 }))}
              series={res.scenarios.map((s) => ({ id: s.scenario_id, label: `${scenarioName(scenarios.find((x) => x.id === s.scenario_id), lang)} · ${t("analytics.median")}`, color: scenarioColor(s.scenario_id, allIds), data: s.bands[out].p50 }))} />
            <p className="mt-2 text-[11px] text-muted">{res.note}</p>
          </Panel>
          {res.scenarios.some((s) => s.difference_to_baseline) && (
            <Panel title={`${t("analytics.diffBand")} · ${out}`}>
              <TrajectoryChart height={200} zeroLine
                bands={res.scenarios.filter((s) => s.difference_to_baseline).map((s) => ({ id: s.scenario_id, label: `${scenarioName(scenarios.find((x) => x.id === s.scenario_id), lang)} Δ P5–P95`, color: scenarioColor(s.scenario_id, allIds), lo: s.difference_to_baseline![out].p5, hi: s.difference_to_baseline![out].p95 }))}
                series={res.scenarios.filter((s) => s.difference_to_baseline).map((s) => ({ id: s.scenario_id, label: `Δ ${t("analytics.median")}`, color: scenarioColor(s.scenario_id, allIds), data: s.difference_to_baseline![out].p50 }))} />
              <ul className="mt-2 text-xs text-ink-2">
                {res.scenarios.filter((s) => s.difference_to_baseline).map((s) => (
                  <li key={s.scenario_id}>{scenarioName(scenarios.find((x) => x.id === s.scenario_id), lang)}: {t("analytics.probPositive")} = <span className="text-ink tabular">{pct(s.difference_to_baseline![out].prob_positive_end)}</span></li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title={t("analytics.paramSummary")} bodyClassName="p-0">
            <Table dense head={[t("common.parameter"), t("analytics.nominal"), t("common.range"), "ρ_s"]}
              rows={res.parameter_summary.slice(0, 25).map((p) => [<span key="p" className="font-mono">{p.id}</span>, fmt(p.nominal), `[${fmt(p.range[0], 2)}, ${fmt(p.range[1], 2)}]`, fmt(p["spearman_with_TOTAL_end"] as number | null, 3)])} />
          </Panel>
        </>
      )}
    </div>
  );
}

interface SAResult {
  method: string; parameters: string[]; outputs: string[]; month: number; n_runs: number; nominal_outputs: Record<string, number>; note?: string;
  indices?: Record<string, ({ id: string } & Record<string, number>)[]>;
  heatmap?: { rows: string[]; cols: string[]; values: (number | null)[][]; metric: string };
  tornado?: { id: string; low: number; high: number; output_low: Record<string, number>; output_high: Record<string, number>; swing: Record<string, number> }[];
  interactions?: { output: string; rows: string[]; values: (number | null)[][] } | null;
}

export function SensitivityTab() {
  const { t, lang } = useI18n();
  const { scenarios, meta } = useApp();
  const [sid, setSid] = useState(() => scenarios.find((s) => s.template_id === "S4")?.id ?? scenarios[0]?.id);
  const [method, setMethod] = useState<"morris" | "sobol" | "tornado">("morris");
  const [n, setN] = useState(20);
  const [second, setSecond] = useState(false);
  const [params, setParams] = useState<string[] | null>(null);
  const [out, setOut] = useState("TOTAL");
  const [est, setEst] = useState<{ runs: number; approx_seconds: number } | null>(null);
  const [res, setRes] = useState<SAResult | null>(null);
  const { busy, err, wrap } = useBusy();
  const all = meta?.uncertain_parameters ?? [];
  const nParams = (params ?? all).length;

  useEffect(() => { setN(method === "sobol" ? 64 : 20); }, [method]);
  useEffect(() => {
    api.get<{ runs: number; approx_seconds: number }>(`/analysis/sensitivity/estimate?method=${method}&n_params=${nParams}&n=${n}&second_order=${second}`).then(setEst).catch(() => setEst(null));
  }, [method, nParams, n, second]);

  const run = () => wrap(async () => setRes(await api.post<SAResult>("/analysis/sensitivity", { scenario_id: sid, method, n, param_ids: params, second_order: second, outputs: ["TOTAL", "SOC", "ORG", "SUP", "Q"] })));
  const metric = res?.method === "sobol" ? "ST" : "mu_star";

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t("analytics.saIntro")}</p>
      <Panel>
        <div className="grid gap-3 md:grid-cols-5">
          <Field label={t("common.scenario")}><Select value={sid} onChange={(e) => setSid(e.target.value)}>{scenarios.map((s) => <option key={s.id} value={s.id}>{scenarioName(s, lang)}</option>)}</Select></Field>
          <Field label={t("common.method")}>
            <Select value={method} onChange={(e) => setMethod(e.target.value as "morris")} data-testid="sa-method">
              <option value="morris">{t("analytics.morris")}</option><option value="sobol">{t("analytics.sobol")}</option><option value="tornado">{t("analytics.tornado")}</option>
            </Select>
          </Field>
          {method !== "tornado" && <Field label={method === "morris" ? t("analytics.trajectories") : t("analytics.baseN")}><Input type="number" value={n} onChange={(e) => setN(Number(e.target.value))} data-testid="sa-n" /></Field>}
          {method === "sobol" && <label className="flex items-end gap-2 pb-1 text-xs text-ink-2"><Switch checked={second} onChange={setSecond} label="second order" />{t("analytics.secondOrder")}</label>}
          <div className="flex items-end gap-2">
            <Button variant="primary" onClick={run} disabled={busy || nParams < 2} data-testid="run-sa">{busy ? <Spinner /> : <Play size={14} />}{t("common.run")}</Button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <ParamPicker all={all} selected={params} onChange={setParams} defaultLabel={t("analytics.paramsDefault", { n: all.length })} />
          {est && <span className="text-xs text-muted">{t("analytics.estRuns", { runs: est.runs, s: est.approx_seconds })}</span>}
        </div>
      </Panel>
      <ErrorBox error={err} />
      {res && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title={`${t("analytics.ranking")} · ${res.method} · ${t("common.month")} ${res.month} · ${res.n_runs} runs`}
            actions={res.indices && <Select value={out} onChange={(e) => setOut(e.target.value)} className="h-7 w-28 text-xs" aria-label={t("common.output")}>{res.outputs.map((o) => <option key={o}>{o}</option>)}</Select>}>
            {res.indices && (
              <BarList testId="sa-ranking" digits={3}
                rows={res.indices[out].slice(0, 20).map((r) => ({ key: r.id, label: r.id, value: r[metric] }))}
                secondary={res.method === "sobol" ? { label: "S1", values: Object.fromEntries(res.indices[out].map((r) => [r.id, r.S1])) } : undefined} />
            )}
            {res.method === "sobol" && <p className="mt-2 text-[11px] text-muted">Bar = ST (total order); inner light bar = S1 (first order). ST − S1 ≈ interaction share. {res.note}</p>}
            {res.method === "morris" && <p className="mt-2 text-[11px] text-muted">μ* = mean absolute elementary effect; large σ relative to μ* indicates non-linearity or interactions.</p>}
            {res.tornado && (
              <Tornado lowLabel={t("common.lower")} highLabel={t("common.upper")} nominal={res.nominal_outputs.TOTAL}
                rows={res.tornado.slice(0, 18).map((r) => ({ key: r.id, label: r.id, low: r.output_low.TOTAL, high: r.output_high.TOTAL }))} />
            )}
          </Panel>
          {res.heatmap && (
            <Panel title={t("analytics.heatmap")} subtitle={res.heatmap.metric}>
              <Heatmap testId="sa-heatmap" rows={res.heatmap.rows.slice(0, 25)} cols={res.heatmap.cols} values={res.heatmap.values.slice(0, 25)} />
            </Panel>
          )}
          {res.indices && (
            <Panel title={`${t("common.details")} · ${out}`} bodyClassName="p-0" className="lg:col-span-2">
              <Table dense head={res.method === "sobol" ? [t("common.parameter"), "S1", "±", "ST", "±"] : [t("common.parameter"), "μ", "μ*", "σ", "μ* conf"]}
                rows={res.indices[out].map((r) => res.method === "sobol"
                  ? [<span key="p" className="font-mono">{r.id}</span>, fmt(r.S1), fmt(r.S1_conf), fmt(r.ST), fmt(r.ST_conf)]
                  : [<span key="p" className="font-mono">{r.id}</span>, fmt(r.mu, 4), fmt(r.mu_star, 4), fmt(r.sigma, 4), fmt(r.mu_star_conf, 4)])} />
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
