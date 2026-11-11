import { expect, test, type Page } from "@playwright/test";

// Complete research workflow (MASTER PROMPT §20, steps 1-14) in one browser session.
// Navigation uses the in-app sidebar so client state behaves exactly as for a user.

async function nav(page: Page, key: string) {
  await page.click(`[data-testid=nav-${key}]`);
}

async function setNumber(page: Page, label: string, value: string) {
  const input = page.getByLabel(label, { exact: true });
  await input.fill(value);
  await input.press("Enter");
}

test("complete simulation workflow with persistence", async ({ page }) => {
  // 1. Open the application
  await page.goto("/");
  await expect(page.getByTestId("synthetic-banner")).toContainText("SENTETİK");
  await expect(page.getByTestId("domain-ENV")).toBeVisible();
  await expect(page.getByTestId("domain-TOTAL")).toContainText("0.628");

  // 2. Load synthetic data (generate a new reproducible dataset)
  await nav(page, "data");
  const before = await page.getByTestId("dataset-list").locator("li").count();
  await page.getByTestId("gen-seed").fill("123");
  await page.getByTestId("gen-months").fill("30");
  await page.getByTestId("generate-synthetic").click();
  await expect(page.getByTestId("dataset-list").locator("li")).toHaveCount(before + 1);
  await expect(page.getByTestId("quality-table")).toBeVisible();

  // 3-6. Change environmental, social, organisational and support variables (baseline scenario)
  await nav(page, "variables");
  await setNumber(page, "E value", "0.800");
  await setNumber(page, "T value", "0.600");
  await setNumber(page, "K value", "0.700");
  await setNumber(page, "S value", "0.650");
  await expect(page.getByTestId("raw-S")).toContainText("208.00"); // 0.65 x 320 h computed by the engine
  await page.getByTestId("save-variables").click();
  await expect(page.getByTestId("save-variables")).toBeDisabled();

  // 7. Modify a causal coefficient (H7: staff training -> preparedness)
  await nav(page, "causal");
  await page.getByTestId("edge-H7").dispatchEvent("click");
  await expect(page.getByTestId("edge-editor")).toContainText("H7");
  await setNumber(page, "coefficient value", "0.300");
  await page.getByTestId("save-edge").click();
  await expect(page.getByTestId("edge-editor")).toContainText(/Özgün değerden değiştirildi|Modified from original/);

  // 8. Create a new scenario from a template (inherits the edited baseline conditions)
  await nav(page, "scenarios");
  await page.getByTestId("template-select").selectOption("S2");
  const rowsBefore = await page.getByTestId("scenario-table").locator("tbody tr").count();
  await page.getByTestId("new-from-template").click();
  await expect(page.getByTestId("scenario-table").locator("tbody tr")).toHaveCount(rowsBefore + 1);

  // 9. Run a 12-month simulation of the new scenario
  await nav(page, "lab");
  await expect(page.getByTestId("lab-scenario").locator("option:checked")).toContainText(/kopya|copy/);
  await page.getByTestId("run-simulation").click();

  // 10. Compare against baseline
  const delta = page.getByTestId("delta-table");
  await expect(delta).toBeVisible();
  await expect(delta.locator("tbody tr")).toHaveCount(6); // baseline + S1-S4 + new scenario
  await expect(page.getByTestId("comparability")).toContainText(/Koşullar aynı|Identical conditions/);

  // 11. Inspect charts (rendered SVG lines with data)
  await expect(page.getByTestId("chart-main").locator("path.recharts-curve").first()).toBeVisible();
  await expect(page.getByTestId("stockflow")).toBeVisible();

  // 13. Export results (CSV produced by the engine)
  const dl = page.waitForEvent("download");
  await page.getByTestId("export-csv").click();
  const file = await dl;
  const text = await (await file.createReadStream()).toArray().then((c) => Buffer.concat(c).toString());
  expect(text).toContain("index_TOTAL");
  expect(text).toContain("SYNTHETIC");

  // 12. Inspect the 3D school (lazy-loaded WebGL scene + linked indicators)
  await nav(page, "twin");
  await expect(page.locator("[data-testid=twin-viewport] canvas")).toBeVisible();
  await page.getByTestId("zone-support").click();
  await expect(page.getByTestId("twin-selected")).toHaveAttribute("data-zone", "support");
  await expect(page.getByTestId("twin-indicators")).toContainText("A");
  await page.getByTestId("floor-1").click();
  await page.getByTestId("zone-library").click();
  await expect(page.getByTestId("twin-label")).toContainText(/Kütüphane|Library/);

  // 14. Reload the project and verify persistence (same browser workspace)
  await page.reload();
  await nav(page, "scenarios");
  await expect(page.getByTestId("scenario-table").locator("tbody tr")).toHaveCount(rowsBefore + 1);
  const persisted = await page.evaluate(async () => {
    const ws = localStorage.getItem("ssrdt-workspace") || "default";
    const m = await (await fetch("/api/model", { headers: { "X-Workspace-Id": ws } })).json();
    const s = await (await fetch("/api/scenarios", { headers: { "X-Workspace-Id": ws } })).json();
    return { h7: m.config.edges.find((e: { id: string }) => e.id === "H7").coefficient, E: s.find((x: { is_baseline: boolean }) => x.is_baseline).initial_state.E };
  });
  expect(persisted.h7).toBeCloseTo(0.3);
  expect(persisted.E).toBeCloseTo(0.8);
});

test("scenario duplication, rename and deletion", async ({ page }) => {
  await page.goto("/scenarios");
  const rows = page.getByTestId("scenario-table").locator("tbody tr");
  await expect(rows).toHaveCount(5); // seeded S0-S4 in this fresh browser workspace
  const n = await rows.count();
  await page.locator("[data-testid^=dup-]").nth(1).click();
  await expect(rows).toHaveCount(n + 1);
  await rows.nth(n).getByRole("button", { name: /Yeniden adlandır|Rename/ }).click();
  await page.getByTestId("rename-input").fill("E2E renamed scenario");
  await page.getByTestId("confirm-rename").click();
  await expect(page.getByTestId("scenario-table")).toContainText("E2E renamed scenario");
  await rows.nth(n).getByRole("button", { name: /^(Sil|Delete) / }).click();
  await page.getByTestId("confirm-delete").click();
  await expect(rows).toHaveCount(n);
});

test("localisation switches between Turkish (default) and English", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-lab")).toHaveText("Simülasyon Laboratuvarı");
  await expect(page.locator("html")).toHaveAttribute("lang", "tr");
  await page.getByTestId("lang-en").click();
  await expect(page.getByTestId("nav-lab")).toHaveText("Simulation Lab");
  await expect(page.getByTestId("synthetic-banner")).toContainText("SYNTHETIC DEMONSTRATION DATA");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.reload();
  await expect(page.getByTestId("nav-lab")).toHaveText("Simulation Lab"); // persisted preference
});

test("responsive layout at phone and tablet width", async ({ page }) => {
  for (const [w, h] of [[390, 844], [820, 1180]]) {
    await page.setViewportSize({ width: w, height: h });
    for (const p of ["/", "/lab", "/twin", "/variables"]) {
      await page.goto(p);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${p} at ${w}px`).toBeLessThanOrEqual(1);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByTestId("nav-causal").click();
  await expect(page).toHaveURL(/\/causal/);
});

test("sensitivity analysis and variables filters", async ({ page }) => {
  await page.goto("/analytics");
  await page.getByRole("tab", { name: /Duyarlılık|Sensitivity/ }).click();
  await page.getByTestId("sa-method").selectOption("morris");
  await page.getByTestId("sa-n").fill("4");
  await page.getByTestId("run-sa").click();
  await expect(page.getByTestId("sa-ranking").locator("li").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("sa-heatmap")).toBeVisible();
  await page.goto("/variables");
  await page.getByTestId("filter-domain").selectOption("SUP");
  await expect(page.locator("[data-testid^=var-]").filter({ has: page.locator("input") })).toHaveCount(4);
});
