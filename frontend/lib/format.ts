// Presentation-only helpers (formatting and colour lookup). No model mathematics.

export function fmt(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

export function fmtSigned(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = v.toFixed(digits);
  return v > 0 ? `+${s}` : s.startsWith("-0.000") ? s.replace("-", "") : s;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return Math.round(v).toLocaleString();
}

export function fmtDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

/** Validated dark categorical palette, fixed order (never cycled past 8). */
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const DOMAIN_COLOR: Record<string, string> = { ENV: SERIES[0], SOC: SERIES[1], ORG: SERIES[2], SUP: SERIES[3] };
export const POS = "#3987e5";
export const NEG = "#e66767";
export const NEUTRAL_DARK = "#383835";

/** Colour follows the entity: a scenario keeps its slot from its position in the library. */
export function scenarioColor(id: string, allIds: string[]): string {
  const i = allIds.indexOf(id);
  return i < 0 ? "#828c99" : SERIES[i % SERIES.length];
}

// Sequential blue ramp (dark mode: low values recede toward the surface).
const SEQ = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4"];
export function sequential(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "#2a2f37";
  const i = Math.max(0, Math.min(SEQ.length - 1, Math.round(v * (SEQ.length - 1))));
  return SEQ[i];
}

// Diverging blue <-> red with neutral grey midpoint; d in [-1, 1].
const DIV_NEG = ["#e66767", "#c85a5a", "#a65050", "#7d4646", "#553d3c"];
const DIV_POS = ["#3d4a5c", "#2f5a8f", "#2f6db5", "#3987e5", "#6da7ec"];
export function diverging(d: number | null | undefined): string {
  if (d === null || d === undefined || !Number.isFinite(d)) return "#2a2f37";
  if (Math.abs(d) < 0.02) return NEUTRAL_DARK;
  const k = Math.min(4, Math.floor(Math.min(1, Math.abs(d)) * 5));
  return d > 0 ? DIV_POS[k] : DIV_NEG[4 - k];
}

export const EVIDENCE_STYLE: Record<string, { color: string; dash: string }> = {
  E1: { color: "#e8ebef", dash: "" },
  E2: { color: "#b4bcc7", dash: "" },
  H: { color: "#828c99", dash: "5 4" },
  L: { color: "#199e70", dash: "" },
};
