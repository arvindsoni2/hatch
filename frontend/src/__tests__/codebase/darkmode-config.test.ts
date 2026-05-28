import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Dark mode configuration", () => {
  it("tailwind.config uses class-based dark mode", () => {
    const tsConfig = path.join(__dirname, "../../../tailwind.config.ts");
    const jsConfig = path.join(__dirname, "../../../tailwind.config.js");
    const content = fs.existsSync(tsConfig)
      ? fs.readFileSync(tsConfig, "utf-8")
      : fs.readFileSync(jsConfig, "utf-8");
    expect(content).toContain("darkMode");
    expect(content).toContain('"class"');
  });
});
