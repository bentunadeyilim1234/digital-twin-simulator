"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Layers, LocateFixed, Map } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { scenarioName, useApp } from "@/lib/store";
import { diverging, fmt, fmtSigned, sequential } from "@/lib/format";
import type { CompareResult } from "@/lib/types";
import { LEVEL_RANGE, ZONES, levelToRamp, zoneById, zoneIndicators, zoneTint, type FloorId, type TintMode, type ZoneId } from "@/lib/zones";
import { Badge, Button, ErrorBox, Field, PageHeader, Panel, Select, Slider, Spinner, Table, cn } from "@/components/ui";
import { SchoolPlan2D } from "@/components/twin/SchoolPlan2D";
import type { SceneHandle } from "@/components/twin/SchoolScene";

// Lazy-loaded: three.js is only downloaded when this page is opened.
const SchoolScene = dynamic(() => import("@/components/twin/SchoolScene"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted"><Spinner className="mr-2" />3D…</div>,
});

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function TwinPage() {
  const { t, lang } = useI18n();
  const { scenarios, configHash } = useApp();
  const baseline = scenarios.find((s) => s.is_baseline);
  const [sid, setSid] = useState<string>(() => scenarios.find((s) => s.template_id === "S4")?.id ?? baseline?.id ?? "");
  const [cmp, setCmp] = useState<CompareResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [month, setMonth] = useState(12);
  const [mode, setMode] = useState<TintMode>("level");
  const [floor, setFloor] = useState<FloorId | "all">("all");
  const [selected, setSelected] = useState<ZoneId | null>("support");
  const [view, setView] = useState<"3d" | "2d">("3d");
  const [webgl, setWebgl] = useState(true);
  const sceneRef = useRef<SceneHandle>(null);

  useEffect(() => {
    const ok = hasWebGL();
    setWebgl(ok);
    if (!ok) setView("2d");
  }, []);

  useEffect(() => {
    if (!sid || !baseline) return;
    let cancelled = false;
    api.post<CompareResult>("/compare", { scenario_ids: Array.from(new Set([baseline.id, sid])), baseline_id: baseline.id, save: false })
      .then((r) => { if (!cancelled) { setCmp(r); setErr(null); setMonth((m) => Math.min(m, r.results[sid].horizon)); } })
      .catch((e) => !cancelled && setErr(String(e.message)));
    return () => { cancelled = true; };
  }, [sid, baseline, configHash]);

  const labels = useMemo(() => Object.fromEntries(ZONES.map((z) => [z.id, t(`twin.zones.${z.id}`)])) as Record<ZoneId, string>, [t]);
  const tints = useMemo(() => {
    const out = {} as Record<ZoneId, string>;
    for (const z of ZONES) {
      const v = cmp ? zoneTint(cmp, sid, z, month, mode) : null;
      out[z.id] = mode === "level" ? sequential(levelToRamp(v)) : diverging(v);
    }
    return out;
  }, [cmp, sid, month, mode]);

  const r = cmp?.results[sid];
  const b = cmp ? cmp.results[cmp.baseline_id] : undefined;
  const N = r?.horizon ?? 12;
  const zone = selected ? zoneById(selected) : null;
  const floors: (FloorId | "all")[] = ["all", 0, 1, 2, "outdoor"];
  const floorLabel = (f: FloorId | "all") => (f === "all" ? t("twin.allFloors") : f === "outdoor" ? t("twin.outdoor") : f === 0 ? t("twin.ground") : t("twin.floor", { n: f }));

  return (
    <div className="space-y-4">
      <PageHeader title={t("twin.title")} subtitle={t("twin.subtitle")} />
      <ErrorBox error={err} />
      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)_320px]">
        {/* Left: controls */}
        <div className="space-y-3">
          <Panel>
            <div className="space-y-3">
              <Field label={t("twin.scenarioSel")}>
                <Select value={sid} onChange={(e) => setSid(e.target.value)} data-testid="twin-scenario">
                  {scenarios.map((s) => <option key={s.id} value={s.id}>{scenarioName(s, lang)}</option>)}
                </Select>
              </Field>
              <Field label={`${t("twin.month")}: ${month}`}>
                <Slider value={month} min={0} max={N} step={1} onChange={(v) => setMonth(Math.round(v))} label="twin month" />
              </Field>
              <Field label={t("twin.colorBy")}>
                <Select value={mode} onChange={(e) => setMode(e.target.value as TintMode)} data-testid="twin-mode">
                  <option value="level">{t("twin.readiness")}</option>
                  <option value="vsBaseline">{t("twin.change")}</option>
                  <option value="vsStart">{t("twin.before")} → {t("twin.after", { n: month })}</option>
                </Select>
              </Field>
              <div className="flex items-center justify-between text-[11px] text-muted" aria-hidden>
                <span className="tabular">{mode === "level" ? `≤${LEVEL_RANGE[0].toFixed(2)}` : "−0.10"}</span>
                <span className="mx-2 h-2 flex-1 rounded-sm" style={{ background: mode === "level" ? "linear-gradient(90deg,#0d366b,#2a78d6,#9ec5f4)" : "linear-gradient(90deg,#e66767,#383835,#6da7ec)" }} />
                <span className="tabular">{mode === "level" ? `≥${LEVEL_RANGE[1].toFixed(2)}` : "+0.10"}</span>
              </div>
            </div>
          </Panel>
          <Panel title={<span className="flex items-center gap-1.5"><Layers size={13} />{t("twin.floors")}</span>}>
            <div className="flex flex-wrap gap-1" role="group" aria-label={t("twin.floors")}>
              {floors.map((f) => (
                <Button key={String(f)} size="sm" variant={floor === f ? "primary" : "outline"} onClick={() => setFloor(f)} data-testid={`floor-${f}`} aria-pressed={floor === f}>
                  {floorLabel(f)}
                </Button>
              ))}
            </div>
          </Panel>
          <Panel title={t("twin.departments")} bodyClassName="p-1">
            <ul data-testid="zone-list">
              {ZONES.map((z) => (
                <li key={z.id}>
                  <button onClick={() => { setSelected(z.id); if (!(z.floors as (FloorId | "all")[]).includes(floor)) setFloor(z.floors.length > 1 ? "all" : z.floors[0]); }} data-testid={`zone-${z.id}`} aria-pressed={selected === z.id}
                    className={cn("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-panel-2", selected === z.id && "bg-panel-3 text-ink")}>
                    <span className="h-3 w-3 shrink-0 rounded-sm border border-black/40" style={{ background: tints[z.id] }} />
                    <span className="flex-1 truncate text-ink-2">{labels[z.id]}</span>
                    <span className="font-mono text-[10px] text-muted">{z.indicators.join("·")}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        {/* Centre: model */}
        <div className="min-w-0">
          <div className="relative h-[460px] overflow-hidden rounded-lg border border-line bg-[#0e1217] md:h-[600px]" data-testid="twin-viewport" data-selected-zone={selected ?? ""} data-view={view}>
            {view === "3d" && webgl
              ? <SchoolScene ref={sceneRef} tints={tints} selected={selected} onSelect={setSelected} floor={floor} labels={labels} />
              : <SchoolPlan2D tints={tints} selected={selected} onSelect={setSelected} floor={floor} labels={labels} />}
            {selected && (
              <div className="pointer-events-none absolute left-2 top-2 rounded border border-[#7a5a1e] bg-[#12161c]/95 px-2 py-1 text-xs text-[#f0c070]" data-testid="twin-label">
                {labels[selected]} · {floorLabel(floor)}
              </div>
            )}
            <div className="absolute right-2 top-2 flex gap-1">
              {webgl && (
                <Button size="sm" variant="secondary" onClick={() => setView(view === "3d" ? "2d" : "3d")} data-testid="toggle-view">
                  {view === "3d" ? <><Map size={13} />{t("twin.view2d")}</> : <><Box size={13} />{t("twin.view3d")}</>}
                </Button>
              )}
              {view === "3d" && webgl && <Button size="sm" variant="secondary" onClick={() => sceneRef.current?.resetView()} data-testid="reset-view"><LocateFixed size={13} />{t("twin.resetView")}</Button>}
            </div>
            {!cmp && <div className="absolute inset-0 grid place-items-center"><Spinner /></div>}
          </div>
          {!webgl && <p className="mt-2 text-xs text-[#f0c070]">{t("twin.noWebgl")}</p>}
          <p className="mt-2 text-[11px] text-muted">{t("twin.disclaimer")}</p>
        </div>

        {/* Right: selected area */}
        <Panel title={t("twin.selected")} className="h-fit">
          {!zone || !r ? <p className="text-xs text-muted">{t("twin.selectHint")}</p> : (
            <div className="space-y-3 text-xs" data-testid="twin-selected" data-zone={zone.id}>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-sm" style={{ background: tints[zone.id] }} />
                <span className="text-sm font-semibold text-ink">{labels[zone.id]}</span>
              </div>
              <div className="flex flex-wrap gap-1">{zone.floors.map((f) => <Badge key={String(f)} tone="outline">{floorLabel(f)}</Badge>)}</div>
              <div>
                <div className="mb-1 font-medium text-ink-2">{t("twin.linked")}</div>
                <Table dense testId="twin-indicators"
                  head={["", t("twin.before"), t("twin.after", { n: month }), t("twin.baselineCompare")]}
                  rows={zoneIndicators(r, zone, month).map(({ key, value }) => {
                    const start = zoneIndicators(r, zone, 0).find((x) => x.key === key)?.value ?? null;
                    const base = b ? zoneIndicators(b, zone, month).find((x) => x.key === key)?.value ?? null : null;
                    return [<span key="k" className="font-mono" title={key}>{key}</span>, fmt(start), <span key="v" className="text-ink">{fmt(value)}</span>,
                      <span key="d" className={cn((value ?? 0) - (base ?? 0) > 1e-6 ? "text-[#86b6ef]" : (value ?? 0) - (base ?? 0) < -1e-6 ? "text-[#f09a9a]" : "text-ink-2")}>{base === null || value === null ? "—" : fmtSigned(value - base)}</span>];
                  })} />
              </div>
              {zone.id === "support" && (
                <div className="rounded-md border border-line bg-panel-2 p-2">
                  <div className="mb-1 font-medium text-ink-2">{t("lab.stockflow")}</div>
                  <dl className="grid grid-cols-[1fr_auto] gap-x-2 gap-y-0.5 tabular">
                    <dt className="text-muted">{t("flows.Q")}</dt><dd>{fmt(r.flows.Q[month], 1)}</dd>
                    <dt className="text-muted">{t("flows.I")}</dt><dd>{fmt(r.flows.I[month], 1)}</dd>
                    <dt className="text-muted">{t("flows.C_flow")}</dt><dd>{fmt(r.flows.C_flow[month], 1)}</dd>
                    <dt className="text-muted">{t("flows.mu")}</dt><dd>{fmt(r.flows.mu[month], 1)}</dd>
                  </dl>
                  <p className="mt-1 text-[11px] text-muted">{t("flows.requestsNote")}</p>
                </div>
              )}
              <p className="text-[11px] text-muted">{t("twin.subtitle")}</p>
              <p className="text-[11px] text-muted">hash {r.provenance.config_hash} · {r.provenance.data_class}</p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
