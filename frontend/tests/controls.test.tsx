import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(() => cleanup());
import { NumberField } from "@/components/ui";
import { VariableControl } from "@/components/VariableControl";
import { I18nProvider } from "@/lib/i18n";
import { scenarioName } from "@/lib/store";
import type { Scenario, Variable } from "@/lib/types";

// Recharts' ResponsiveContainer needs ResizeObserver in jsdom
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;

const variable: Variable = {
  id: "SOC-02", symbol: "T", key: "institutional_trust", domain: "SOC", role: "state", initial: 0.5,
  labels: { en: "Institutional trust", tr: "Kurumsal güven" }, definition: { en: "def", tr: "tanım" },
  measurement: { unit: "scale mean (1-5 Likert)", lower: 1, upper: 5, direction: "positive", sources: ["survey"] },
  measurement_evidence: "E2", references: [], notes: "",
};

function scenario(): Scenario {
  return {
    id: "s", name: "S", description: "", notes: "", template_id: null, is_baseline: false, horizon_months: 12,
    initial_state: { T: 0.5 }, initial_stock: {}, variable_modes: {}, overrides: {}, context_schedule: {}, interventions: [],
    external: {}, parameter_overrides: {}, dataset_id: null, dataset_anchor: "latest",
  };
}

describe("NumberField", () => {
  it("commits on Enter and clamps to range", () => {
    const onChange = vi.fn();
    render(<NumberField value={0.5} onChange={onChange} label="num" />);
    const input = screen.getByLabelText("num");
    fireEvent.change(input, { target: { value: "1.7" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(1);
    fireEvent.change(input, { target: { value: "0,25" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith(0.25);
  });
});

describe("VariableControl", () => {
  it("numeric input updates the scenario's initial state", () => {
    let draft = scenario();
    const update = (fn: (d: Scenario) => void) => { const c = structuredClone(draft); fn(c); draft = c; };
    render(<I18nProvider><VariableControl v={variable} draft={draft} onChange={update} templateValue={0.5} /></I18nProvider>);
    const input = screen.getByLabelText("T value");
    fireEvent.change(input, { target: { value: "0.72" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(draft.initial_state.T).toBeCloseTo(0.72);
  });

  it("manual override switch sets mode and override value, and is visibly flagged", () => {
    let draft = scenario();
    const update = (fn: (d: Scenario) => void) => { const c = structuredClone(draft); fn(c); draft = c; };
    const { rerender } = render(<I18nProvider><VariableControl v={variable} draft={draft} onChange={update} templateValue={0.5} /></I18nProvider>);
    act(() => { fireEvent.click(screen.getByLabelText("T manual override")); });
    expect(draft.variable_modes.T).toBe("manual");
    expect(draft.overrides.T).toEqual({ value: 0.5 });
    rerender(<I18nProvider><VariableControl v={variable} draft={draft} onChange={update} templateValue={0.5} /></I18nProvider>);
    expect(screen.getByText("ELLE GEÇERSİZ KILMA")).toBeTruthy(); // Turkish is the default language
  });
});

describe("scenarioName", () => {
  it("localises unrenamed template scenarios", () => {
    const s = { ...scenario(), name: "S1 — Accessibility Improvement", labels: { en: "S1 — Accessibility Improvement", tr: "S1 — Erişilebilirlik İyileştirmesi" } };
    expect(scenarioName(s, "tr")).toBe("S1 — Erişilebilirlik İyileştirmesi");
    expect(scenarioName({ ...s, name: "Custom" }, "tr")).toBe("Custom");
  });
});
