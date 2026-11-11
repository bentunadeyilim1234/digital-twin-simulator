import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

// End-to-end tests run the real stack: FastAPI engine (port 8000, temporary SQLite file)
// and the Next.js app (port 3000). Existing dev servers are reused when already running.
const dbPath = path.join(os.tmpdir(), `ssrdt-e2e-${Date.now()}.sqlite3`);

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "off",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: "../backend/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      env: { TWIN_DB_PATH: dbPath },
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
