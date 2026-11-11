"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en from "./en";
import tr from "./tr";
import type { Lang, LangText } from "../types";

const dictionaries = { en, tr } as const;
const LANG_KEY = "ssrdt-lang";

type Vars = Record<string, string | number>;

function lookup(dict: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), dict);
}

export function translate(lang: Lang, key: string, vars?: Vars): string {
  const v = lookup(dictionaries[lang], key) ?? lookup(dictionaries.en, key);
  if (typeof v !== "string") return key;
  return vars ? v.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`)) : v;
}

export function translateList(lang: Lang, key: string): string[] {
  const v = lookup(dictionaries[lang], key);
  return Array.isArray(v) ? (v as string[]) : [];
}

interface I18nCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Vars) => string;
  tl: (key: string) => string[];
  pick: (txt?: LangText | null, fallback?: string) => string;
}

const Ctx = createContext<I18nCtx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("tr"); // Turkish is the default language

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(LANG_KEY);
      if (saved === "en" || saved === "tr") setLangState(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(LANG_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<I18nCtx>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      tl: (key) => translateList(lang, key),
      pick: (txt, fallback = "") => (txt ? txt[lang] || txt.en || fallback : fallback),
    }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18nCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useI18n must be used inside I18nProvider");
  return c;
}
