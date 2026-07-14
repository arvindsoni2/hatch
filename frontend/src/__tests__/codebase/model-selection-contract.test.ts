import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(process.cwd(), "..");
const EASY_INSTALL_FILES = [
  "README.md",
  "install.sh",
  "install.ps1",
  "docker-compose.easy.yml",
  "docker-compose.local-ai.yml",
  "scripts/fetch_models.sh",
  "scripts/verify_runtime.sh",
  "frontend/src/app/onboarding/page.tsx",
  "frontend/src/app/settings/ai/page.tsx",
  "frontend/src/components/setup/AiCapabilitiesForm.tsx",
];

describe("selection-driven model contract", () => {
  it("keeps fixed model downloads and compose defaults out of beginner paths", () => {
    for (const file of EASY_INSTALL_FILES) {
      const text = readFileSync(resolve(ROOT, file), "utf8");
      expect(text, file).not.toMatch(/huggingface\.co\/.*Qwen|:-Qwen/);
    }
  });

  it("preserves the explicitly documented developer-stack exception", () => {
    const compose = readFileSync(resolve(ROOT, "docker-compose.yml"), "utf8");
    expect(compose).toContain("Qwen_Qwen3.5-4B-Q4_K_M.gguf");
    expect(compose).toContain("Qwen_Qwen3.5-0.8B-Q8_0.gguf");
  });

  it("requires explicit primary and triage variables in the easy local overlay", () => {
    const compose = readFileSync(resolve(ROOT, "docker-compose.local-ai.yml"), "utf8");
    expect(compose).toContain("HATCH_PRIMARY_MODEL_FILE:?");
    expect(compose).toContain("HATCH_TRIAGE_MODEL_FILE:?");
  });
});
