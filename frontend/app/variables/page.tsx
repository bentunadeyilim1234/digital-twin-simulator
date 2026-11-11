"use client";

import { useEffect, useMemo, useState } from "react";
import { Save, Undo2 } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { scenarioName, useApp } from "@/lib/store";
import { useScenarioDraft } from "@/lib/useScenarioDraft";
import type { Dataset, DomainId } from "@/lib/types";
import { Badge, Button, ErrorBox, Field, PageHeader, Select, Toast } from "@/components/ui";
import { VariableControl } from "@/components/VariableControl";
import { DOMAIN_COLOR } from "@/lib/format";

export default function VariablesPage() {
  const { t, lang } = useI18n();
  const { config, scenarios, datasets, activeScenarioId, setActive } = useApp();
  const { draft, dirty, update, save, revert, saving, error } = useScenarioDraft(activeScenarioId);
  const [fDomain, setFDomain] = useState("all");
  const [fRole, setFRole] = useState("all");
  const [fEv, setFEv] = useState("all");
  const [fQual, setFQual] = useState("all");
  const [fMode, setFMode] = useState("all");
  const [dsId, setDsId] = useState<string>(datasets[0]?.id ?? "");
  const [ds, setDs] = useState<Dataset | null>(null);
  const [raw, setRaw] = useState<Record<string, { raw: number | null; unit: string }>>({});
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!dsId) { setDs(null); return; }
    api.get<Dataset>(`/datasets/${dsId}`).then(setDs).catch(() => setDs(null));
  }, [dsId]);

  // Raw-unit equivalents are computed by the engine (single source of normalisation logic)
  const initKey = draft ? JSON.stringify(draft.initial_state) : "";
  useEffect(() => {
    if (!draft) return;
    const id = setTimeout(() => {
      api.post<Record<string, { raw: number | null; unit: string }>>("/denormalize", { values: draft.initial_state }).then(setRaw).catch(() => undefined);
    }, 200);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initKey]);

  const quality = useMemo(() => {
    const q = datasets.find((d) => d.id === dsId)?.quality?.variables ?? {};
    return (sym: string) => {
      const r = q[sym];
      if (!r || !r.present) return "nodata";
      return r.missing_pct <= 5 ? "complete" : "gaps";
    };
  }, [datasets, dsId]);

  if (!config || !draft) return null;
  const vars = config.variables.filter((v) =>
    (fDomain === "all" || v.domain === fDomain) && (fRole === "all" || v.role === fRole) && (fEv === "all" || v.measurement_evidence === fEv)
    && (fMode === "all" || (fMode === "manual") === (draft.variable_modes?.[v.symbol] === "manual")) && (fQual === "all" || quality(v.symbol) === fQual));

  const shiftDomain = (d: DomainId, delta: number) =>
    update((s) => {
      for (const sym of config.domains.find((x) => x.id === d)!.variables) {
        s.initial_state[sym] = Math.min(1, Math.max(0, Math.round(((s.initial_state[sym] ?? 0) + delta) * 1000) / 1000));
        if (s.variable_modes?.[sym] === "manual") s.overrides[sym] = { value: s.initial_state[sym] };
      }
    });

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("variables.title")} subtitle={t("variables.subtitle")}
        actions={<>
          {dirty && <Badge tone="warm">{t("variables.unsaved")}</Badge>}
          <Button variant="ghost" onClick={revert} disabled={!dirty}><Undo2 size={14} />{t("common.reset")}</Button>
          <Button variant="primary" data-testid="save-variables" disabled={!dirty || saving} onClick={async () => { if (await save()) setToast(t("common.saved")); }}>
            <Save size={14} />{t("variables.saveScenario")}
          </Button>
        </>}
      />
      <ErrorBox error={error} />
      <div className="grid gap-3 rounded-lg border border-line bg-panel p-3 sm:grid-cols-3 lg:grid-cols-7">
        <Field label={t("variables.editing")} className="sm:col-span-2 lg:col-span-2">
          <Select value={draft.id} onChange={(e) => setActive(e.target.value)} data-testid="var-scenario">
            {scenarios.map((s) => <option key={s.id} value={s.id}>{scenarioName(s, lang)}{s.is_baseline ? ` · ${t("common.baseline")}` : ""}</option>)}
          </Select>
        </Field>
        <Field label={t("variables.filterDomain")}>
          <Select value={fDomain} onChange={(e) => setFDomain(e.target.value)} data-testid="filter-domain">
            <option value="all">{t("common.all")}</option>
            {config.domains.map((d) => <option key={d.id} value={d.id}>{t(`domains.${d.id}`)}</option>)}
          </Select>
        </Field>
        <Field label={t("variables.filterType")}>
          <Select value={fRole} onChange={(e) => setFRole(e.target.value)}>
            <option value="all">{t("common.all")}</option>
            {["state", "context", "derived"].map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
          </Select>
        </Field>
        <Field label={t("variables.filterEvidence")}>
          <Select value={fEv} onChange={(e) => setFEv(e.target.value)}>
            <option value="all">{t("common.all")}</option>
            {["E1", "E2", "H", "L"].map((r) => <option key={r} value={r}>{r}</option>)}
          </Select>
        </Field>
        <Field label={t("variables.filterQuality")}>
          <Select value={fQual} onChange={(e) => setFQual(e.target.value)}>
            <option value="all">{t("common.all")}</option>
            <option value="complete">≤5% {t("data.missing").toLowerCase()}</option>
            <option value="gaps">&gt;5% {t("data.missing").toLowerCase()}</option>
            <option value="nodata">{t("variables.noHistory")}</option>
          </Select>
        </Field>
        <Field label={t("variables.filterMode")}>
          <Select value={fMode} onChange={(e) => setFMode(e.target.value)}>
            <option value="all">{t("common.all")}</option>
            <option value="model">{t("variables.modeModel")}</option>
            <option value="manual">{t("variables.modeManual")}</option>
          </Select>
        </Field>
        <Field label={t("common.dataset")} className="sm:col-span-2 lg:col-span-2">
          <Select value={dsId} onChange={(e) => setDsId(e.target.value)}>
            <option value="">{t("common.none")}</option>
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name} · {t(`dataClass.${d.data_class}`)}</option>)}
          </Select>
        </Field>
        <div className="flex flex-wrap items-end gap-2 sm:col-span-3 lg:col-span-5">
          <span className="text-xs text-ink-2">{t("variables.groupShift")}:</span>
          {config.domains.map((d) => (
            <span key={d.id} className="flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-xs">
              <span className="h-2 w-2 rounded-sm" style={{ background: DOMAIN_COLOR[d.id] }} />{d.id}
              <Button size="sm" variant="ghost" className="h-6 px-1.5" onClick={() => shiftDomain(d.id, -0.05)} aria-label={`${d.id} -0.05`}>−.05</Button>
              <Button size="sm" variant="ghost" className="h-6 px-1.5" onClick={() => shiftDomain(d.id, 0.05)} aria-label={`${d.id} +0.05`}>+.05</Button>
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {vars.map((v) => (
          <VariableControl key={v.symbol} v={v} draft={draft} onChange={update} raw={raw[v.symbol]} history={ds?.variables?.[v.symbol] ?? null} templateValue={v.initial} />
        ))}
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
