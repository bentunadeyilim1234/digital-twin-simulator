// Fictional school maquette: zones, geometry and the school-level indicators linked to each
// function. Pure module (no React/three) so selection and tint logic can be unit-tested.
//
// IMPORTANT: the model is institution-level. A zone does NOT have its own simulated value;
// it displays the school-level aggregate indicators that relate to that function. The tint
// is the plain mean of those engine outputs (a display aggregation, documented in the UI).
// No security features, access points, cameras, locks or movement paths are modelled.

import type { CompareResult, SimResult } from "./types";

export type ZoneId = "classrooms" | "library" | "cafeteria" | "gym" | "admin" | "support" | "commons" | "courtyard" | "green";
export type FloorId = 0 | 1 | 2 | "outdoor";

export interface Block { pos: [number, number, number]; size: [number, number, number]; floor: FloorId }

export interface Zone {
  id: ZoneId;
  indicators: string[]; // variable symbols or index keys produced by the engine
  blocks: Block[];
  floors: FloorId[];
}

const FH = 1; // floor height (model units)
const fy = (floor: number, h = FH * 0.92) => floor * FH + h / 2;

function box(x0: number, x1: number, z0: number, z1: number, floor: number, h = FH * 0.92): Block {
  return { pos: [(x0 + x1) / 2, fy(floor, h), (z0 + z1) / 2], size: [x1 - x0 - 0.06, h, z1 - z0 - 0.06], floor: floor as FloorId };
}

export const ZONES: Zone[] = [
  {
    id: "admin", indicators: ["K", "R", "IF", "M"], floors: [0],
    blocks: [box(-6, -2, -4, -2, 0)],
  },
  {
    id: "commons", indicators: ["C", "T", "J", "M"], floors: [0],
    blocks: [box(-2, 2, -4, -2, 0)],
  },
  {
    id: "support", indicators: ["A", "S", "L", "R"], floors: [0],
    blocks: [box(2, 6, -4, -2, 0)],
  },
  {
    id: "cafeteria", indicators: ["E", "F", "C"], floors: [0],
    blocks: [box(-6, -4, -2, 3, 0)],
  },
  {
    id: "library", indicators: ["E", "O", "M"], floors: [1],
    blocks: [box(-2, 2, -4, -2, 1)],
  },
  {
    id: "classrooms", indicators: ["E", "O", "C"], floors: [0, 1, 2],
    blocks: [
      box(4, 6, -2, 3, 0),
      box(-6, -2, -4, -2, 1), box(2, 6, -4, -2, 1), box(-6, -4, -2, 3, 1), box(4, 6, -2, 3, 1),
      box(-6, -2, -4, -2, 2), box(-2, 2, -4, -2, 2), box(2, 6, -4, -2, 2), box(-6, -4, -2, 3, 2), box(4, 6, -2, 3, 2),
    ],
  },
  {
    id: "gym", indicators: ["F", "O", "E"], floors: [0],
    blocks: [{ pos: [9.5, 0.8, -2], size: [3.9, 1.6, 3.9], floor: 0 }],
  },
  {
    id: "courtyard", indicators: ["E", "F", "C"], floors: ["outdoor"],
    blocks: [{ pos: [0, 0.03, 0.5], size: [7.9, 0.06, 4.9], floor: "outdoor" }],
  },
  {
    id: "green", indicators: ["F", "E"], floors: ["outdoor"],
    blocks: [{ pos: [2, 0.02, 5.4], size: [19, 0.04, 3.6], floor: "outdoor" }],
  },
];

export const ZONE_IDS = ZONES.map((z) => z.id);

export function zoneById(id: ZoneId): Zone {
  const z = ZONES.find((x) => x.id === id);
  if (!z) throw new Error(`unknown zone ${id}`);
  return z;
}

export function indicatorSeries(r: SimResult, key: string): (number | null)[] {
  return r.variables[key] ?? r.indices[key] ?? r.flows[key] ?? [];
}

/** Value of each linked indicator at a month, straight from the engine output. */
export function zoneIndicators(r: SimResult, zone: Zone, month: number): { key: string; value: number | null }[] {
  const m = Math.max(0, Math.min(month, r.horizon));
  return zone.indicators.map((k) => ({ key: k, value: indicatorSeries(r, k)[m] ?? null }));
}

/** Display aggregation: plain mean of the zone's linked indicators (missing values excluded). */
export function zoneLevel(r: SimResult, zone: Zone, month: number): number | null {
  const vals = zoneIndicators(r, zone, month).map((x) => x.value).filter((v): v is number => v !== null && Number.isFinite(v));
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

export type TintMode = "level" | "vsBaseline" | "vsStart";

/** Display range of the sequential level ramp (labelled in the legend). */
export const LEVEL_RANGE: [number, number] = [0.4, 0.9];

export function levelToRamp(v: number | null): number | null {
  if (v === null) return null;
  return Math.max(0, Math.min(1, (v - LEVEL_RANGE[0]) / (LEVEL_RANGE[1] - LEVEL_RANGE[0])));
}

/** Tint input for a zone: level in [0,1] or a signed change (scaled to [-1,1] by `changeScale`). */
export function zoneTint(cmp: CompareResult, scenarioId: string, zone: Zone, month: number, mode: TintMode, changeScale = 0.1): number | null {
  const r = cmp.results[scenarioId];
  if (!r) return null;
  const level = zoneLevel(r, zone, month);
  if (mode === "level") return level;
  const ref = mode === "vsStart" ? zoneLevel(r, zone, 0) : (cmp.results[cmp.baseline_id] ? zoneLevel(cmp.results[cmp.baseline_id], zone, month) : null);
  if (level === null || ref === null) return null;
  return Math.max(-1, Math.min(1, (level - ref) / changeScale));
}

export function visibleOnFloor(block: Block, selected: FloorId | "all"): "full" | "dim" | "hidden" {
  if (selected === "all") return "full";
  if (block.floor === "outdoor") return selected === 0 ? "full" : "dim";
  if (selected === "outdoor") return "dim";
  if (block.floor === selected) return "full";
  return (block.floor as number) < (selected as number) ? "dim" : "hidden";
}
