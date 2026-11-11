"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CircleCheck, CircleX } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmt, fmtDate, DOMAIN_COLOR } from "@/lib/format";
import type { LangText } from "@/lib/types";
import { Badge, ErrorBox, Meter, PageHeader, Panel, Spinner, Stat } from "@/components/ui";

interface Overview {
  hash: string;
  parameter_status: string;
  engine_version: string;
  baseline: { id: string; name: string; labels?: LangText; indices_start: Record<string, number>; indices_end: Record<string, number>; Q_start: number; data_class: string };
  changes: { modified_parameters: string[]; modified_edges: string[]; custom_edges: string[] };
  verification: { passed: number; total: number; all_passed: boolean };
  evidence_counts: Record<string, number>;
  datasets: Record<string, number>;
  n_scenarios: number;
  latest_runs: { id: string; kind: string; name: string; created_at: string }[];
  validated_horizon_months: number;
}

export default function OverviewPage() {
  const { t, pick } = useI18n();
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    setErr(null);
    api.get<Overview>("/overview").then(setData).catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  if (err) return <ErrorBox error={err} onRetry={load} />;
  if (!data) return <div className="flex items-center gap-2 text-sm text-muted"><Spinner />{t("app.loading")}</div>;

  const doms = ["ENV", "SOC", "ORG", "SUP"] as const;
  const s = data.baseline.indices_start;
  const e = data.baseline.indices_end;
  const weakest = doms.reduce((a, b) => (s[a] <= s[b] ? a : b));
  const evTotal = Object.values(data.evidence_counts).reduce((a, b) => a + b, 0) || 1;
  const anyChange = data.changes.modified_edges.length + data.changes.modified_parameters.length + data.changes.custom_edges.length > 0;

  return (
    <div className="space-y-4">
      <PageHeader title={t("overview.title")} subtitle={t("overview.subtitle")} />

      <section aria-label={t("overview.domainScores")}>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">{t("overview.domainScores")}</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          {doms.map((d) => (
            <Stat
              key={d} testId={`domain-${d}`} accent={DOMAIN_COLOR[d]} label={t(`domains.${d}`)}
              value={<span className="tabular">{fmt(s[d], 3)}</span>}
              sub={<><Meter value={s[d]} color={DOMAIN_COLOR[d]} label={d} /><span className="mt-1 block">{t("overview.horizonEnd", { n: 12 })}: {fmt(e[d], 3)}</span></>}
            />
          ))}
          <Stat testId="domain-TOTAL" label={t("overview.overall")} value={<span className="tabular">{fmt(s.TOTAL, 3)}</span>} sub={t("overview.totalCaveat")} />
          <Stat testId="domain-MIN" label={t("overview.weakest")} value={<span className="tabular">{fmt(s.MIN_DOMAIN, 3)}</span>}
            sub={<span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: DOMAIN_COLOR[weakest] }} />{t(`domains.${weakest}`)}</span>} />
        </div>
        <p className="mt-2 text-xs text-muted">{t("app.boundary")}</p>
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={t("overview.modelStatus")}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-ink-2">{t("overview.configHash")}</dt><dd className="font-mono text-ink">{data.hash}</dd>
            <dt className="text-ink-2">{t("overview.paramStatus")}</dt><dd><Badge tone="warm">{data.parameter_status}</Badge></dd>
            <dt className="text-ink-2">{t("overview.verification")}</dt>
            <dd className="flex items-center gap-1.5 text-ink">
              {data.verification.all_passed ? <CircleCheck size={14} className="text-good" /> : <CircleX size={14} className="text-critical" />}
              {t("overview.checksPassed", { p: data.verification.passed, t: data.verification.total })}
            </dd>
            <dt className="text-ink-2">{t("overview.pending")}</dt><dd className="tabular text-ink">{fmt(data.baseline.Q_start, 1)}</dd>
            <dt className="text-ink-2">{t("common.scenarios")}</dt><dd className="tabular text-ink">{data.n_scenarios}</dd>
            <dt className="text-ink-2">Engine</dt><dd className="text-ink">{data.engine_version}</dd>
          </dl>
        </Panel>

        <Panel title={t("overview.evidenceStatus")}>
          <div className="mb-2 flex h-3 overflow-hidden rounded-sm" aria-hidden>
            {(["E1", "E2", "L", "H"] as const).map((k, i) => (
              <span key={k} style={{ width: `${(data.evidence_counts[k] / evTotal) * 100}%`, background: ["#199e70", "#3987e5", "#9085e9", "#c98500"][i], marginRight: 2 }} />
            ))}
          </div>
          <ul className="space-y-1 text-xs">
            {(["E1", "E2", "L", "H"] as const).map((k, i) => (
              <li key={k} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-ink-2"><span className="h-2 w-2 rounded-sm" style={{ background: ["#199e70", "#3987e5", "#9085e9", "#c98500"][i] }} />{t(`evidenceLabels.${k}`)}</span>
                <span className="tabular text-ink">{data.evidence_counts[k]}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={t("overview.validation")}>
          <p className="text-sm text-ink">{t("overview.validatedHorizon", { n: data.validated_horizon_months })}</p>
          <p className="mt-1 text-xs text-muted">{t("overview.notValidated")}</p>
          <h3 className="mb-1 mt-3 text-xs font-medium text-ink-2">{t("overview.provenance")}</h3>
          <ul className="space-y-1 text-xs">
            {Object.entries(data.datasets).map(([k, v]) => (
              <li key={k} className="flex justify-between"><span className="text-ink-2">{t(`dataClass.${k}`)}</span><span className="tabular">{v}</span></li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-muted">{t("common.baseline")}: {pick(data.baseline.labels, data.baseline.name)} · {data.baseline.data_class}</p>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={t("overview.latestRuns")} className="lg:col-span-1">
          {data.latest_runs.length === 0 ? <p className="text-xs text-muted">{t("overview.noRuns")}</p> : (
            <ul className="space-y-1.5 text-xs">
              {data.latest_runs.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate"><Badge tone="outline">{r.kind}</Badge> <span className="text-ink">{r.name}</span></span>
                  <span className="shrink-0 text-muted">{fmtDate(r.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={t("overview.changes")}>
          {!anyChange ? <p className="text-xs text-muted">{t("overview.noChanges")}</p> : (
            <div className="space-y-2 text-xs">
              {[["modifiedEdges", data.changes.modified_edges], ["modifiedParams", data.changes.modified_parameters], ["customEdges", data.changes.custom_edges]].map(([k, list]) =>
                (list as string[]).length ? (
                  <div key={k as string}>
                    <div className="mb-1 text-ink-2">{t(`overview.${k}`)}</div>
                    <div className="flex flex-wrap gap-1">{(list as string[]).map((x) => <Badge key={x} tone="warm">{x}</Badge>)}</div>
                  </div>
                ) : null)}
            </div>
          )}
        </Panel>
        <Panel title={t("overview.quickStart")}>
          <ul className="space-y-1.5 text-sm">
            {[["/lab", "qsLab"], ["/twin", "qsTwin"], ["/causal", "qsCausal"]].map(([href, k]) => (
              <li key={href}>
                <Link href={href} className="group flex items-center justify-between rounded-md px-2 py-1.5 text-ink-2 hover:bg-panel-2 hover:text-ink">
                  {t(`overview.${k}`)} <ArrowRight size={14} className="text-muted group-hover:text-accent" />
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
