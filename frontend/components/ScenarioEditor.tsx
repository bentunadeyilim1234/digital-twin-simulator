"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { DOMAIN_COLOR, fmt } from "@/lib/format";
import type { Scenario } from "@/lib/types";
import { Badge, Button, Field, Input, NumberField, Select, Slider, Switch, Textarea, cn } from "@/components/ui";

function Section({ title, children, defaultOpen = true, testId }: { title: string; children: React.ReactNode; defaultOpen?: boolean; testId?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-line last:border-b-0" data-testid={testId}>
      <button className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-ink-2 hover:text-ink" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{title}
      </button>
      {open && <div className="space-y-3 px-3 pb-3">{children}</div>}
    </div>
  );
}

/** Editor for every scenario field: schedules, external conditions, data, overrides and initial conditions. */
export function ScenarioEditor({ draft, update }: { draft: Scenario; update: (fn: (d: Scenario) => void) => void }) {
  const { t, pick } = useI18n();
  const { config, datasets, meta } = useApp();
  const [newOverride, setNewOverride] = useState("");
  if (!config) return null;
  const params = (meta?.uncertain_parameters ?? []).filter((p) => !(p in draft.parameter_overrides));

  return (
    <div className="text-xs">
      <Section title={t("common.scenario")}>
        <Field label={t("common.name")}><Input value={draft.name} onChange={(e) => update((d) => { d.name = e.target.value; })} data-testid="scenario-name" /></Field>
        <Field label={t("lab.horizon")}>
          <div className="flex items-center gap-2">
            <Slider value={draft.horizon_months} min={1} max={config.time.max_horizon} step={1} onChange={(v) => update((d) => { d.horizon_months = Math.round(v); })} label="horizon" />
            <NumberField value={draft.horizon_months} min={1} max={config.time.max_horizon} digits={0} onChange={(v) => update((d) => { d.horizon_months = Math.round(v); })} label="horizon months" />
          </div>
        </Field>
      </Section>

      <Section title={t("lab.interventions")} testId="interventions-section">
        {draft.interventions.length === 0 && <p className="text-muted">{t("common.none")}</p>}
        {draft.interventions.map((iv, i) => (
          <div key={i} className="space-y-2 rounded-md border border-line bg-panel-2 p-2" data-testid={`intervention-${i}`}>
            <div className="flex items-center gap-2">
              <Select value={iv.key} onChange={(e) => update((d) => { d.interventions[i].key = e.target.value; })} aria-label="intervention type">
                {config.interventions.map((x) => <option key={x.key} value={x.key}>{pick(x.labels)}</option>)}
              </Select>
              <Button variant="ghost" size="icon" aria-label={t("common.remove")} onClick={() => update((d) => { d.interventions.splice(i, 1); })}><Trash2 size={13} /></Button>
            </div>
            <Field label={`${t("lab.intensity")} (${fmt(iv.intensity, 2)})`}>
              <div className="flex items-center gap-2">
                <Slider value={iv.intensity} onChange={(v) => update((d) => { d.interventions[i].intensity = Math.round(v * 100) / 100; })} label={`intensity ${iv.key}`} />
                <NumberField value={iv.intensity} digits={2} onChange={(v) => update((d) => { d.interventions[i].intensity = v; })} label={`intensity value ${iv.key}`} />
              </div>
            </Field>
            <div className="grid grid-cols-3 gap-2">
              <Field label={t("lab.start")}><NumberField className="w-full" value={iv.start_month} min={1} max={draft.horizon_months} digits={0} onChange={(v) => update((d) => { d.interventions[i].start_month = Math.round(v); })} label="start" /></Field>
              <Field label={t("lab.ramp")}><NumberField className="w-full" value={iv.ramp_months} min={0} max={24} digits={0} onChange={(v) => update((d) => { d.interventions[i].ramp_months = Math.round(v); })} label="ramp" /></Field>
              <Field label={t("lab.endMonth")}>
                <Input className="h-7 text-xs" placeholder="—" value={iv.end_month ?? ""} inputMode="numeric"
                  onChange={(e) => update((d) => { const n = parseInt(e.target.value, 10); d.interventions[i].end_month = Number.isFinite(n) ? n : null; })} />
              </Field>
            </div>
          </div>
        ))}
        <Button size="sm" data-testid="add-intervention" onClick={() => update((d) => { d.interventions.push({ key: config.interventions[0].key, intensity: 0.5, start_month: 1, ramp_months: 3, end_month: null }); })}>
          <Plus size={13} />{t("lab.addIntervention")}
        </Button>
      </Section>

      <Section title={t("lab.external")} defaultOpen={false}>
        {config.external_conditions.map((e) => {
          const v = draft.external[e.key]?.value ?? e.default;
          const scheduled = !!draft.external[e.key]?.values?.length;
          return (
            <Field key={e.key} label={`${pick(e.labels)}${scheduled ? " (schedule)" : ""}`} hint={pick(e.description)}>
              <div className="flex items-center gap-2">
                <Slider value={v} disabled={scheduled} onChange={(x) => update((d) => { d.external[e.key] = { value: Math.round(x * 100) / 100 }; })} label={e.key} />
                <NumberField value={v} digits={2} disabled={scheduled} onChange={(x) => update((d) => { d.external[e.key] = { value: x }; })} label={`${e.key} value`} />
              </div>
            </Field>
          );
        })}
      </Section>

      <Section title={t("lab.datasetSel")} defaultOpen={false}>
        <Field label={t("common.dataset")}>
          <Select value={draft.dataset_id ?? ""} onChange={(e) => update((d) => { d.dataset_id = e.target.value || null; })}>
            <option value="">{t("common.none")}</option>
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.data_class}</option>)}
          </Select>
        </Field>
        {draft.dataset_id && (
          <Field label={t("lab.anchor")}>
            <Select value={draft.dataset_anchor} onChange={(e) => update((d) => { d.dataset_anchor = e.target.value as "latest" | "replay"; })}>
              <option value="latest">{t("lab.anchorLatest")}</option>
              <option value="replay">{t("lab.anchorReplay")}</option>
            </Select>
          </Field>
        )}
      </Section>

      <Section title={t("lab.paramOverrides")} defaultOpen={false}>
        {Object.entries(draft.parameter_overrides).map(([pid, v]) => (
          <div key={pid} className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-mono text-[11px]" title={pid}>{pid}</span>
            <NumberField value={v} min={0} max={1000} digits={3} onChange={(x) => update((d) => { d.parameter_overrides[pid] = x; })} label={pid} />
            <Button variant="ghost" size="icon" aria-label={t("common.remove")} onClick={() => update((d) => { delete d.parameter_overrides[pid]; })}><Trash2 size={13} /></Button>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Select value={newOverride} onChange={(e) => setNewOverride(e.target.value)} aria-label={t("lab.addOverride")}>
            <option value="">{t("lab.addOverride")}…</option>
            {params.map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Button size="sm" disabled={!newOverride} onClick={() => {
            const p = [...config.parameters].find((x) => x.id === newOverride);
            const e = config.edges.find((x) => `edge.${x.id}` === newOverride);
            update((d) => { d.parameter_overrides[newOverride] = p ? p.value : e ? e.coefficient : 0; });
            setNewOverride("");
          }}><Plus size={13} /></Button>
        </div>
      </Section>

      <Section title={t("lab.variables")} defaultOpen={false} testId="lab-variables">
        {config.domains.map((dom) => (
          <div key={dom.id} className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-ink-2"><span className="h-2 w-2 rounded-sm" style={{ background: DOMAIN_COLOR[dom.id] }} />{t(`domains.${dom.id}`)}</div>
            {dom.variables.map((sym) => {
              const v = config.variables.find((x) => x.symbol === sym)!;
              const manual = draft.variable_modes?.[sym] === "manual";
              const val = draft.initial_state[sym] ?? v.initial;
              return (
                <div key={sym} className={cn("grid grid-cols-[30px_1fr_64px_auto] items-center gap-1.5 rounded px-1", manual && "bg-[#211a0c]")} data-testid={`lab-var-${sym}`}>
                  <span className="font-mono font-semibold" title={pick(v.labels)}>{sym}</span>
                  <Slider value={val} onChange={(x) => update((d) => { d.initial_state[sym] = Math.round(x * 1000) / 1000; if (manual) d.overrides[sym] = { value: d.initial_state[sym] }; })} label={`${sym} initial`} />
                  <NumberField className="w-16" value={val} onChange={(x) => update((d) => { d.initial_state[sym] = x; if (manual) d.overrides[sym] = { value: x }; })} label={`${sym} initial value`} />
                  <span title={t("variables.modeManual")}>
                    <Switch checked={manual} label={`${sym} manual`} onChange={(m) => update((d) => {
                      d.variable_modes = { ...d.variable_modes }; d.overrides = { ...d.overrides };
                      if (m) { d.variable_modes[sym] = "manual"; d.overrides[sym] = { value: d.initial_state[sym] ?? v.initial }; }
                      else { delete d.variable_modes[sym]; delete d.overrides[sym]; }
                    })} />
                  </span>
                </div>
              );
            })}
          </div>
        ))}
        {Object.keys(draft.variable_modes ?? {}).length > 0 && <Badge tone="warm">{t("variables.manualActive")}: {Object.keys(draft.variable_modes).join(", ")}</Badge>}
      </Section>

      <Section title={t("common.notes")} defaultOpen={false}>
        <Textarea value={draft.notes} onChange={(e) => update((d) => { d.notes = e.target.value; })} aria-label={t("common.notes")} />
      </Section>
    </div>
  );
}
