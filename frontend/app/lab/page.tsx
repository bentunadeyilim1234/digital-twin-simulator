"use client";

import { useMemo, useState } from "react";
import { Download, Play, RotateCcw, Save } from "lucide-react";
import { api, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { MAX_COMPARE, scenarioName, useApp } from "@/lib/store";
import { useScenarioDraft } from "@/lib/useScenarioDraft";
import { DOMAIN_COLOR, fmt, fmtInt, fmtSigned, scenarioColor } from "@/lib/format";
import type { CompareResult, Series } from "@/lib/types";
import { Badge, Button, Empty, ErrorBox, Field, PageHeader, Panel, Select, Slider, Spinner, Table, Toast, cn } from "@/components/ui";
import { Legend, StockFlowDiagram, TrajectoryChart, type BandSeries } from "@/components/charts";
import { ScenarioEditor } from "@/components/ScenarioEditor";

const OUTPUTS = ["TOTAL", "MIN_DOMAIN", "ENV", "SOC", "ORG", "SUP", "E", "C", "T", "A", "K", "S", "P", "R", "L", "H", "TR", "IF"];

export default function LabPage() {
  const { t, lang } = useI18n();
  const { scenarios, activeScenarioId, setActive, compareIds, setCompareIds, lastCompare, setLastCompare } = useApp();
  const { draft, dirty, update, save, saving, error, revert } = useScenarioDraft(activeScenarioId);
  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState<string | null>(null);
  const [output, setOutput] = useState("TOTAL");
  const [month, setMonth] = useState<number | null>(null);
  const [band, setBand] = useState<{ key: string; bands: BandSeries[] } | null>(null);
  const [bandBusy, setBandBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const allIds = useMemo(() => scenarios.map((s) => s.id), [scenarios]);
  const baseline = scenarios.find((s) => s.is_baseline);
  const result: CompareResult | null = lastCompare;

  const run = async () => {
    if (!draft) return;
    setRunning(true); setRunErr(null);
    try {
      if (dirty && !(await save())) throw new Error(error ?? "save failed");
      const ids = Array.from(new Set([draft.id, ...(baseline ? [baseline.id] : []), ...compareIds.filter((i) => allIds.includes(i))])).slice(0, MAX_COMPARE);
      const res = await api.post<CompareResult>("/compare", { scenario_ids: ids, baseline_id: baseline?.id, save: true });
      setLastCompare(res);
      setBand(null);
      setMonth(res.results[draft.id].horizon);
      setToast(t("lab.savedRun"));
    } catch (e) {
      setRunErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const resetToBaseline = () => {
    if (!baseline) return;
    update((d) => {
      for (const k of ["initial_state", "initial_stock", "external", "parameter_overrides", "context_schedule", "variable_modes", "overrides", "horizon_months", "dataset_id", "dataset_anchor"] as const) {
        (d as unknown as Record<string, unknown>)[k] = structuredClone((baseline as unknown as Record<string, unknown>)[k]);
      }
      d.interventions = [];
    });
  };

  const computeBand = async () => {
    if (!result || !draft) return;
    setBandBusy(true);
    try {
      const ids = Array.from(new Set([result.baseline_id, draft.id]));
      const out = ["TOTAL", "MIN_DOMAIN", "ENV", "SOC", "ORG", "SUP"].includes(output) ? output : OUTPUTS.includes(output) ? output : "TOTAL";
      const uq = await api.post<{ scenarios: { scenario_id: string; bands: Record<string, { p5: Series; p95: Series }> }[] }>("/analysis/uncertainty",
        { scenario_ids: ids, n_samples: 100, outputs: [out], save: false });
      setBand({ key: out, bands: uq.scenarios.map((s) => ({ id: s.scenario_id, label: `${scenarioName(scenarios.find((x) => x.id === s.scenario_id), lang)} P5–P95`, color: scenarioColor(s.scenario_id, allIds), lo: s.bands[out].p5, hi: s.bands[out].p95 })) });
    } catch (e) {
      setRunErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBandBusy(false);
    }
  };

  if (!draft) return null;
  const order = result?.order.filter((id) => result.results[id]) ?? [];
  const active = result?.results[draft.id];
  const N = active?.horizon ?? draft.horizon_months;
  const m = Math.min(month ?? N, N);
  const pickSeries = (id: string, key: string): Series => {
    const r = result!.results[id];
    return r.indices[key] ?? r.variables[key] ?? r.flows[key] ?? [];
  };
  const series = order.map((id) => ({
    id, label: scenarioName(scenarios.find((s) => s.id === id), lang) || result!.results[id].scenario_name || id,
    color: scenarioColor(id, allIds), data: pickSeries(id, output), dash: id === result?.baseline_id ? "5 3" : undefined,
  }));

  return (
    <div className="space-y-4">
      <PageHeader title={t("lab.title")}
        actions={<>
          {dirty && <Badge tone="warm">{t("variables.unsaved")}</Badge>}
          <Button variant="ghost" onClick={resetToBaseline} title={t("lab.resetBaselineHelp")} data-testid="reset-baseline"><RotateCcw size={14} />{t("lab.resetBaseline")}</Button>
          <Button onClick={async () => { if (await save()) setToast(t("common.saved")); }} disabled={!dirty || saving} data-testid="save-scenario"><Save size={14} />{t("common.save")}</Button>
          <Button variant="primary" onClick={run} disabled={running} data-testid="run-simulation">{running ? <Spinner /> : <Play size={14} />}{t("lab.run")}</Button>
        </>}
      />
      <ErrorBox error={error || runErr} />
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_300px]">
        {/* Left: configuration */}
        <div className="space-y-3">
          <Panel bodyClassName="p-0" title={t("lab.activeScenario")}>
            <div className="border-b border-line p-3">
              <Select value={draft.id} onChange={(e) => { if (!dirty || confirm(t("variables.unsaved") + " — " + t("common.cancel") + "?")) { revert(); setActive(e.target.value); } }} data-testid="lab-scenario">
                {scenarios.map((s) => <option key={s.id} value={s.id}>{scenarioName(s, lang)}{s.is_baseline ? ` · ${t("common.baseline")}` : ""}</option>)}
              </Select>
            </div>
            <ScenarioEditor draft={draft} update={update} />
          </Panel>
          <Panel title={t("lab.compareWith")}>
            <ul className="space-y-1 text-xs" data-testid="compare-list">
              {scenarios.map((s) => (
                <li key={s.id}>
                  <label className="flex items-center gap-2 text-ink-2">
                    <input type="checkbox" className="accent-[#3987e5]" checked={compareIds.includes(s.id) || s.id === draft.id || s.is_baseline}
                      disabled={s.id === draft.id || s.is_baseline || (!compareIds.includes(s.id) && compareIds.length >= MAX_COMPARE - 1)}
                      onChange={(e) => setCompareIds(e.target.checked ? [...compareIds, s.id] : compareIds.filter((x) => x !== s.id))} />
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: scenarioColor(s.id, allIds) }} />
                    <span className="truncate">{scenarioName(s, lang)}</span>
                  </label>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        {/* Centre: results */}
        <div className="min-w-0 space-y-4">
          {!result || !active ? <Empty>{t("lab.noResults")}</Empty> : (
            <>
              <Panel title={t("lab.trajectories")}
                actions={<>
                  <Select value={output} onChange={(e) => { setOutput(e.target.value); setBand(null); }} className="h-7 w-36 text-xs" aria-label={t("lab.selectOutput")} data-testid="lab-output">
                    {OUTPUTS.map((o) => <option key={o} value={o}>{["ENV", "SOC", "ORG", "SUP", "TOTAL", "MIN_DOMAIN"].includes(o) ? t(`domains.${o}`) : o}</option>)}
                  </Select>
                  <Button size="sm" variant="outline" onClick={computeBand} disabled={bandBusy} data-testid="uq-band">{bandBusy ? <Spinner /> : null}{t("lab.runUq")}</Button>
                </>}>
                <TrajectoryChart testId="chart-main" series={series} bands={band && band.key === output ? band.bands : []} height={260} />
                <p className="mt-1 text-[11px] text-muted">{t("lab.autoScale")}</p>
                {band && <p className="mt-1 text-[11px] text-muted">{t("lab.uncertainty")} · n=100 · {t("analytics.uqIntro")}</p>}
              </Panel>

              <Panel title={t("lab.domainsPanel")}>
                <Legend items={order.map((id) => ({ label: scenarioName(scenarios.find((s) => s.id === id), lang), color: scenarioColor(id, allIds), dash: id === result.baseline_id ? "5 3" : undefined }))} />
                <div className="grid gap-4 md:grid-cols-2">
                  {(["ENV", "SOC", "ORG", "SUP"] as const).map((d) => (
                    <TrajectoryChart key={d} title={<span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: DOMAIN_COLOR[d] }} />{t(`domains.${d}`)}</span>}
                      series={order.map((id) => ({ id, label: scenarioName(scenarios.find((s) => s.id === id), lang), color: scenarioColor(id, allIds), data: result.results[id].indices[d], dash: id === result.baseline_id ? "5 3" : undefined }))}
                      height={150} hideLegend />
                  ))}
                </div>
              </Panel>

              <Panel title={t("lab.stockflow")} subtitle={t("lab.stockflowCaption")}>
                <div className="mb-2 flex items-center gap-3 text-xs">
                  <span className="text-ink-2">{t("common.month")} {m}</span>
                  <Slider value={m} min={0} max={N} step={1} onChange={(v) => setMonth(Math.round(v))} label="stock-flow month" className="max-w-xs" />
                </div>
                <StockFlowDiagram month={m} Q={active.flows.Q[m]} Qprev={active.flows.Q[Math.max(0, m - 1)]} I={active.flows.I[m]} C={active.flows.C_flow[m]} mu={active.flows.mu[m]} pressure={active.flows.backlog_pressure[m]}
                  labels={{ Q: t("flows.Q"), I: t("flows.I"), C: t("flows.C_flow"), mu: "μ", Qp: t("flows.Qp"), month: t("common.month") }} />
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <TrajectoryChart title={t("flows.Q")} series={order.map((id) => ({ id, label: scenarioName(scenarios.find((s) => s.id === id), lang), color: scenarioColor(id, allIds), data: result.results[id].flows.Q, dash: id === result.baseline_id ? "5 3" : undefined }))} height={150} digits={1} testId="chart-Q" />
                  <TrajectoryChart title={`${t("flows.I")} · ${t("flows.C_flow")} · μ — ${scenarioName(draft, lang)}`}
                    series={[{ id: "I", label: "I", color: "#3987e5", data: active.flows.I }, { id: "C", label: "C_flow", color: "#199e70", data: active.flows.C_flow }, { id: "mu", label: "μ", color: "#9085e9", data: active.flows.mu, dash: "4 3" }]} height={150} digits={1} />
                </div>
                <p className="mt-2 text-[11px] text-muted">{t("flows.requestsNote")}</p>
              </Panel>

              <Panel title={t("lab.deltaTable", { n: N })}>
                <Table testId="delta-table"
                  head={[t("common.scenario"), "ΔTOTAL", "ΔENV", "ΔSOC", "ΔORG", "ΔSUP", "ΔMIN", "ΔQ"]}
                  rows={order.map((id) => {
                    const d = result.deltas[id];
                    const c = (v: number | null | undefined) => <span className={cn((v ?? 0) > 1e-6 ? "text-[#86b6ef]" : (v ?? 0) < -1e-6 ? "text-[#f09a9a]" : "text-ink-2")}>{fmtSigned(v)}</span>;
                    return [
                      <span key="n" className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: scenarioColor(id, allIds) }} />{scenarioName(scenarios.find((s) => s.id === id), lang)}</span>,
                      ...(d ? [c(d.indices.TOTAL[N]), c(d.indices.ENV[N]), c(d.indices.SOC[N]), c(d.indices.ORG[N]), c(d.indices.SUP[N]), c(d.indices.MIN_DOMAIN[N]), <span key="q">{fmtSigned(d.flows.Q[N], 1)}</span>] : Array(7).fill("—")),
                    ];
                  })} />
              </Panel>

              <Panel title={t("lab.resources")} subtitle={active.resources.unit}>
                <Table head={[t("common.scenario"), t("lab.programHours"), t("lab.supportHours")]}
                  rows={order.map((id) => [scenarioName(scenarios.find((s) => s.id === id), lang), fmtInt(result.resources[id].program_hours_total), fmtInt(result.resources[id].support_hours_total)])} />
              </Panel>
            </>
          )}
        </div>

        {/* Right: assumptions */}
        <div className="space-y-3">
          <Panel title={t("lab.assumptions")}>
            <div className="space-y-2 text-xs">
              <Badge tone="warm">{t("app.illustrative")}</Badge>
              <p className="text-ink-2">{t("app.boundary")}</p>
              {active && <p className="text-muted">hash {active.provenance.config_hash} · {active.provenance.data_class}</p>}
            </div>
          </Panel>
          {result && (
            <Panel title={t("lab.comparability")}>
              <ul className="space-y-1.5 text-xs" data-testid="comparability">
                {order.filter((id) => id !== result.baseline_id).map((id) => (
                  <li key={id}>
                    <div className="font-medium text-ink">{scenarioName(scenarios.find((s) => s.id === id), lang)}</div>
                    {result.comparability[id]?.length ? (
                      <div className="text-[#f0c070]">{t("lab.notComparable")} {result.comparability[id].join("; ")}</div>
                    ) : <div className="text-muted">{t("lab.comparable")}</div>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {active && (
            <Panel title={t("lab.targets")}>
              <Table dense head={["", "X", "X*"]} rows={["E", "C", "T", "A", "K", "S", "P"].map((s) => [<span key="s" className="font-mono">{s}</span>, fmt(active.variables[s][N]), fmt(active.targets[s][N])])} />
              {active.diagnostics.warnings.length > 0 && (
                <div className="mt-2 text-[11px] text-[#f0c070]">
                  <div className="font-medium">{t("common.warnings")}</div>
                  <ul className="list-disc pl-4">{active.diagnostics.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                </div>
              )}
              <p className="mt-2 text-[11px] text-muted">mass balance max error {active.diagnostics.mass_balance_max_error.toExponential(1)}</p>
              <Button size="sm" variant="outline" className="mt-2" onClick={() => download("/export/simulation.csv", `simulation_${draft.id}.csv`, { scenario_id: draft.id }, "POST")} data-testid="export-csv">
                <Download size={13} />{t("lab.exportCsv")}
              </Button>
            </Panel>
          )}
          <Field label={t("common.notes")}><p className="text-xs text-muted">{t("docs.timing")}</p></Field>
        </div>
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
