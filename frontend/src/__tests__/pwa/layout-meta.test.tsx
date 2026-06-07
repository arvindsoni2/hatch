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

  it("has appleWebApp metadata without deprecated capable flag", () => {
    // appleWebApp.capable: true generated the deprecated mobile-web-app-capable meta tag.
    // statusBarStyle is kept; capable is intentionally removed to silence the Chrome warning.
    expect(layoutContent).toContain("appleWebApp");
    expect(layoutContent).toContain("statusBarStyle");
    expect(layoutContent).not.toContain("capable: true");
  });

  it("includes apple touch icon", () => {
    // Next.js metadata API uses icons: { apple: ... }
    expect(layoutContent).toContain("apple");
    expect(layoutContent).toContain("icon");
  });
});
