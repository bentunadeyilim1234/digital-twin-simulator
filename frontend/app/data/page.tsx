"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileJson, Play, ShieldCheck, Trash2, Upload } from "lucide-react";
import { api, ApiError, download, saveJson } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { DOMAIN_COLOR, fmt, fmtDate } from "@/lib/format";
import type { Dataset } from "@/lib/types";
import { Badge, Button, ErrorBox, Field, Input, PageHeader, Panel, Select, Spinner, Switch, Table, Toast, cn } from "@/components/ui";
import { TrajectoryChart } from "@/components/charts";

interface Inspection { columns: string[]; n_rows: number; suggested_mapping: Record<string, string | null>; unmapped: string[]; forbidden_columns: string[]; privacy_ok: boolean; preview: Record<string, unknown>[]; targets: string[] }
type ColMap = { target: string; scale: "normalized" | "raw"; lower?: string; upper?: string; direction?: string };

export default function DataPage() {
  const { t, pick } = useI18n();
  const { datasets, refreshDatasets, meta, config } = useApp();
  const [sel, setSel] = useState<string>(datasets[0]?.id ?? "");
  const [detail, setDetail] = useState<Dataset | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [gen, setGen] = useState({ months: 36, seed: 7, missing_rate: 0.05, noise_sd: 0.02, smoothing: 0.6, start_period: "2023-09", seasonal: true, include_intervention: true });
  const [busy, setBusy] = useState(false);
  // import wizard
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [insp, setInsp] = useState<Inspection | null>(null);
  const [mapping, setMapping] = useState<Record<string, ColMap>>({});
  const [imp, setImp] = useState({ name: "", data_class: "PUBLIC_RESEARCH", source: "", authorization_reference: "", data_controller: "" });
  const [impErrors, setImpErrors] = useState<string[] | null>(null);

  useEffect(() => {
    if (!sel) { setDetail(null); return; }
    api.get<Dataset>(`/datasets/${sel}`).then(setDetail).catch((e) => setErr(String(e.message)));
  }, [sel]);
  useEffect(() => { if (!sel && datasets[0]) setSel(datasets[0].id); }, [datasets, sel]);

  const summary = datasets.find((d) => d.id === sel);
  const q = summary?.quality;

  const generate = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.post<{ id: string }>("/datasets/synthetic", gen);
      await refreshDatasets(); setSel(r.id); setToast(t("common.saved"));
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const inspect = async (f: File) => {
    setFile(f); setInsp(null); setImpErrors(null);
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api.form<Inspection>("/datasets/inspect", fd);
      setInsp(r);
      setMapping(Object.fromEntries(r.columns.map((c) => [c, { target: r.forbidden_columns.includes(c) ? "ignore" : r.suggested_mapping[c] ?? "", scale: "normalized" as const }])));
      setImp((s) => ({ ...s, name: f.name.replace(/\.(csv|json|txt)$/i, "") }));
    } catch (e) { setImpErrors(e instanceof ApiError && e.errors ? e.errors : [String((e as Error).message)]); }
  };

  const doImport = async () => {
    if (!file || !insp) return;
    const mp: Record<string, unknown> = {};
    for (const [c, m] of Object.entries(mapping)) {
      if (!m.target) continue;
      mp[c] = m.scale === "raw" && config?.variables.some((v) => v.symbol === m.target)
        ? { target: m.target, scale: "raw", ...(m.lower ? { lower: Number(m.lower) } : {}), ...(m.upper ? { upper: Number(m.upper) } : {}), ...(m.direction ? { direction: m.direction } : {}) }
        : m.target;
    }
    const fd = new FormData();
    fd.append("file", file); fd.append("mapping", JSON.stringify(mp)); fd.append("data_class", imp.data_class); fd.append("name", imp.name);
    fd.append("provenance", JSON.stringify({ source: imp.source, authorization_reference: imp.authorization_reference, data_controller: imp.data_controller }));
    try {
      const r = await api.form<{ id: string; warnings: string[] }>("/datasets/import", fd);
      await refreshDatasets(); setSel(r.id); setInsp(null); setFile(null); setImpErrors(r.warnings.length ? r.warnings : null);
      setToast(t("data.importOk"));
    } catch (e) { setImpErrors(e instanceof ApiError && e.errors ? e.errors : [String((e as Error).message)]); }
  };

  return (
    <div className="space-y-4">
      <PageHeader title={t("data.title")} subtitle={t("data.subtitle")}
        actions={<Button onClick={async () => saveJson(await api.get("/export/research-metadata"), "ssrdt_research_metadata.json")} data-testid="export-metadata"><FileJson size={14} />{t("data.exportMeta")}</Button>} />
      <ErrorBox error={err} />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <Panel title={t("data.datasets")} bodyClassName="p-0">
            <ul className="divide-y divide-line" data-testid="dataset-list">
              {datasets.map((d) => (
                <li key={d.id}>
                  <button onClick={() => setSel(d.id)} className={cn("w-full px-3 py-2 text-left hover:bg-panel-2", sel === d.id && "bg-panel-3")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm text-ink">{d.name}</span>
                      <Badge tone={d.data_class === "SYNTHETIC" ? "warm" : d.data_class === "AUTHORIZED_SCHOOL" ? "good" : "accent"}>{t(`dataClass.${d.data_class}`)}</Badge>
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted">{d.periods.join(" → ")} · {d.n_periods} · {fmtDate(d.created_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title={t("data.generator")} subtitle={t("app.synthetic")}>
            <div className="grid grid-cols-2 gap-2">
              <Field label={t("data.monthsN")}><Input type="number" min={6} max={120} value={gen.months} onChange={(e) => setGen({ ...gen, months: Number(e.target.value) })} data-testid="gen-months" /></Field>
              <Field label={t("common.seed")}><Input type="number" value={gen.seed} onChange={(e) => setGen({ ...gen, seed: Number(e.target.value) })} data-testid="gen-seed" /></Field>
              <Field label={t("data.missingRate")}><Input type="number" step="0.01" min={0} max={0.5} value={gen.missing_rate} onChange={(e) => setGen({ ...gen, missing_rate: Number(e.target.value) })} /></Field>
              <Field label={t("data.noise")}><Input type="number" step="0.005" min={0} max={0.2} value={gen.noise_sd} onChange={(e) => setGen({ ...gen, noise_sd: Number(e.target.value) })} /></Field>
              <Field label={t("data.smoothing")}><Input type="number" step="0.05" min={0} max={0.95} value={gen.smoothing} onChange={(e) => setGen({ ...gen, smoothing: Number(e.target.value) })} /></Field>
              <Field label={t("data.startPeriod")}><Input value={gen.start_period} onChange={(e) => setGen({ ...gen, start_period: e.target.value })} /></Field>
              <label className="col-span-2 flex items-center gap-2 text-xs text-ink-2"><Switch checked={gen.seasonal} onChange={(v) => setGen({ ...gen, seasonal: v })} label="seasonal" />{t("data.seasonal")}</label>
              <label className="col-span-2 flex items-center gap-2 text-xs text-ink-2"><Switch checked={gen.include_intervention} onChange={(v) => setGen({ ...gen, include_intervention: v })} label="intervention" />{t("data.withIntervention")}</label>
            </div>
            <Button variant="primary" className="mt-3 w-full" onClick={generate} disabled={busy} data-testid="generate-synthetic">{busy ? <Spinner /> : <Play size={14} />}{t("data.generate")}</Button>
          </Panel>
        </div>

        <div className="min-w-0 space-y-4">
          {summary && q && (
            <Panel title={`${t("data.quality")} · ${summary.name}`}
              actions={<>
                <Button size="sm" variant="outline" onClick={() => download(`/datasets/${summary.id}/export.csv`, `${summary.id}.csv`)}><Download size={13} />{t("data.exportCsv")}</Button>
                <Button size="sm" variant="danger" aria-label={t("common.delete")} onClick={async () => { await api.del(`/datasets/${summary.id}`); setSel(""); await refreshDatasets(); }}><Trash2 size={13} /></Button>
              </>}>
              <div className="mb-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div><div className="text-muted">{t("data.completeness")}</div><div className="text-lg font-semibold tabular">{fmt(q.completeness_pct, 1)}%</div></div>
                <div><div className="text-muted">{t("common.months")}</div><div className="text-lg font-semibold tabular">{q.n_periods}</div></div>
                <div><div className="text-muted">{t("data.massBalance")}</div><div className="text-sm">{q.flow_mass_balance ? (q.flow_mass_balance.consistent ? <Badge tone="good">{t("data.consistent")}</Badge> : <Badge tone="bad">{t("data.inconsistent")}</Badge>) : "—"}</div></div>
                <div><div className="text-muted">{t("data.labelled")}</div><div className="text-sm">{q.all_records_labelled ? <Badge tone="good"><ShieldCheck size={11} />{summary.data_class}</Badge> : <Badge tone="bad">✗</Badge>}</div></div>
              </div>
              {(summary.provenance as { statement?: string })?.statement && <p className="mb-2 text-xs font-semibold text-[#e7c27a]">{(summary.provenance as { statement?: string }).statement}</p>}
              <Table dense testId="quality-table" head={["", t("data.missing"), "%", t("data.longestGap"), "min", "mean", "max"]}
                rows={Object.entries(q.variables).map(([s, v]) => [<span key="s" className="font-mono">{s}</span>, v.missing, fmt(v.missing_pct, 1), v.longest_gap ?? "—", fmt(v.min, 3), fmt(v.mean, 3), fmt(v.max, 3)])} />
            </Panel>
          )}
          {detail && config && (
            <Panel title={t("data.series")}>
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
                {config.domains.map((d) => (
                  <TrajectoryChart key={d.id} height={140} yDomain={[0, 1]} xLabels={detail.periods}
                    title={<span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: DOMAIN_COLOR[d.id] }} />{t(`domains.${d.id}`)}</span>}
                    series={d.variables.filter((s) => detail.variables[s]).map((s, i) => ({ id: s, label: s, color: ["#3987e5", "#d95926", "#199e70", "#c98500"][i], data: detail.variables[s] }))} />
                ))}
                {detail.flows?.Q && <TrajectoryChart height={140} digits={0} xLabels={detail.periods} title={t("flows.Q")} series={[{ id: "Q", label: "Q", color: "#3987e5", data: detail.flows.Q }]} />}
              </div>
            </Panel>
          )}

          <Panel title={t("data.importTitle")} subtitle={t("data.mapHelp")}>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => fileRef.current?.click()} data-testid="choose-file"><Upload size={14} />{t("data.chooseFile")}</Button>
              <input ref={fileRef} type="file" accept=".csv,.json,.txt" hidden data-testid="file-input" onChange={(e) => { const f = e.target.files?.[0]; if (f) void inspect(f); e.target.value = ""; }} />
              {file && <span className="text-xs text-ink-2">{file.name}</span>}
            </div>
            {impErrors && <div className="mt-3"><ErrorBox error={impErrors.join(" · ")} /></div>}
            {insp && (
              <div className="mt-3 space-y-3">
                {!insp.privacy_ok && <ErrorBox error={`${t("data.privacyBlocked")} ${insp.forbidden_columns.join(", ")}`} />}
                <Table dense testId="mapping-table" head={[t("data.column"), t("data.mapTo"), t("data.scale"), t("common.lower"), t("common.upper"), t("common.direction")]}
                  rows={insp.columns.map((c) => {
                    const m = mapping[c] ?? { target: "", scale: "normalized" };
                    const isVar = config?.variables.some((v) => v.symbol === m.target);
                    const set = (patch: Partial<ColMap>) => setMapping((x) => ({ ...x, [c]: { ...m, ...patch } }));
                    return [
                      <span key="c" className={cn("font-mono", insp.forbidden_columns.includes(c) && "text-[#f09a9a] line-through")}>{c}</span>,
                      <Select key="t" value={m.target} onChange={(e) => set({ target: e.target.value })} className={cn("h-7 text-xs", !m.target && "border-[#7a5a1e]")} aria-label={`map ${c}`} disabled={insp.forbidden_columns.includes(c)}>
                        <option value="">—</option><option value="ignore">{t("data.ignore")}</option>
                        {insp.targets.filter((x) => x !== "ignore").map((x) => <option key={x} value={x}>{x}</option>)}
                      </Select>,
                      isVar ? <Select key="s" value={m.scale} onChange={(e) => set({ scale: e.target.value as "raw" })} className="h-7 text-xs"><option value="normalized">{t("data.normalized")}</option><option value="raw">{t("data.rawScale")}</option></Select> : "—",
                      isVar && m.scale === "raw" ? <Input key="l" className="h-7 w-20 text-xs" placeholder={String(config?.variables.find((v) => v.symbol === m.target)?.measurement.lower)} value={m.lower ?? ""} onChange={(e) => set({ lower: e.target.value })} /> : "",
                      isVar && m.scale === "raw" ? <Input key="u" className="h-7 w-20 text-xs" placeholder={String(config?.variables.find((v) => v.symbol === m.target)?.measurement.upper)} value={m.upper ?? ""} onChange={(e) => set({ upper: e.target.value })} /> : "",
                      isVar && m.scale === "raw" ? <Select key="d" value={m.direction ?? ""} onChange={(e) => set({ direction: e.target.value })} className="h-7 w-24 text-xs"><option value="">default</option><option value="positive">{t("common.positive")}</option><option value="negative">{t("common.negative")}</option></Select> : "",
                    ];
                  })} />
                <div className="grid gap-2 md:grid-cols-4">
                  <Field label={t("common.name")}><Input value={imp.name} onChange={(e) => setImp({ ...imp, name: e.target.value })} /></Field>
                  <Field label={t("data.dataClassSel")}>
                    <Select value={imp.data_class} onChange={(e) => setImp({ ...imp, data_class: e.target.value })} data-testid="import-class">
                      {(meta?.data_classes ?? []).map((c) => <option key={c} value={c}>{t(`dataClass.${c}`)}</option>)}
                    </Select>
                  </Field>
                  {imp.data_class === "PUBLIC_RESEARCH" && <Field label={t("data.provSource")} className="md:col-span-2"><Input value={imp.source} onChange={(e) => setImp({ ...imp, source: e.target.value })} /></Field>}
                  {imp.data_class === "AUTHORIZED_SCHOOL" && <>
                    <Field label={t("data.provAuth")}><Input value={imp.authorization_reference} onChange={(e) => setImp({ ...imp, authorization_reference: e.target.value })} /></Field>
                    <Field label={t("data.provController")}><Input value={imp.data_controller} onChange={(e) => setImp({ ...imp, data_controller: e.target.value })} /></Field>
                  </>}
                </div>
                <Button variant="primary" onClick={doImport} data-testid="do-import">{t("data.importBtn")}</Button>
                <details className="text-xs"><summary className="cursor-pointer text-ink-2">{t("data.rowsPreview")} ({insp.n_rows})</summary>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-panel-2 p-2 text-[11px] text-ink-2">{JSON.stringify(insp.preview, null, 1)}</pre></details>
              </div>
            )}
          </Panel>

          <Panel title={t("data.referencesTitle")} bodyClassName="p-0">
            <Table dense head={["ID", "", t("data.verification")]}
              rows={(meta?.references ?? []).map((r) => [<span key="i" className="font-mono">{r.id}</span>, <span key="c" className="text-ink-2">{r.citation}{r.doi ? ` doi:${r.doi}` : ""}</span>, <span key="v" className="text-[11px] text-muted">{r.verification}</span>])} />
          </Panel>
          <p className="text-xs text-muted">{pick(config?.parameter_set.statement)}</p>
        </div>
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
