"use client";

import { useEffect, useState } from "react";
import { CircleCheck, CircleX, Download, Play } from "lucide-react";
import { api, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { fmt, pct, SERIES } from "@/lib/format";
import type { Series } from "@/lib/types";
import { Badge, Button, Empty, ErrorBox, EvidenceBadge, Field, Input, Panel, Select, Spinner, Switch, Table } from "@/components/ui";
import { TrajectoryChart } from "@/components/charts";
import { ParamPicker, useBusy } from "./common";

function DatasetSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  const datasets = useApp((s) => s.datasets);
  return (
    <Field label={t("common.dataset")}>
      <Select value={value} onChange={(e) => onChange(e.target.value)} data-testid="cal-dataset">
        {datasets.map((d) => <option key={d.id} value={d.id}>{d.name} · {t(`dataClass.${d.data_class}`)} · {d.n_periods}</option>)}
      </Select>
    </Field>
  );
}

function allParamIds(): string[] {
  const cfg = useApp.getState().config;
  if (!cfg) return [];
  return [...cfg.edges.filter((e) => e.enabled && e.kind !== "structural").map((e) => `edge.${e.id}`), ...cfg.parameters.filter((p) => !["cost", "weights"].includes(p.group)).map((p) => p.id)];
}

interface LsqResult {
  status: string; n_calibration: number; n_holdout: number; targets: string[]; objective_initial: number; objective_fitted: number; residual_sd: number;
  jacobian_condition_number: number | null; periods: string[];
  parameters: { id: string; initial: number; prior_centre: number; estimate: number; se: number; ci95: [number, number]; identifiable: boolean; identifiability_notes: string[]; at_bound: boolean }[];
  fit: Record<string, { calibration_initial: Metrics; calibration_fitted: Metrics; holdout_fitted: Metrics | null }>;
  trajectories: Record<string, { observed: Series; initial: Series; fitted: Series }>;
  truth: Record<string, number> | null; assumptions: string[]; dataset_name: string;
}
interface Metrics { n: number; rmse: number | null; mae: number | null; r2: number | null; bias: number | null }

export function LsqTab() {
  const { t } = useI18n();
  const { datasets, meta, refreshConfig } = useApp();
  const [ds, setDs] = useState(datasets[0]?.id ?? "");
  const [params, setParams] = useState<string[] | null>(null);
  const [holdout, setHoldout] = useState(6);
  const [lam, setLam] = useState(0.05);
  const [prior, setPrior] = useState("config");
  const [res, setRes] = useState<LsqResult | null>(null);
  const [applied, setApplied] = useState(false);
  const [target, setTarget] = useState("T");
  const { busy, err, wrap } = useBusy();
  if (!datasets.length) return <Empty>{t("analytics.datasetRequired")}</Empty>;
  const all = allParamIds();
  const run = () => wrap(async () => {
    const r = await api.post<LsqResult>("/calibration/lsq", { dataset_id: ds, param_ids: params ?? meta?.default_calibration_params, holdout, reg_lambda: lam, prior_source: prior });
    setRes(r); setApplied(false); if (!r.targets.includes(target)) setTarget(r.targets[0]);
  });
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t("analytics.lsqIntro")}</p>
      <Panel>
        <div className="grid gap-3 md:grid-cols-5">
          <DatasetSelect value={ds} onChange={setDs} />
          <Field label={t("analytics.holdout")}><Input type="number" min={0} value={holdout} onChange={(e) => setHoldout(Number(e.target.value))} /></Field>
          <Field label={t("analytics.regLambda")}><Input type="number" step="0.01" min={0} value={lam} onChange={(e) => setLam(Number(e.target.value))} /></Field>
          <Field label={t("analytics.priorSource")}>
            <Select value={prior} onChange={(e) => setPrior(e.target.value)}>
              <option value="config">{t("analytics.priorConfig")}</option><option value="expert">{t("analytics.priorExpert")}</option><option value="literature">{t("analytics.priorLiterature")}</option>
            </Select>
          </Field>
          <div className="flex items-end"><Button variant="primary" onClick={run} disabled={busy} data-testid="run-lsq">{busy ? <Spinner /> : <Play size={14} />}{t("common.run")}</Button></div>
        </div>
        <div className="mt-3"><ParamPicker all={all} selected={params} onChange={setParams} defaultLabel={`default (${meta?.default_calibration_params.length ?? 0})`} /></div>
      </Panel>
      <ErrorBox error={err} />
      {res && (
        <>
          <Panel title={`${t("common.status")}: ${res.status}`} subtitle={`${res.dataset_name} · ${res.n_calibration} + ${res.n_holdout} · SSR ${fmt(res.objective_initial, 3)} → ${fmt(res.objective_fitted, 3)} · σ̂ ${fmt(res.residual_sd, 4)} · cond(J) ${fmt(res.jacobian_condition_number, 1)}`}
            actions={<Button size="sm" variant="primary" disabled={applied} data-testid="apply-lsq" onClick={async () => {
              await api.post("/calibration/apply", { estimates: Object.fromEntries(res.parameters.map((p) => [p.id, p.estimate])), method: "lsq", dataset_name: res.dataset_name });
              setApplied(true); await refreshConfig();
            }}>{t("analytics.applyEstimates")}</Button>} bodyClassName="p-0">
            <Table testId="lsq-table" dense
              head={[t("common.parameter"), t("analytics.initialVal"), t("analytics.estimateVal"), "SE", t("analytics.ci"), t("analytics.identifiable"), ...(res.truth ? [t("analytics.truth")] : [])]}
              rows={res.parameters.map((p) => [
                <span key="p" className="font-mono">{p.id}</span>, fmt(p.initial), <span key="e" className="text-ink">{fmt(p.estimate)}{p.at_bound ? " ⚑" : ""}</span>, fmt(p.se),
                `[${fmt(p.ci95[0])}, ${fmt(p.ci95[1])}]`,
                p.identifiable ? <Badge key="i" tone="good">{t("common.yes")}</Badge> : <span key="i" title={p.identifiability_notes.join("; ")}><Badge tone="bad">{t("common.no")}</Badge> <span className="text-[11px] text-muted">{p.identifiability_notes.join("; ")}</span></span>,
                ...(res.truth ? [fmt(res.truth[p.id])] : []),
              ])} />
            {applied && <p className="p-3 text-xs text-good">{t("analytics.applied")}</p>}
          </Panel>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title={t("analytics.fit")} bodyClassName="p-0">
              <Table dense head={["", `${t("analytics.rmse")} (${t("analytics.initialVal")})`, `${t("analytics.rmse")} (${t("analytics.fitted")})`, t("analytics.r2"), t("analytics.holdoutRmse")]}
                rows={Object.entries(res.fit).map(([s, f]) => [<span key="s" className="font-mono">{s}</span>, fmt(f.calibration_initial.rmse, 4), fmt(f.calibration_fitted.rmse, 4), fmt(f.calibration_fitted.r2, 3), fmt(f.holdout_fitted?.rmse, 4)])} />
            </Panel>
            <Panel title={`${t("analytics.observed")} vs ${t("analytics.fitted")}`} actions={<Select value={target} onChange={(e) => setTarget(e.target.value)} className="h-7 w-20 text-xs" aria-label="target">{Object.keys(res.trajectories).map((k) => <option key={k}>{k}</option>)}</Select>}>
              <TrajectoryChart height={210} digits={target === "Q" ? 1 : 3} xLabels={res.periods}
                series={[
                  { id: "obs", label: t("analytics.observed"), color: "#b4bcc7", data: res.trajectories[target].observed, width: 1.5 },
                  { id: "ini", label: t("analytics.initialVal"), color: SERIES[1], data: res.trajectories[target].initial, dash: "4 3" },
                  { id: "fit", label: t("analytics.fitted"), color: SERIES[0], data: res.trajectories[target].fitted },
                ]} />
              {res.n_holdout > 0 && <p className="text-[11px] text-muted">{t("analytics.holdout")}: {res.periods[res.n_calibration]} → {res.periods[res.periods.length - 1]}</p>}
            </Panel>
          </div>
          <Panel title={t("lab.assumptions")}><ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-2">{res.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Panel>
        </>
      )}
    </div>
  );
}

interface BayesResult {
  backend: string; pymc_available: boolean; n_chains: number; n_iter: number; burn: number; acceptance_rate: number[]; converged: boolean; convergence_rule: string;
  targets: string[]; periods: string[]; dataset_name: string; truth: Record<string, number> | null; assumptions: string[];
  sigma: { mean: number; q05: number; q95: number };
  parameters: { id: string; map: number; prior: { low: number; high: number; mode: number; q05: number; q95: number; source: string }; posterior: { mean: number; sd: number; q05: number; q50: number; q95: number }; rhat: number | null; ess: number; posterior_to_prior_sd: number | null; identifiable: boolean; notes: string[] }[];
  predictive: Record<string, { observed: Series; p5: Series; p50: Series; p95: Series }>;
}

export function BayesTab() {
  const { t } = useI18n();
  const { datasets, meta } = useApp();
  const [ds, setDs] = useState(datasets[0]?.id ?? "");
  const [params, setParams] = useState<string[] | null>(null);
  const [chains, setChains] = useState(3);
  const [iters, setIters] = useState(3000);
  const [burn, setBurn] = useState(1000);
  const [res, setRes] = useState<BayesResult | null>(null);
  const [target, setTarget] = useState("T");
  const { busy, err, wrap } = useBusy();
  if (!datasets.length) return <Empty>{t("analytics.datasetRequired")}</Empty>;
  const all = allParamIds();
  const run = () => wrap(async () => {
    const r = await api.post<BayesResult>("/calibration/bayes", { dataset_id: ds, param_ids: params ?? meta?.default_bayes_params, n_chains: chains, n_iter: iters, burn });
    setRes(r); if (!r.targets.includes(target)) setTarget(r.targets[0]);
  });
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t("analytics.bayesIntro")}</p>
      {!meta?.capabilities.pymc && <p className="text-xs text-muted">{t("analytics.pymcNote")}</p>}
      <Panel>
        <div className="grid gap-3 md:grid-cols-5">
          <DatasetSelect value={ds} onChange={setDs} />
          <Field label={t("analytics.chains")}><Input type="number" min={1} max={6} value={chains} onChange={(e) => setChains(Number(e.target.value))} /></Field>
          <Field label={t("analytics.iterations")}><Input type="number" min={200} max={20000} value={iters} onChange={(e) => setIters(Number(e.target.value))} data-testid="bayes-iter" /></Field>
          <Field label={t("analytics.burn")}><Input type="number" min={0} value={burn} onChange={(e) => setBurn(Number(e.target.value))} /></Field>
          <div className="flex items-end"><Button variant="primary" onClick={run} disabled={busy} data-testid="run-bayes">{busy ? <Spinner /> : <Play size={14} />}{t("common.run")}</Button></div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <ParamPicker all={all} selected={params} onChange={setParams} defaultLabel={`default (${meta?.default_bayes_params.length ?? 0})`} />
          <span className="text-xs text-muted">≈ {Math.round(chains * iters * 0.0012)} s</span>
        </div>
      </Panel>
      <ErrorBox error={err} />
      {res && (
        <>
          <Panel title={res.converged ? t("analytics.converged") : t("analytics.notConverged")}
            subtitle={`${res.backend} · ${res.dataset_name} · ${t("analytics.acceptance")} ${res.acceptance_rate.map((a) => pct(a)).join(" / ")} · σ ≈ ${fmt(res.sigma.mean, 4)} · ${res.convergence_rule}`} bodyClassName="p-0">
            <Table testId="bayes-table" dense
              head={[t("common.parameter"), t("analytics.prior"), "MAP", t("analytics.posterior"), t("analytics.credible"), t("analytics.rhat"), t("analytics.ess"), ...(res.truth ? [t("analytics.truth")] : []), ""]}
              rows={res.parameters.map((p) => [
                <span key="p" className="font-mono">{p.id}</span>, `[${fmt(p.prior.q05)}, ${fmt(p.prior.q95)}]`, fmt(p.map), <span key="m" className="text-ink">{fmt(p.posterior.mean)}</span>,
                `[${fmt(p.posterior.q05)}, ${fmt(p.posterior.q95)}]`,
                <span key="r" className={(p.rhat ?? 1) > 1.1 ? "text-[#f09a9a]" : (p.rhat ?? 1) > 1.05 ? "text-[#f0c070]" : ""}>{fmt(p.rhat, 3)}</span>,
                Math.round(p.ess), ...(res.truth ? [fmt(res.truth[p.id])] : []),
                <span key="n" className="text-[11px] text-muted">{p.notes.join("; ")}</span>,
              ])} />
          </Panel>
          <Panel title={t("analytics.predictive")} actions={<Select value={target} onChange={(e) => setTarget(e.target.value)} className="h-7 w-20 text-xs" aria-label="target">{res.targets.map((k) => <option key={k}>{k}</option>)}</Select>}>
            <TrajectoryChart height={220} xLabels={res.periods}
              bands={[{ id: "pp", label: "P5–P95", color: SERIES[0], lo: res.predictive[target].p5, hi: res.predictive[target].p95 }]}
              series={[{ id: "obs", label: t("analytics.observed"), color: "#b4bcc7", data: res.predictive[target].observed, width: 1.5 }, { id: "p50", label: t("analytics.median"), color: SERIES[0], data: res.predictive[target].p50 }]} />
          </Panel>
          <Panel title={t("lab.assumptions")}><ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-2">{res.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Panel>
        </>
      )}
    </div>
  );
}

interface Verification { checks: { id: string; name: string; status: string; detail: string }[]; passed: number; total: number; all_passed: boolean }
interface Conceptual { relationships: { id: string; hypothesis: string | null; source: string; target: string; sign: number; coefficient: number; evidence: string; flags: string[] }[]; evidence_counts: Record<string, number> }
interface Envelope { unvalidated_assumptions: string[]; outside_scope: string[]; validated_horizon_months: number; parameter_provenance_counts: Record<string, number>; statement?: { en: string; tr: string } }

export function ValidationTab() {
  const { t, pick } = useI18n();
  const datasets = useApp((s) => s.datasets);
  const [ver, setVer] = useState<Verification | null>(null);
  const [con, setCon] = useState<Conceptual | null>(null);
  const [env, setEnv] = useState<Envelope | null>(null);
  const [ds, setDs] = useState(datasets[0]?.id ?? "");
  const [holdout, setHoldout] = useState(6);
  const [calib, setCalib] = useState(true);
  const [hist, setHist] = useState<{ variables: Record<string, { calibration: Metrics; holdout: Metrics; residuals: Series; observed: Series; simulated: Series; trend: { direction_agrees: boolean | null }; residual_lag1_autocorrelation: number | null }>; periods: string[]; n_calibration: number; mean_holdout_rmse: number; note: string | null } | null>(null);
  const [histVar, setHistVar] = useState("T");
  const [ivVar, setIvVar] = useState("A");
  const [ivPeriod, setIvPeriod] = useState(24);
  const [iv, setIv] = useState<{ its: Record<string, number | number[]>; model: { mean_post_change_vs_counterfactual: number; intervention_inputs_present: boolean }; agreement: { same_direction: boolean | null; difference: number }; series: { observed: Series; model_with_intervention: Series; model_counterfactual: Series; periods: string[] }; assumptions: string[] } | null>(null);
  const { busy, err, wrap } = useBusy();

  useEffect(() => {
    void wrap(async () => {
      const [v, c, e] = await Promise.all([api.get<Verification>("/validation/verification"), api.get<Conceptual>("/validation/conceptual"), api.get<Envelope>("/validation/envelope")]);
      setVer(v); setCon(c); setEnv(e);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const d = datasets.find((x) => x.id === ds);
    const ivm = (d?.provenance as { generator?: { intervention?: { start_month?: number; key?: string } } })?.generator?.intervention;
    if (ivm?.start_month) setIvPeriod(ivm.start_month);
  }, [ds, datasets]);

  return (
    <div className="space-y-4">
      <ErrorBox error={err} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t("analytics.verification")} subtitle={ver ? `${ver.passed} / ${ver.total}` : undefined}>
          {!ver ? <Spinner /> : (
            <ul className="space-y-1.5 text-xs" data-testid="verification-list">
              {ver.checks.map((c) => (
                <li key={c.id} className="flex gap-2">
                  {c.status === "pass" ? <CircleCheck size={14} className="mt-0.5 shrink-0 text-good" /> : <CircleX size={14} className="mt-0.5 shrink-0 text-critical" />}
                  <div><span className="font-mono text-muted">{c.id}</span> <span className="text-ink">{c.name}</span><div className="text-[11px] text-ink-2">{c.detail}</div></div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={t("analytics.envelope")} actions={<Button size="sm" variant="outline" onClick={() => download("/validation/report", "validation_report.md", { dataset_id: ds || null, holdout, format: "markdown" }, "POST")} data-testid="export-report"><Download size={13} />{t("analytics.exportReport")}</Button>}>
          {env && (
            <div className="space-y-2 text-xs">
              <p className="text-ink">{t("overview.validatedHorizon", { n: env.validated_horizon_months })}</p>
              {env.statement && <p className="text-ink-2">{pick(env.statement)}</p>}
              <div><div className="mb-1 font-medium text-ink-2">{t("analytics.outsideScope")}</div><ul className="list-disc pl-5 text-ink-2">{env.outside_scope.map((x) => <li key={x}>{x}</li>)}</ul></div>
              <details><summary className="cursor-pointer text-ink-2">{t("analytics.unvalidated")} ({env.unvalidated_assumptions.length})</summary>
                <ul className="mt-1 list-disc pl-5 font-mono text-[11px] text-muted">{env.unvalidated_assumptions.map((x) => <li key={x}>{x}</li>)}</ul></details>
            </div>
          )}
        </Panel>
      </div>
      <Panel title={t("analytics.conceptual")} subtitle={con ? Object.entries(con.evidence_counts).map(([k, v]) => `${k}: ${v}`).join(" · ") : undefined} bodyClassName="p-0">
        {con && <Table dense head={["ID", "", "→", t("common.evidence"), "coef", ""]}
          rows={con.relationships.map((r) => [<span key="i" className="font-mono">{r.id}</span>, r.hypothesis ?? "", `${r.source} → ${r.target}`, <EvidenceBadge key="e" e={r.evidence} />, `${r.sign > 0 ? "+" : "−"}${fmt(r.coefficient, 2)}`, <span key="f" className="text-[11px] text-muted">{r.flags.join("; ")}</span>])} />}
      </Panel>
      <Panel title={t("analytics.historical")}>
        <div className="grid gap-3 md:grid-cols-4">
          <DatasetSelect value={ds} onChange={setDs} />
          <Field label={t("analytics.holdout")}><Input type="number" min={1} value={holdout} onChange={(e) => setHoldout(Number(e.target.value))} /></Field>
          <label className="flex items-end gap-2 pb-1 text-xs text-ink-2"><Switch checked={calib} onChange={setCalib} label="calibrate" />{t("analytics.calibrateFirst")}</label>
          <div className="flex items-end"><Button variant="primary" disabled={busy || !ds} data-testid="run-historical" onClick={() => wrap(async () => setHist(await api.post("/validation/historical", { dataset_id: ds, holdout, calibrate: calib })))}>{busy ? <Spinner /> : <Play size={14} />}{t("common.run")}</Button></div>
        </div>
        {hist && (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <Table dense testId="historical-table" head={["", t("analytics.rmse"), t("analytics.holdoutRmse"), t("analytics.mae"), t("analytics.trendAgrees"), t("analytics.lag1")]}
              rows={Object.entries(hist.variables).map(([s, v]) => [<span key="s" className="font-mono">{s}</span>, fmt(v.calibration.rmse, 4), fmt(v.holdout.rmse, 4), fmt(v.holdout.mae, 4), v.trend.direction_agrees === null ? "—" : v.trend.direction_agrees ? "✓" : "✗", fmt(v.residual_lag1_autocorrelation, 2)])} />
            <div>
              <Select value={histVar} onChange={(e) => setHistVar(e.target.value)} className="mb-2 h-7 w-20 text-xs" aria-label="variable">{Object.keys(hist.variables).map((k) => <option key={k}>{k}</option>)}</Select>
              <TrajectoryChart height={170} xLabels={hist.periods} series={[{ id: "o", label: t("analytics.observed"), color: "#b4bcc7", data: hist.variables[histVar].observed, width: 1.5 }, { id: "s", label: t("analytics.fitted"), color: SERIES[0], data: hist.variables[histVar].simulated }]} />
              <TrajectoryChart height={120} zeroLine xLabels={hist.periods} title={t("analytics.residuals")} series={[{ id: "r", label: t("analytics.residuals"), color: SERIES[1], data: hist.variables[histVar].residuals }]} />
            </div>
            {hist.note && <p className="text-[11px] text-muted lg:col-span-2">{hist.note}</p>}
          </div>
        )}
      </Panel>
      <Panel title={t("analytics.intervention")}>
        <div className="grid gap-3 md:grid-cols-4">
          <DatasetSelect value={ds} onChange={setDs} />
          <Field label={t("analytics.ivVariable")}><Select value={ivVar} onChange={(e) => setIvVar(e.target.value)}>{["A", "T", "C", "K", "S", "P", "H", "L", "R"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label={t("analytics.ivPeriod")}><Input type="number" value={ivPeriod} onChange={(e) => setIvPeriod(Number(e.target.value))} /></Field>
          <div className="flex items-end"><Button variant="primary" disabled={busy || !ds} data-testid="run-its" onClick={() => wrap(async () => setIv(await api.post("/validation/intervention", { dataset_id: ds, variable: ivVar, intervention_period: ivPeriod })))}>{t("common.run")}</Button></div>
        </div>
        {iv && (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-ink-2">{t("analytics.levelChange")}</dt><dd className="tabular">{fmt(iv.its.level_change as number, 4)} [{(iv.its.level_change_ci95 as number[]).map((x) => fmt(x, 4)).join(", ")}] · {t("analytics.pValue")}={fmt(iv.its.level_change_p as number, 3)}</dd>
              <dt className="text-ink-2">{t("analytics.slopeChange")}</dt><dd className="tabular">{fmt(iv.its.slope_change as number, 4)} [{(iv.its.slope_change_ci95 as number[]).map((x) => fmt(x, 4)).join(", ")}] · {t("analytics.pValue")}={fmt(iv.its.slope_change_p as number, 3)}</dd>
              <dt className="text-ink-2">{t("analytics.observedChange")}</dt><dd className="tabular">{fmt(iv.its.observed_mean_post_change as number, 4)}</dd>
              <dt className="text-ink-2">{t("analytics.modelChange")}</dt><dd className="tabular">{fmt(iv.model.mean_post_change_vs_counterfactual, 4)}{!iv.model.intervention_inputs_present && " (no recorded intervention)"}</dd>
              <dt className="text-ink-2">same direction</dt><dd>{iv.agreement.same_direction === null ? "—" : iv.agreement.same_direction ? "✓" : "✗"}</dd>
            </dl>
            <TrajectoryChart height={180} xLabels={iv.series.periods} series={[
              { id: "o", label: t("analytics.observed"), color: "#b4bcc7", data: iv.series.observed, width: 1.5 },
              { id: "w", label: "model", color: SERIES[0], data: iv.series.model_with_intervention },
              { id: "c", label: "counterfactual", color: SERIES[1], data: iv.series.model_counterfactual, dash: "4 3" },
            ]} />
            <ul className="list-disc pl-5 text-[11px] text-muted lg:col-span-2">{iv.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </div>
        )}
      </Panel>
    </div>
  );
}
