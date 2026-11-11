import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "Okul Güvenliği ve Dayanıklılığı Dijital İkizi · School Safety & Resilience Digital Twin",
  description:
    "Deterministic institutional simulation of school preparedness, support capacity and organisational processes. Synthetic demonstration data.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#0b0e12", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" className="dark">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
