"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useApp } from "./store";
import type { Scenario } from "./types";

/** Local editable copy of a stored scenario with dirty tracking and save. */
export function useScenarioDraft(id: string | null) {
  const scenarios = useApp((s) => s.scenarios);
  const upsertLocal = useApp((s) => s.upsertLocal);
  const stored = useMemo(() => scenarios.find((s) => s.id === id) ?? null, [scenarios, id]);
  const [draft, setDraft] = useState<Scenario | null>(stored ? structuredClone(stored) : null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(stored ? structuredClone(stored) : null);
    setError(null);
  }, [stored]);

  const dirty = useMemo(() => {
    if (!draft || !stored) return false;
    const strip = (s: Scenario) => JSON.stringify({ ...s, created_at: undefined, updated_at: undefined });
    return strip(draft) !== strip(stored);
  }, [draft, stored]);

  const update = useCallback((fn: (d: Scenario) => void) => {
    setDraft((d) => {
      if (!d) return d;
      const c = structuredClone(d);
      fn(c);
      return c;
    });
  }, []);

  const save = useCallback(async (): Promise<Scenario | null> => {
    if (!draft) return null;
    setSaving(true);
    setError(null);
    try {
      const saved = await api.put<Scenario>(`/scenarios/${draft.id}`, draft);
      upsertLocal(saved);
      return saved;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setSaving(false);
    }
  }, [draft, upsertLocal]);

  const revert = useCallback(() => setDraft(stored ? structuredClone(stored) : null), [stored]);

  return { draft, stored, dirty, update, save, revert, saving, error, setDraft };
}
