"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Anchor, Plus, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { DOMAIN_BANDS, edgePath, GRAPH_H, GRAPH_W, NODE_POS } from "@/lib/graphLayout";
import { DOMAIN_COLOR, fmt, NEG, POS } from "@/lib/format";
import type { Edge, Evidence } from "@/lib/types";
import { Badge, Button, Dialog, ErrorBox, EvidenceBadge, Field, Input, NumberField, PageHeader, Panel, Select, Slider, Switch, Textarea, Toast, cn } from "@/components/ui";

interface GraphNode { id: string; kind: string; role: string; domain: string | null; label: string; evidence?: string }
interface Loop { id: string; polarity: string; edges: string[]; labels: { en: string; tr: string }; description: { en: string; tr: string }; computed_polarity: string; closed: boolean; active: boolean }
interface Graph { nodes: GraphNode[]; edges: Edge[]; loops: Loop[]; detected_loops: { edges: string[]; polarity: string; declared_as: string | null; nodes: string[] }[] }

export default function CausalPage() {
  const { t, lang, pick } = useI18n();
  const refreshConfig = useApp((s) => s.refreshConfig);
  const [g, setG] = useState<Graph | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<{ type: "node" | "edge"; id: string } | null>(null);
  const [hoverLoop, setHoverLoop] = useState<string | null>(null);
  const [show, setShow] = useState({ U: false, D: false, flow: true, structural: true });
  const [toast, setToast] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setG(await api.get<Graph>(`/model/graph?lang=${lang}`));
      setErr(null);
    } catch (e) { setErr(String((e as Error).message)); }
  }, [lang]);
  useEffect(() => { void load(); }, [load]);

  const visibleNode = useCallback((n: GraphNode) => (n.kind === "intervention" ? show.U : n.kind === "external" ? show.D : n.kind === "flow" ? show.flow : true), [show]);
  const nodeById = useMemo(() => Object.fromEntries((g?.nodes ?? []).map((n) => [n.id, n])), [g]);
  const loopEdges = useMemo(() => new Set(hoverLoop ? g?.loops.find((l) => l.id === hoverLoop)?.edges ?? [] : []), [hoverLoop, g]);

  if (err) return <ErrorBox error={err} onRetry={load} />;
  if (!g) return null;

  const edges = g.edges.filter((e) => nodeById[e.source] && nodeById[e.target] && visibleNode(nodeById[e.source]) && visibleNode(nodeById[e.target]) && (show.structural || e.kind !== "structural"));
  const selEdge = sel?.type === "edge" ? g.edges.find((e) => e.id === sel.id) : undefined;
  const selNode = sel?.type === "node" ? nodeById[sel.id] : undefined;

  const patch = async (id: string, body: Partial<Edge>) => {
    try {
      await api.patch(`/model/edges/${id}`, body);
      await Promise.all([load(), refreshConfig()]);
    } catch (e) { setErr(String((e as Error).message)); }
  };

  return (
    <div className="space-y-4">
      <PageHeader title={t("causal.title")} subtitle={t("causal.subtitle")}
        actions={<>
          <Button onClick={() => setAddOpen(true)} data-testid="add-edge"><Plus size={14} />{t("causal.addEdge")}</Button>
          <Button variant="outline" title={t("causal.reanchorHelp")} onClick={async () => {
            await api.post("/model/anchor", { apply: true }); await refreshConfig(); setToast(t("common.saved"));
          }}><Anchor size={14} />{t("causal.reanchor")}</Button>
          <Button variant="danger" onClick={() => setResetOpen(true)}><RotateCcw size={14} />{t("causal.resetAll")}</Button>
        </>}
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-panel px-3 py-2 text-xs">
            {([["U", "showInterventions"], ["D", "showExternal"], ["flow", "showFlows"], ["structural", "showStructural"]] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-ink-2">
                <Switch checked={show[k]} onChange={(v) => setShow((s) => ({ ...s, [k]: v }))} label={t(`causal.${label}`)} />{t(`causal.${label}`)}
              </label>
            ))}
            <span className="ml-auto flex flex-wrap items-center gap-3 text-muted">
              <span className="flex items-center gap-1"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke={POS} strokeWidth="2" /></svg>{t("causal.positive")}</span>
              <span className="flex items-center gap-1"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke={NEG} strokeWidth="2" /></svg>{t("causal.negative")}</span>
              <span className="flex items-center gap-1"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="#b4bcc7" strokeWidth="2" strokeDasharray="4 3" /></svg>{t("causal.hypothesis")}</span>
              <span>{t("causal.disabledEdge")}</span>
            </span>
          </div>
          <div className="overflow-x-auto rounded-lg border border-line bg-panel">
            <svg viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`} className="min-w-[760px]" role="img" aria-label={t("causal.title")} data-testid="causal-graph">
              <defs>
                {[["pos", POS], ["neg", NEG], ["off", "#3a414b"], ["st", "#6b7480"]].map(([id, c]) => (
                  <marker key={id} id={`ah-${id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill={c} />
                  </marker>
                ))}
              </defs>
              {DOMAIN_BANDS.map((b) => (
                <g key={b.id}>
                  <rect x={b.x} y={110} width={b.w} height={330} rx={8} fill="#151a21" stroke="#222831" />
                  <text x={b.x + 10} y={128} fill={DOMAIN_COLOR[b.id]} fontSize="12" fontWeight="600">{b.id} · {t(`domains.${b.id}`)}</text>
                </g>
              ))}
              {show.flow && <><rect x={200} y={505} width={860} height={205} rx={8} fill="#13171d" stroke="#222831" strokeDasharray="4 4" />
                <text x={210} y={523} fill="#828c99" fontSize="12">{t("lab.stockflow")}</text></>}
              {edges.map((e) => {
                const [sx, sy] = NODE_POS[e.source] ?? [0, 0];
                const [tx, ty] = NODE_POS[e.target] ?? [0, 0];
                const structural = e.kind === "structural";
                const color = !e.enabled ? "#3a414b" : structural ? "#6b7480" : e.sign > 0 ? POS : NEG;
                const marker = !e.enabled ? "off" : structural ? "st" : e.sign > 0 ? "pos" : "neg";
                const w = structural ? 1.2 : Math.max(1.2, Math.min(4.5, 1 + e.coefficient * 5));
                const isSel = sel?.type === "edge" && sel.id === e.id;
                const inLoop = loopEdges.has(e.id);
                const d = edgePath(sx, sy, tx, ty);
                return (
                  <g key={e.id} className="cursor-pointer" onClick={() => setSel({ type: "edge", id: e.id })} data-testid={`edge-${e.id}`}>
                    <path d={d} stroke="transparent" strokeWidth={12} fill="none" />
                    {(isSel || inLoop) && <path d={d} stroke={inLoop ? "#e0a040" : "#e8ebef"} strokeWidth={w + 4} opacity={0.35} fill="none" />}
                    <path d={d} fill="none" stroke={color} strokeWidth={w} strokeDasharray={e.evidence === "H" && !structural ? "6 4" : undefined}
                      opacity={e.enabled ? (hoverLoop && !inLoop ? 0.25 : 0.9) : 0.5} markerEnd={`url(#ah-${marker})`}>
                      <title>{`${e.id}: ${e.source} → ${e.target} (${e.sign > 0 ? "+" : "−"}${fmt(e.coefficient, 2)}, ${e.evidence})`}</title>
                    </path>
                  </g>
                );
              })}
              {g.nodes.filter(visibleNode).map((n) => {
                const [x, y] = NODE_POS[n.id] ?? [0, 0];
                const isSel = sel?.type === "node" && sel.id === n.id;
                const fill = n.kind === "variable" ? "#181d24" : n.kind === "flow" ? "#14202e" : n.kind === "intervention" ? "#1d1a2e" : "#22201a";
                const stroke = n.kind === "variable" ? DOMAIN_COLOR[n.domain ?? "ENV"] : n.kind === "flow" ? "#5598e7" : n.kind === "intervention" ? "#9085e9" : "#c98500";
                return (
                  <g key={n.id} transform={`translate(${x},${y})`} className="cursor-pointer" onClick={() => setSel({ type: "node", id: n.id })} data-testid={`node-${n.id}`}>
                    {n.kind === "flow" && n.role === "stock" ? (
                      <rect x={-26} y={-18} width={52} height={36} rx={4} fill={fill} stroke={stroke} strokeWidth={isSel ? 3 : 1.5} />
                    ) : (
                      <circle r={n.kind === "variable" ? 22 : 18} fill={fill} stroke={stroke} strokeWidth={isSel ? 3 : 1.5} strokeDasharray={n.role === "context" ? "4 3" : n.role === "derived" ? "1.5 2.5" : undefined} />
                    )}
                    <text textAnchor="middle" dy="4" fill="#e8ebef" fontSize={n.id.length > 3 ? 10 : 13} fontWeight="600">{n.kind === "variable" || n.kind === "flow" ? n.id.replace("C_flow", "C_f") : n.id.replace(/^U_/, "U·").slice(0, 9)}</text>
                    <text textAnchor="middle" y={n.kind === "variable" ? 36 : 32} fill="#828c99" fontSize="10">{n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label}</text>
                  </g>
                );
              })}
            </svg>
          </div>
          <Panel title={t("causal.loops")} subtitle={t("causal.detected", { n: g.detected_loops.length })}>
            <ul className="grid gap-2 md:grid-cols-2">
              {g.loops.map((l) => (
                <li key={l.id} onMouseEnter={() => setHoverLoop(l.id)} onMouseLeave={() => setHoverLoop(null)} onFocus={() => setHoverLoop(l.id)} tabIndex={0}
                  className="rounded-md border border-line bg-panel-2 p-2 text-xs outline-none hover:border-[#7a5a1e]" data-testid={`loop-${l.id}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold">{l.id}</span>
                    <span className="text-ink">{pick(l.labels)}</span>
                    <Badge tone={l.computed_polarity === "reinforcing" ? "accent" : "warm"}>{t(`causal.${l.computed_polarity}`)}</Badge>
                    {!l.active && <Badge tone="bad">{t("common.disabled")}</Badge>}
                  </div>
                  <p className="mt-1 text-ink-2">{pick(l.description)}</p>
                  <p className="mt-1 font-mono text-[11px] text-muted">{l.edges.join(" → ")}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel title={t("causal.inspector")} className="h-fit xl:sticky xl:top-24">
          {!sel && <p className="text-xs text-muted">{t("causal.selectHint")}</p>}
          {selNode && <NodeInspector node={selNode} edges={g.edges} onSelectEdge={(id) => setSel({ type: "edge", id })} />}
          {selEdge && <EdgeEditor key={selEdge.id + selEdge.coefficient + selEdge.enabled + selEdge.sign} edge={selEdge} onPatch={(b) => patch(selEdge.id, b)}
            onRestore={async () => { await api.post(`/model/edges/${selEdge.id}/restore`); await Promise.all([load(), refreshConfig()]); }}
            onDelete={async () => { await api.del(`/model/edges/${selEdge.id}`); setSel(null); await Promise.all([load(), refreshConfig()]); }} />}
        </Panel>
      </div>
      <AddEdgeDialog open={addOpen} onOpenChange={setAddOpen} nodes={g.nodes} onAdded={async () => { await Promise.all([load(), refreshConfig()]); setToast(t("common.saved")); }} />
      <Dialog open={resetOpen} onOpenChange={setResetOpen} title={t("causal.resetAll")}
        footer={<><Button onClick={() => setResetOpen(false)}>{t("common.cancel")}</Button>
          <Button variant="danger" data-testid="confirm-reset" onClick={async () => { await api.post("/model/reset"); await Promise.all([load(), refreshConfig()]); setResetOpen(false); setSel(null); }}>{t("common.reset")}</Button></>}>
        <p className="text-sm text-ink-2">{t("causal.resetConfirm")}</p>
      </Dialog>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}

function NodeInspector({ node, edges, onSelectEdge }: { node: GraphNode; edges: Edge[]; onSelectEdge: (id: string) => void }) {
  const { t, pick } = useI18n();
  const config = useApp((s) => s.config);
  const v = config?.variables.find((x) => x.symbol === node.id);
  const inc = edges.filter((e) => e.target === node.id);
  const out = edges.filter((e) => e.source === node.id);
  const list = (es: Edge[], key: "source" | "target") => (
    <ul className="space-y-1">
      {es.map((e) => (
        <li key={e.id}>
          <button className="flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left hover:bg-panel-2" onClick={() => onSelectEdge(e.id)}>
            <span className="truncate"><span className="font-mono">{e[key]}</span> <span className="text-muted">({e.id})</span></span>
            <span className="tabular" style={{ color: !e.enabled ? "#5a626d" : e.sign > 0 ? POS : NEG }}>{e.sign > 0 ? "+" : "−"}{fmt(e.coefficient, 2)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="space-y-3 text-xs" data-testid="node-inspector">
      <div>
        <div className="font-mono text-base font-semibold">{node.id}</div>
        <div className="text-sm text-ink">{node.label}</div>
        <div className="mt-1 flex gap-1"><Badge tone="outline">{node.kind}</Badge>{v && <Badge tone="outline">{t(`roles.${v.role}`)}</Badge>}{v && <EvidenceBadge e={v.measurement_evidence} />}</div>
      </div>
      {v && <p className="text-ink-2">{pick(v.definition)}</p>}
      {v && <p className="text-muted">{v.measurement.unit} · [{v.measurement.lower}, {v.measurement.upper}] · {v.id}</p>}
      <div><div className="mb-1 font-medium text-ink-2">{t("causal.incoming")}</div>{inc.length ? list(inc, "source") : <span className="text-muted">—</span>}</div>
      <div><div className="mb-1 font-medium text-ink-2">{t("causal.outgoing")}</div>{out.length ? list(out, "target") : <span className="text-muted">—</span>}</div>
    </div>
  );
}

function EdgeEditor({ edge, onPatch, onRestore, onDelete }: { edge: Edge; onPatch: (b: Partial<Edge>) => Promise<void>; onRestore: () => Promise<void>; onDelete: () => Promise<void> }) {
  const { t, pick } = useI18n();
  const [coef, setCoef] = useState(edge.coefficient);
  const [notes, setNotes] = useState(edge.notes);
  const structural = edge.kind === "structural";
  const max = Math.max(1, (edge.range?.[1] ?? 0) * 2, edge.coefficient * 1.5);
  return (
    <div className="space-y-3 text-xs" data-testid="edge-editor">
      <div>
        <div className="flex items-center gap-2"><span className="font-mono text-base font-semibold">{edge.id}</span>{edge.hypothesis && <Badge tone="accent">{edge.hypothesis}</Badge>}<EvidenceBadge e={edge.evidence} /></div>
        <div className="mt-1 font-mono text-ink-2">{edge.source} → {edge.target} · {edge.symbol}</div>
        <p className="mt-1 text-ink">{pick(edge.description)}</p>
        {edge.modified && <Badge tone="warm" className="mt-1">{t("causal.modified")}</Badge>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
        <dt className="text-muted">{t("causal.kind")}</dt><dd>{edge.kind}</dd>
        <dt className="text-muted">{t("common.confidence")}</dt><dd>{edge.confidence}</dd>
        <dt className="text-muted">{t("common.references")}</dt><dd className="break-words">{edge.references.join(", ") || "—"}</dd>
        {edge.range && <><dt className="text-muted">{t("common.range")}</dt><dd className="tabular">[{fmt(edge.range[0], 2)}, {fmt(edge.range[1], 2)}]</dd></>}
      </dl>
      {structural ? <p className="text-muted">{t("causal.structuralNote")}</p> : (
        <>
          <Field label={t("causal.coefficient")}>
            <div className="flex items-center gap-2">
              <Slider value={coef} max={max} step={0.005} onChange={setCoef} label="coefficient" />
              <NumberField value={coef} max={5} onChange={setCoef} label="coefficient value" />
            </div>
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <Field label={t("causal.sign")}>
              <Select value={edge.sign} onChange={(e) => onPatch({ sign: Number(e.target.value) as 1 | -1 })} className="w-24">
                <option value={1}>+ ({t("common.positive")})</option><option value={-1}>− ({t("common.negative")})</option>
              </Select>
            </Field>
            <Field label={t("common.evidence")}>
              <Select value={edge.evidence} onChange={(e) => onPatch({ evidence: e.target.value as Evidence })} className="w-24">
                {["E1", "E2", "H", "L"].map((x) => <option key={x}>{x}</option>)}
              </Select>
            </Field>
            <label className="flex items-center gap-2 pt-4 text-ink-2"><Switch checked={edge.enabled} onChange={(v) => onPatch({ enabled: v })} label="enabled" />{edge.enabled ? t("common.enabled") : t("common.disabled")}</label>
          </div>
          <Field label={t("common.notes")}><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" data-testid="save-edge" disabled={coef === edge.coefficient && notes === edge.notes} onClick={() => onPatch({ coefficient: coef, notes })}>{t("common.save")}</Button>
            {!edge.custom && <Button variant="outline" onClick={onRestore}><RotateCcw size={13} />{t("common.restore")}</Button>}
            {edge.custom && <Button variant="danger" onClick={onDelete}>{t("common.delete")}</Button>}
          </div>
          {edge.original && <p className="text-[11px] text-muted">original: {edge.original.sign > 0 ? "+" : "−"}{fmt(edge.original.coefficient, 3)} · {edge.original.enabled ? t("common.enabled") : t("common.disabled")}</p>}
        </>
      )}
    </div>
  );
}

function AddEdgeDialog({ open, onOpenChange, nodes, onAdded }: { open: boolean; onOpenChange: (o: boolean) => void; nodes: GraphNode[]; onAdded: () => Promise<void> }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ source: "K", target: "C", kind: "linear", sign: 1, coefficient: 0.1, evidence: "H", description_en: "", description_tr: "", notes: "" });
  const [err, setErr] = useState<string | null>(null);
  const ids = nodes.map((n) => n.id);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("causal.addEdge")}
      footer={<><Button onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
        <Button variant="primary" data-testid="confirm-add-edge" onClick={async () => {
          try { await api.post("/model/edges", form); setErr(null); onOpenChange(false); await onAdded(); } catch (e) { setErr(String((e as Error).message)); }
        }}>{t("common.add")}</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("causal.source")}><Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>{ids.map((i) => <option key={i}>{i}</option>)}</Select></Field>
        <Field label={t("causal.target")}><Select value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}>{ids.map((i) => <option key={i}>{i}</option>)}</Select></Field>
        <Field label={t("causal.kind")} hint="linear: target ∈ {E,C,T,A,K,S,P}; context_response: target ∈ {F,O,M,J,H,TR,IF}; derived: target = L">
          <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{["linear", "context_response", "derived"].map((k) => <option key={k}>{k}</option>)}</Select>
        </Field>
        <Field label={t("causal.sign")}><Select value={form.sign} onChange={(e) => setForm({ ...form, sign: Number(e.target.value) })}><option value={1}>+</option><option value={-1}>−</option></Select></Field>
        <Field label={t("causal.coefficient")}><Input type="number" step="0.01" min="0" max="5" value={form.coefficient} onChange={(e) => setForm({ ...form, coefficient: Number(e.target.value) })} /></Field>
        <Field label={t("common.evidence")}><Select value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })}>{["H", "E2", "E1", "L"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="EN" className="sm:col-span-2"><Input value={form.description_en} onChange={(e) => setForm({ ...form, description_en: e.target.value })} /></Field>
        <Field label="TR" className="sm:col-span-2"><Input value={form.description_tr} onChange={(e) => setForm({ ...form, description_tr: e.target.value })} /></Field>
      </div>
      <div className={cn("mt-3", !err && "hidden")}><ErrorBox error={err} /></div>
    </Dialog>
  );
}
