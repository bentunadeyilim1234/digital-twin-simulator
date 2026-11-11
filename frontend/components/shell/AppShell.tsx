"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  BookOpen, Box, ChartLine, Database, FlaskConical, LayoutDashboard, Library, Network, PanelLeftClose, PanelLeftOpen, SlidersHorizontal, TriangleAlert,
} from "lucide-react";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { useApp } from "@/lib/store";
import { Button, cn, ErrorBox, Spinner } from "@/components/ui";

const NAV = [
  { href: "/", key: "overview", icon: LayoutDashboard },
  { href: "/twin", key: "twin", icon: Box },
  { href: "/variables", key: "variables", icon: SlidersHorizontal },
  { href: "/causal", key: "causal", icon: Network },
  { href: "/lab", key: "lab", icon: FlaskConical },
  { href: "/scenarios", key: "scenarios", icon: Library },
  { href: "/analytics", key: "analytics", icon: ChartLine },
  { href: "/data", key: "data", icon: Database },
  { href: "/docs", key: "docs", icon: BookOpen },
];

function Sidebar({ collapsed, onToggle, mobileOpen, onNavigate }: { collapsed: boolean; onToggle: () => void; mobileOpen: boolean; onNavigate: () => void }) {
  const { t } = useI18n();
  const path = usePathname();
  return (
    <nav
      aria-label="Main"
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex flex-col border-r border-line bg-panel transition-[width,transform] md:sticky md:top-0 md:h-screen md:translate-x-0",
        collapsed ? "md:w-14" : "md:w-56",
        mobileOpen ? "w-60 translate-x-0" : "w-60 -translate-x-full",
      )}
    >
      <div className={cn("flex h-12 items-center gap-2 border-b border-line px-3", collapsed && "md:justify-center md:px-0")}>
        <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-[#13294a] text-[11px] font-bold text-[#9ec5f4]" aria-hidden>DT</div>
        <div className={cn("min-w-0", collapsed && "md:hidden")}>
          <div className="truncate text-[13px] font-semibold leading-tight">{t("app.short")}</div>
          <div className="truncate text-[11px] text-muted">{t("app.tagline")}</div>
        </div>
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {NAV.map(({ href, key, icon: Icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                onClick={onNavigate}
                data-testid={`nav-${key}`}
                title={collapsed ? t(`nav.${key}`) : undefined}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] text-ink-2 hover:bg-panel-2 hover:text-ink",
                  active && "bg-panel-3 text-ink",
                  collapsed && "md:justify-center",
                )}
              >
                <Icon size={16} className={cn("shrink-0", active && "text-accent")} />
                <span className={cn("truncate", collapsed && "md:hidden")}>{t(`nav.${key}`)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="hidden border-t border-line p-2 md:block">
        <Button variant="ghost" size="sm" className="w-full" onClick={onToggle} aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}>
          {collapsed ? <PanelLeftOpen size={15} /> : <><PanelLeftClose size={15} /><span>{t("nav.collapse")}</span></>}
        </Button>
      </div>
    </nav>
  );
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const { t, lang, setLang } = useI18n();
  const config = useApp((s) => s.config);
  return (
    <div className="sticky top-0 z-20 border-b border-line bg-plane/95 backdrop-blur">
      <div className="flex h-12 items-center gap-3 px-4">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenu} aria-label="Menu"><PanelLeftOpen size={16} /></Button>
        <div className="min-w-0 flex-1 truncate text-sm font-medium text-ink-2">{t("app.title")}</div>
        {config && (
          <span className="hidden rounded border border-[#5b4520] px-1.5 py-0.5 text-[11px] text-[#f0c070] sm:inline" title={config.parameter_set.statement[lang]}>
            {t("app.illustrative")}
          </span>
        )}
        <div className="flex items-center gap-0.5 rounded-md border border-line p-0.5" role="group" aria-label={t("app.language")}>
          {(["tr", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              data-testid={`lang-${l}`}
              aria-pressed={lang === l}
              className={cn("rounded px-2 py-0.5 text-xs font-semibold uppercase", lang === l ? "bg-panel-3 text-ink" : "text-muted hover:text-ink")}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2 border-t border-[#3a2f17] bg-[#1a160d] px-4 py-1 text-[11px] text-[#e7c27a]" data-testid="synthetic-banner">
        <TriangleAlert size={13} className="shrink-0" />
        <span className="truncate font-semibold">{t("app.synthetic")}</span>
        <span className="hidden truncate text-[#b99b5e] lg:inline">· {t("app.boundary")}</span>
      </div>
    </div>
  );
}

function Boot({ children }: { children: ReactNode }) {
  const { init, loading, error, config } = useApp();
  const { t } = useI18n();
  useEffect(() => {
    if (!config) void init();
  }, [config, init]);
  if (error && !config) {
    return (
      <div className="mx-auto mt-16 max-w-xl space-y-3">
        <ErrorBox error={`${t("app.backendDown")} (${error})`} onRetry={() => void init()} />
      </div>
    );
  }
  if (!config || loading) {
    return <div className="flex items-center gap-2 p-6 text-sm text-muted"><Spinner /> {t("app.loading")}</div>;
  }
  return <>{children}</>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem("ssrdt-sidebar") === "1");
    } catch { /* ignore */ }
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      try { window.localStorage.setItem("ssrdt-sidebar", c ? "0" : "1"); } catch { /* ignore */ }
      return !c;
    });
  };
  return (
    <I18nProvider>
      <div className="flex min-h-screen">
        <Sidebar collapsed={collapsed} onToggle={toggle} mobileOpen={mobileOpen} onNavigate={() => setMobileOpen(false)} />
        {mobileOpen && <div className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={() => setMobileOpen(false)} aria-hidden />}
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onMenu={() => setMobileOpen(true)} />
          <main className="min-w-0 flex-1 px-4 py-4 lg:px-6">
            <Boot>{children}</Boot>
          </main>
        </div>
      </div>
    </I18nProvider>
  );
}
