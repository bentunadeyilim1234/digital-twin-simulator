"use client";

import { create } from "zustand";
import { api } from "./api";
import type { CompareResult, DatasetSummary, Meta, ModelConfig, Scenario } from "./types";

export const MAX_COMPARE = 8;

interface AppState {
  meta: Meta | null;
  config: ModelConfig | null;
  configHash: string;
  scenarios: Scenario[];
  datasets: DatasetSummary[];
  loading: boolean;
  error: string | null;
  activeScenarioId: string | null;
  compareIds: string[];
  lastCompare: CompareResult | null;
  init: () => Promise<void>;
  refreshConfig: () => Promise<void>;
  refreshScenarios: () => Promise<void>;
  refreshDatasets: () => Promise<void>;
  setActive: (id: string | null) => void;
  setCompareIds: (ids: string[]) => void;
  setLastCompare: (c: CompareResult | null) => void;
  upsertLocal: (s: Scenario) => void;
}

export const useApp = create<AppState>((set, get) => ({
  meta: null,
  config: null,
  configHash: "",
  scenarios: [],
  datasets: [],
  loading: false,
  error: null,
  activeScenarioId: null,
  compareIds: [],
  lastCompare: null,
  init: async () => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const [meta, model, scenarios, datasets] = await Promise.all([
        api.get<Meta>("/meta"),
        api.get<{ config: ModelConfig; hash: string }>("/model"),
        api.get<Scenario[]>("/scenarios"),
        api.get<DatasetSummary[]>("/datasets"),
      ]);
      const base = scenarios.find((s) => s.is_baseline);
      set({
        meta, config: model.config, configHash: model.hash, scenarios, datasets, loading: false,
        activeScenarioId: get().activeScenarioId ?? base?.id ?? scenarios[0]?.id ?? null,
        compareIds: get().compareIds.length ? get().compareIds : scenarios.slice(0, MAX_COMPARE).map((s) => s.id),
      });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : String(e) });
    }
  },
  refreshConfig: async () => {
    const model = await api.get<{ config: ModelConfig; hash: string }>("/model");
    set({ config: model.config, configHash: model.hash });
  },
  refreshScenarios: async () => {
    const scenarios = await api.get<Scenario[]>("/scenarios");
    const ids = new Set(scenarios.map((s) => s.id));
    set({
      scenarios,
      compareIds: get().compareIds.filter((i) => ids.has(i)),
      activeScenarioId: get().activeScenarioId && ids.has(get().activeScenarioId!) ? get().activeScenarioId : scenarios.find((s) => s.is_baseline)?.id ?? null,
    });
  },
  refreshDatasets: async () => {
    set({ datasets: await api.get<DatasetSummary[]>("/datasets") });
  },
  setActive: (id) => set({ activeScenarioId: id }),
  setCompareIds: (ids) => set({ compareIds: ids }),
  setLastCompare: (c) => set({ lastCompare: c }),
  upsertLocal: (s) => set({ scenarios: get().scenarios.some((x) => x.id === s.id) ? get().scenarios.map((x) => (x.id === s.id ? s : x)) : [...get().scenarios, s] }),
}));

/** Display name: localised template label while the user has not renamed the scenario. */
export function scenarioName(s: Scenario | undefined | null, lang: "tr" | "en"): string {
  if (!s) return "—";
  if (s.labels && s.name === s.labels.en) return s.labels[lang] || s.name;
  return s.name;
}
