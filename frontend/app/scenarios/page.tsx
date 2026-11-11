"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Download, FileJson, FlaskConical, Pencil, Plus, Star, Trash2, Upload } from "lucide-react";
import { api, download, saveJson } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { scenarioName, useApp } from "@/lib/store";
import { fmt, fmtDate, scenarioColor } from "@/lib/format";
import type { RunSummary, Scenario } from "@/lib/types";
import { Badge, Button, Dialog, ErrorBox, Field, Input, PageHeader, Panel, Select, Table, Toast } from "@/components/ui";

export default function ScenariosPage() {
  const { t, lang, pick } = useI18n();
  const router = useRouter();
  const { scenarios, meta, refreshScenarios, refreshConfig, refreshDatasets, setActive } = useApp();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [tpl, setTpl] = useState("S1");
  const [renaming, setRenaming] = useState<Scenario | null>(null);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<Scenario | null>(null);
  const [projectFile, setProjectFile] = useState<unknown>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const projRef = useRef<HTMLInputElement>(null);
  const allIds = scenarios.map((s) => s.id);

  const loadRuns = useCallback(() => api.get<RunSummary[]>("/runs?limit=60").then(setRuns).catch((e) => setErr(String(e.message))), []);
  useEffect(() => { void loadRuns(); }, [loadRuns]);

  const act = async (fn: () => Promise<unknown>, msg?: string) => {
    try { setErr(null); await fn(); await refreshScenarios(); if (msg) setToast(msg); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  const importScenarioFile = async (f: File) => {
    try {
      const data = JSON.parse(await f.text());
      await act(() => api.post("/scenarios/import", Array.isArray(data) ? { scenarios: data } : data.scenarios ? data : { scenario: data }), t("common.saved"));
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  return (
    <div className="space-y-4">
      <PageHeader title={t("scenarios.title")} subtitle={t("scenarios.subtitle")}
        actions={<>
          <Select value={tpl} onChange={(e) => setTpl(e.target.value)} className="w-56" aria-label={t("scenarios.template")} data-testid="template-select">
            {meta?.templates.map((x) => <option key={x.id} value={x.id}>{pick(x.labels)}</option>)}
          </Select>
          <Button variant="primary" data-testid="new-from-template" onClick={() => act(async () => {
            const tp = meta!.templates.find((x) => x.id === tpl)!;
            const s = await api.post<Scenario>("/scenarios", { template_id: tpl, name: `${pick(tp.labels)} — ${t("common.copy")}` });
            setActive(s.id);
          }, t("common.saved"))}><Plus size={14} />{t("scenarios.newFrom")}</Button>
          <Button onClick={() => fileRef.current?.click()}><Upload size={14} />{t("scenarios.importJson")}</Button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void importScenarioFile(f); e.target.value = ""; }} />
        </>}
      />
      <ErrorBox error={err} />
      <Panel title={t("common.scenarios")} bodyClassName="p-0">
        <Table testId="scenario-table"
          head={["", t("common.name"), t("scenarios.template"), t("scenarios.interventions"), t("lab.horizon"), t("common.updated"), ""]}
          rows={scenarios.map((s) => [
            <span key="c" className="block h-2.5 w-2.5 rounded-sm" style={{ background: scenarioColor(s.id, allIds) }} />,
            <span key="n" className="flex items-center gap-1.5">
              <span className="text-ink">{scenarioName(s, lang)}</span>
              {s.is_baseline && <Badge tone="accent">{t("common.baseline")}</Badge>}
              {Object.keys(s.variable_modes ?? {}).length > 0 && <Badge tone="warm">manual</Badge>}
            </span>,
            s.template_id ?? "—",
            <span key="i" className="text-ink-2">{s.interventions.map((iv) => `${iv.key.replace("U_", "")}·${fmt(iv.intensity, 2)}`).join(", ") || "—"}</span>,
            s.horizon_months,
            fmtDate(s.updated_at),
            <span key="a" className="flex justify-end gap-0.5">
              <Button size="icon" variant="ghost" title={t("scenarios.openLab")} aria-label={t("scenarios.openLab")} onClick={() => { setActive(s.id); router.push("/lab"); }}><FlaskConical size={13} /></Button>
              <Button size="icon" variant="ghost" title={t("common.duplicate")} aria-label={`${t("common.duplicate")} ${s.name}`} data-testid={`dup-${s.id}`}
                onClick={() => act(() => api.post(`/scenarios/${s.id}/duplicate`, { name: `${scenarioName(s, lang)} (${t("common.copy")})` }), t("common.saved"))}><Copy size={13} /></Button>
              <Button size="icon" variant="ghost" title={t("common.rename")} aria-label={t("common.rename")} onClick={() => { setRenaming(s); setNewName(scenarioName(s, lang)); }}><Pencil size={13} /></Button>
              {!s.is_baseline && <Button size="icon" variant="ghost" title={t("scenarios.setBaseline")} aria-label={t("scenarios.setBaseline")}
                onClick={() => act(() => api.put(`/scenarios/${s.id}`, { ...s, is_baseline: true }), t("common.saved"))}><Star size={13} /></Button>}
              <Button size="icon" variant="ghost" title={t("scenarios.exportJson")} aria-label={t("scenarios.exportJson")} onClick={() => saveJson(s, `scenario_${s.id}.json`)}><FileJson size={13} /></Button>
              {!s.is_baseline && <Button size="icon" variant="ghost" title={t("common.delete")} aria-label={`${t("common.delete")} ${s.name}`} onClick={() => setDeleting(s)}><Trash2 size={13} /></Button>}
            </span>,
          ])}
        />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Panel title={t("scenarios.runs")} bodyClassName="p-0">
          <Table
            head={[t("scenarios.kind"), t("common.name"), t("common.created"), ""]}
            rows={runs.map((r) => [
              <Badge key="k" tone="outline">{r.kind}</Badge>,
              <span key="n" className="text-ink">{r.name}</span>,
              fmtDate(r.created_at),
              <span key="a" className="flex justify-end gap-0.5">
                {r.kind === "simulation" && <Button size="icon" variant="ghost" aria-label="CSV" title="CSV" onClick={() => download(`/runs/${r.id}/export.csv`, `${r.id}.csv`)}><Download size={13} /></Button>}
                <Button size="icon" variant="ghost" aria-label="JSON" title="JSON" onClick={async () => saveJson(await api.get(`/runs/${r.id}`), `${r.id}.json`)}><FileJson size={13} /></Button>
                <Button size="icon" variant="ghost" aria-label={t("common.delete")} onClick={async () => { await api.del(`/runs/${r.id}`); void loadRuns(); }}><Trash2 size={13} /></Button>
              </span>,
            ])}
          />
          {runs.length === 0 && <p className="p-3 text-xs text-muted">{t("overview.noRuns")}</p>}
        </Panel>
        <Panel title={t("scenarios.exportProject")}>
          <div className="space-y-2">
            <Button className="w-full" onClick={async () => saveJson(await api.get("/export/project"), "ssrdt_project.json")} data-testid="export-project"><Download size={14} />{t("scenarios.exportProject")}</Button>
            <Button className="w-full" onClick={() => projRef.current?.click()}><Upload size={14} />{t("scenarios.importProject")}</Button>
            <input ref={projRef} type="file" accept=".json" hidden onChange={async (e) => {
              const f = e.target.files?.[0]; e.target.value = "";
              if (f) { try { setProjectFile(JSON.parse(await f.text())); } catch (er) { setErr(String(er)); } }
            }} />
          </div>
        </Panel>
      </div>

      <Dialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)} title={t("common.rename")}
        footer={<><Button onClick={() => setRenaming(null)}>{t("common.cancel")}</Button>
          <Button variant="primary" data-testid="confirm-rename" onClick={() => act(async () => { await api.put(`/scenarios/${renaming!.id}`, { ...renaming!, name: newName, labels: null }); setRenaming(null); }, t("common.saved"))}>{t("common.save")}</Button></>}>
        <Field label={t("scenarios.newName")}><Input value={newName} onChange={(e) => setNewName(e.target.value)} data-testid="rename-input" /></Field>
      </Dialog>
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} title={t("common.delete")}
        footer={<><Button onClick={() => setDeleting(null)}>{t("common.cancel")}</Button>
          <Button variant="danger" data-testid="confirm-delete" onClick={() => act(async () => { await api.del(`/scenarios/${deleting!.id}`); setDeleting(null); })}>{t("common.delete")}</Button></>}>
        <p className="text-sm text-ink-2">{t("scenarios.confirmDelete")} <span className="text-ink">{scenarioName(deleting, lang)}</span></p>
      </Dialog>
      <Dialog open={!!projectFile} onOpenChange={(o) => !o && setProjectFile(null)} title={t("scenarios.importProject")}
        footer={<><Button onClick={() => setProjectFile(null)}>{t("common.cancel")}</Button>
          <Button variant="danger" onClick={async () => {
            try { await api.post("/import/project", projectFile); setProjectFile(null); await Promise.all([refreshScenarios(), refreshConfig(), refreshDatasets()]); setToast(t("common.saved")); }
            catch (e) { setErr(e instanceof Error ? e.message : String(e)); setProjectFile(null); }
          }}>{t("common.import")}</Button></>}>
        <p className="text-sm text-ink-2">{t("scenarios.importProjectConfirm")}</p>
      </Dialog>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
