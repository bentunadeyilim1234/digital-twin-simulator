import { describe, expect, it } from "vitest";
import { LEVEL_RANGE, ZONES, levelToRamp, visibleOnFloor, zoneById, zoneIndicators, zoneLevel, zoneTint } from "@/lib/zones";
import type { CompareResult, SimResult } from "@/lib/types";

function fakeResult(id: string, scale: number): SimResult {
  const vars = ["E", "F", "O", "M", "C", "T", "J", "H", "A", "R", "L", "K", "S", "TR", "P", "IF"];
  const series = (base: number) => [base, base * scale, base * scale];
  return {
    scenario_id: id, scenario_name: id, horizon: 2, months: [0, 1, 2],
    variables: Object.fromEntries(vars.map((v, i) => [v, series(0.4 + i * 0.02)])),
    targets: {}, indices: { TOTAL: series(0.6) }, flows: { Q: [10, 11, 12] }, interventions: {}, external: {},
    resources: { program_hours_total: 0, program_hours_by_intervention: {}, program_hours_monthly: [], support_hours_total: 0, unit: "" },
    modes: {}, diagnostics: { warnings: [], mass_balance_max_error: 0, clipped_targets: 0 },
    provenance: { data_class: "SYNTHETIC", engine_version: "1", config_hash: "x", scenario_hash: "y", parameter_status: "ILLUSTRATIVE" },
  };
}

const base = fakeResult("b", 1);
const scen = fakeResult("s", 1.1);
const cmp: CompareResult = { baseline_id: "b", order: ["b", "s"], results: { b: base, s: scen }, deltas: {}, comparability: {}, same_horizon: true, resources: {} };

describe("zones", () => {
  it("every zone links only to engine outputs and has geometry", () => {
    for (const z of ZONES) {
      expect(z.blocks.length).toBeGreaterThan(0);
      for (const k of z.indicators) expect(base.variables[k] ?? base.indices[k]).toBeDefined();
    }
  });

  it("zone indicators are read straight from the result", () => {
    const z = zoneById("support");
    const ind = zoneIndicators(scen, z, 2);
    expect(ind.map((x) => x.key)).toEqual(["A", "S", "L", "R"]);
    expect(ind[0].value).toBeCloseTo(scen.variables.A[2] as number);
  });

  it("level is the mean of linked indicators", () => {
    const z = zoneById("gym");
    const expected = (["F", "O", "E"].map((k) => base.variables[k][0] as number).reduce((a, b) => a + b)) / 3;
    expect(zoneLevel(base, z, 0)).toBeCloseTo(expected);
  });

  it("tint modes: level, change vs baseline, change vs start", () => {
    const z = zoneById("classrooms");
    expect(zoneTint(cmp, "s", z, 2, "level")).toBeCloseTo(zoneLevel(scen, z, 2) as number);
    expect(zoneTint(cmp, "b", z, 2, "vsBaseline")).toBeCloseTo(0);
    expect(zoneTint(cmp, "s", z, 2, "vsBaseline")!).toBeGreaterThan(0);
    expect(zoneTint(cmp, "s", z, 0, "vsStart")).toBeCloseTo(0);
  });

  it("missing values are excluded, not treated as zero", () => {
    const r = fakeResult("m", 1);
    r.variables.E = [null, null, null];
    const z = zoneById("gym");
    expect(zoneLevel(r, z, 0)).toBeCloseTo(((r.variables.F[0] as number) + (r.variables.O[0] as number)) / 2);
  });

  it("floor visibility isolates floors", () => {
    const classrooms = zoneById("classrooms");
    const f2 = classrooms.blocks.find((b) => b.floor === 2)!;
    const f0 = classrooms.blocks.find((b) => b.floor === 0)!;
    expect(visibleOnFloor(f2, 1)).toBe("hidden");
    expect(visibleOnFloor(f0, 1)).toBe("dim");
    expect(visibleOnFloor(f2, "all")).toBe("full");
  });

  it("level ramp is clamped to the labelled display range", () => {
    expect(levelToRamp(LEVEL_RANGE[0])).toBe(0);
    expect(levelToRamp(LEVEL_RANGE[1])).toBe(1);
    expect(levelToRamp(0.05)).toBe(0);
    expect(levelToRamp(null)).toBeNull();
  });
});
