import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Layout PWA metadata", () => {
  const layoutContent = fs.readFileSync(
    path.join(__dirname, "../../app/layout.tsx"),
    "utf-8"
  );

  it("includes manifest link", () => {
    expect(layoutContent).toContain("manifest");
  });

  it("includes theme-color meta tag", () => {
    expect(layoutContent).toContain("theme-color");
  });

  it("includes apple web app capable", () => {
    // Next.js metadata API uses appleWebApp: { capable: true } which generates
    // the apple-mobile-web-app-capable meta tag at runtime
    expect(layoutContent).toContain("appleWebApp");
    expect(layoutContent).toContain("capable");
  });

  it("includes apple touch icon", () => {
    // Next.js metadata API uses icons: { apple: ... }
    expect(layoutContent).toContain("apple");
    expect(layoutContent).toContain("icon");
  });
});
