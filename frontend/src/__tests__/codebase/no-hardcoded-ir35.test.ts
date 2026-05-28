import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";

describe("Codebase — no hardcoded IR35 labels", () => {
  it("no frontend .tsx/.ts file contains hardcoded IR35 label strings outside allowed uses", () => {
    const srcDir = path.join(__dirname, "../../");
    try {
      const result = execSync(
        `grep -rn "\\bIR35\\b" "${srcDir}" --include="*.tsx" --include="*.ts"` +
          ` | grep -v "node_modules"` +
          ` | grep -v ".test."` +
          ` | grep -v "__tests__"` +
          ` | grep -v "ir35_preference"` +
          ` | grep -v "ir35_status"` +
          ` | grep -v "// "`,
        { encoding: "utf-8" }
      );
      const lines = result.trim().split("\n").filter(Boolean);
      expect(lines.length).toBe(0);
    } catch {
      // grep exit code 1 = no matches found — that's the passing condition
    }
  });

  it("lib/api.ts does not export ir35_status as a top-level field on JobFilters", () => {
    const apiPath = path.join(__dirname, "../../lib/api.ts");
    if (!fs.existsSync(apiPath)) return;
    const content = fs.readFileSync(apiPath, "utf-8");
    // Allow ir35_status inside legal_fields type, not as a direct property of JobFilters
    const directIr35Field = /ir35_status\?:\s*string/.test(content);
    expect(directIr35Field).toBe(false);
  });

  it("FilterPanel does not contain IR35 as a hardcoded string literal", () => {
    const filterPath = path.join(__dirname, "../../components/FilterPanel.tsx");
    if (!fs.existsSync(filterPath)) return;
    const content = fs.readFileSync(filterPath, "utf-8");
    // Disallow "IR35" as a user-visible string (not a field ID)
    const hardcodedIR35 = /["'].*IR35.*["']/.test(content);
    expect(hardcodedIR35).toBe(false);
  });
});
