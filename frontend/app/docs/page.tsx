"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { fmt } from "@/lib/format";
import type { Parameter } from "@/lib/types";
import { Badge, ErrorBox, EvidenceBadge, PageHeader, Panel, Spinner, Table } from "@/components/ui";

interface Eq { target?: string; name?: string; symbolic: string; numeric: string; transition?: string }
interface Equations { general: string[]; state: Eq[]; context: Eq[]; flows: Eq[]; indices: Eq[]; parameters: Parameter[] }

const SECTIONS = ["purpose", "equations", "dictionary", "assumptions", "registry", "envelope", "evidenceTitle", "limitations", "references"];

export default function DocsPage() {
  const { t, tl, pick } = useI18n();
  const { config, meta } = useApp();
  const [eq, setEq] = useState<Equations | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.get<Equations>("/model/equations").then(setEq).catch((e) => setErr(String(e.message))); }, []);
  if (!config) return null;
  const env = config.validation_envelope as { statement?: { en: string; tr: string }; validated_horizon_months?: number; supported_school_contexts?: { en: string; tr: string }; data_frequency?: string };

  const EqBlock = ({ items }: { items: Eq[] }) => (
    <div className="space-y-2">
      {items.map((e, i) => (
        <div key={i} className="rounded-md border border-line bg-panel-2 p-2">
          {e.name && <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted">{e.name}</div>}
          <code className="block whitespace-pre-wrap break-words font-mono text-xs text-ink">{e.symbolic}</code>
          {e.numeric && <code className="mt-1 block whitespace-pre-wrap break-words font-mono text-[11px] text-[#9ec5f4]">{e.numeric}</code>}
          {e.transition && <code className="mt-1 block whitespace-pre-wrap break-words font-mono text-[11px] text-ink-2">{e.transition}</code>}
        </div>
      ))}
    </div>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[200px_1fr]">
      <nav className="hidden lg:block" aria-label="Documentation sections">
        <ul className="sticky top-24 space-y-1 text-xs">
          {SECTIONS.map((s) => <li key={s}><a href={`#${s}`} className="text-ink-2 hover:text-ink">{s === "references" ? t("common.references") : t(`docs.${s}`)}</a></li>)}
        </ul>
      </nav>
      <div className="min-w-0 space-y-4">
        <PageHeader title={t("docs.title")} subtitle={t("docs.subtitle")} />
        <ErrorBox error={err} />
        <Panel id="purpose" title={t("docs.purpose")}>
          <p className="text-sm text-ink-2">{t("docs.purposeText")}</p>
          <h3 className="mt-3 text-xs font-semibold text-ink">{t("docs.cannot")}</h3>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink-2">{tl("docs.cannotList").map((x) => <li key={x}>{x}</li>)}</ul>
          <p className="mt-3 text-xs text-[#e7c27a]">{pick(config.parameter_set.statement)}</p>
        </Panel>
        <Panel id="equations" title={t("docs.equations")} subtitle={t("docs.timing")}>
          {!eq ? <Spinner /> : (
            <div className="space-y-4" data-testid="equations">
              <div><h3 className="mb-2 text-xs font-semibold text-ink">{t("docs.general")}</h3><EqBlock items={eq.general.map((g) => ({ symbolic: g, numeric: "" }))} /></div>
              <div><h3 className="mb-2 text-xs font-semibold text-ink">{t("docs.stateEq")}</h3><EqBlock items={eq.state} /></div>
              <div><h3 className="mb-2 text-xs font-semibold text-ink">{t("docs.contextEq")}</h3><EqBlock items={eq.context.filter((c) => c.symbolic.includes("Δ"))} /></div>
              <div><h3 className="mb-2 text-xs font-semibold text-ink">{t("docs.flowEq")}</h3><EqBlock items={eq.flows} /></div>
              <div><h3 className="mb-2 text-xs font-semibold text-ink">{t("docs.indexEq")}</h3><EqBlock items={eq.indices} /></div>
            </div>
          )}
        </Panel>
        <Panel id="dictionary" title={t("docs.dictionary")} bodyClassName="p-0">
          <Table dense head={["ID", "", t("common.name"), t("variables.filterType"), t("common.unit"), t("common.range"), t("common.direction"), t("common.evidence")]}
            rows={config.variables.map((v) => [v.id, <span key="s" className="font-mono">{v.symbol}</span>, <span key="n" title={pick(v.definition)}>{pick(v.labels)}</span>, t(`roles.${v.role}`), v.measurement.unit, `[${v.measurement.lower}, ${v.measurement.upper}]`, t(`common.${v.measurement.direction}`), <EvidenceBadge key="e" e={v.measurement_evidence} />])} />
        </Panel>
        <Panel id="assumptions" title={t("docs.assumptions")} bodyClassName="p-0">
          <Table dense head={["ID", "", "→", "coef", t("common.evidence"), t("common.references"), t("common.description")]}
            rows={config.edges.filter((e) => e.kind !== "structural").map((e) => [<span key="i" className="font-mono">{e.id}</span>, e.hypothesis ? <Badge key="h" tone="accent">{e.hypothesis}</Badge> : "", `${e.source} → ${e.target}`, `${e.sign > 0 ? "+" : "−"}${fmt(e.coefficient, 3)}${e.enabled ? "" : " (off)"}`, <EvidenceBadge key="e" e={e.evidence} />, <span key="r" className="text-[11px]">{e.references.join(", ") || "—"}</span>, <span key="d" className="text-ink-2">{pick(e.description)}</span>])} />
        </Panel>
        <Panel id="registry" title={t("docs.registry")} bodyClassName="p-0">
          {eq && <Table dense head={[t("common.parameter"), "", t("common.value"), t("common.range"), t("common.unit"), t("docs.provenanceCol")]}
            rows={eq.parameters.map((p) => [<span key="i" className="font-mono">{p.id}</span>, p.symbol, fmt(p.value, 4), p.range ? `[${fmt(p.range[0], 3)}, ${fmt(p.range[1], 3)}]` : "—", p.unit, <Badge key="p" tone={p.provenance === "calibrated" ? "good" : "warm"}>{p.provenance}</Badge>])} />}
        </Panel>
        <Panel id="envelope" title={t("docs.envelope")}>
          <ul className="space-y-1 text-sm text-ink-2">
            <li>{t("overview.validatedHorizon", { n: env.validated_horizon_months ?? 0 })}</li>
            <li>{pick(env.supported_school_contexts)}</li>
            <li>{env.data_frequency}</li>
            <li className="text-[#e7c27a]">{pick(env.statement)}</li>
          </ul>
        </Panel>
        <Panel id="evidenceTitle" title={t("docs.evidenceTitle")}>
          <ul className="space-y-1 text-sm text-ink-2">{(["E1", "E2", "H", "L"] as const).map((k) => <li key={k} className="flex items-center gap-2"><EvidenceBadge e={k} />{t(`evidenceLabels.${k}`)}</li>)}</ul>
        </Panel>
        <Panel id="limitations" title={t("docs.limitations")}>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-ink-2">{tl("docs.limitationsList").map((x) => <li key={x}>{x}</li>)}</ul>
        </Panel>
        <Panel id="references" title={t("common.references")}>
          <ol className="list-decimal space-y-1 pl-5 text-xs text-ink-2">
            {(meta?.references ?? []).map((r) => <li key={r.id}><span className="font-mono text-muted">[{r.id}]</span> {r.citation}{r.doi ? ` https://doi.org/${r.doi}` : ""} <span className="text-[10px] text-muted">({r.verification})</span></li>)}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
