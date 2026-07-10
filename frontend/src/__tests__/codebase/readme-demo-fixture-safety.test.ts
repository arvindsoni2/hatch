import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const DEMO_FIXTURE = join(ROOT, "src/demo/readmeDemoData.ts");
const SCREENSHOT_SPEC = join(ROOT, "e2e/readme-screenshots.spec.ts");

const FORBIDDEN_PATTERNS = [
  /@(?:gmail|hotmail|outlook|yahoo|icloud)\.com/i,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
  /\b(?:\+?\d[\d\s().-]{8,}\d)\b/,
  /\b(?:sk-|OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY)\b/i,
  /\/home\/asoni/i,
  /Arjun Mehta|Arvind Soni|Asoni/i,
];

describe("README demo fixture safety", () => {
  it("uses committed fictional fixture data without secrets or local paths", () => {
    const content = [
      readFileSync(DEMO_FIXTURE, "utf8"),
      readFileSync(SCREENSHOT_SPEC, "utf8"),
    ].join("\n");

    for (const pattern of FORBIDDEN_PATTERNS) {
      expect(content).not.toMatch(pattern);
    }
  });
});
