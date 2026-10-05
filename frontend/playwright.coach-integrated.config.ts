// Local-only real Coach API/browser test configuration with synthetic data.

import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const backend = resolve(__dirname, "../backend");
const root = mkdtempSync(join(tmpdir(), "hatch-coach-browser-"));
process.env.HATCH_COACH_TEST_MEDIA_ROOT = join(root, "media");
const config = join(root, "config");
mkdirSync(config);
writeFileSync(join(config, "ai_runtime.json"), JSON.stringify({
  schema_version: 1,
  ai_mode: "not_configured",
  feature_gates: { coach_interview_prep: true },
}));

const backendUrl = "http://127.0.0.1:8133";
const frontendUrl = "http://127.0.0.1:3133";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "coach-conversation-integrated.spec.ts",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: frontendUrl, trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run python -m uvicorn coach_browser_test_server:app --host 127.0.0.1 --port 8133",
      cwd: backend,
      url: `${backendUrl}/api/health`,
      timeout: 60_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 12_000 },
      env: {
        PYTHONPATH: `${backend}:${join(backend, "tests/integration")}`,
        DATABASE_URL: `sqlite+aiosqlite:///${join(root, "coach.db")}`,
        HATCH_CONFIG_DIR: config,
        HATCH_COACH_MEDIA_ROOT: join(root, "media"),
        HATCH_COACH_CONVERSATIONAL_ENABLED: "true",
        HATCH_APP_LOCK_ENABLED: "false",
        LANGGRAPH_CHECKPOINT_DB: `sqlite:///${join(root, "checkpoints.db")}`,
        DIGEST_ENABLED: "false",
        ANTHROPIC_API_KEY: "",
        OPENAI_API_KEY: "",
        GOOGLE_API_KEY: "",
        OLLAMA_BASE_URL: "http://127.0.0.1:1",
        HF_HUB_OFFLINE: "1",
        TRANSFORMERS_OFFLINE: "1",
      },
    },
    {
      command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3133",
      cwd: __dirname,
      url: frontendUrl,
      timeout: 120_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 12_000 },
      env: { API_URL: backendUrl, NEXT_TELEMETRY_DISABLED: "1" },
    },
  ],
});
