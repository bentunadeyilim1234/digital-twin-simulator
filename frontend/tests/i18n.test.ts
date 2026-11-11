import { describe, expect, it } from "vitest";
import en from "@/lib/i18n/en";
import tr from "@/lib/i18n/tr";
import { translate, translateList } from "@/lib/i18n";

function keys(o: unknown, prefix = ""): string[] {
  if (typeof o !== "object" || o === null || Array.isArray(o)) return [prefix];
  return Object.entries(o).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe("localisation", () => {
  it("Turkish and English dictionaries have identical key sets", () => {
    expect(keys(tr).sort()).toEqual(keys(en).sort());
  });
  it("no empty strings in either language", () => {
    for (const d of [en, tr]) for (const k of keys(d)) {
      const v = k.split(".").reduce<unknown>((o, p) => (o as Record<string, unknown>)[p], d);
      if (typeof v === "string") expect(v.length, k).toBeGreaterThan(0);
    }
  });
  it("translates with interpolation and falls back to the key", () => {
    expect(translate("tr", "nav.lab")).toBe("Simülasyon Laboratuvarı");
    expect(translate("en", "nav.lab")).toBe("Simulation Lab");
    expect(translate("en", "overview.checksPassed", { p: 3, t: 4 })).toBe("3 / 4 checks passed");
    expect(translate("tr", "does.not.exist")).toBe("does.not.exist");
    expect(translateList("tr", "docs.cannotList").length).toBe(4);
  });
  it("the synthetic-data disclaimer exists in both languages", () => {
    expect(en.app.synthetic).toContain("SYNTHETIC DEMONSTRATION DATA");
    expect(tr.app.synthetic).toContain("SENTETİK");
  });
});
