import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("PWA Manifest", () => {
  const manifestPath = path.join(__dirname, "../../../public/manifest.json");

  it("manifest.json exists in public directory", () => {
    expect(fs.existsSync(manifestPath)).toBe(true);
  });

  it("has required PWA fields", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.theme_color).toBeTruthy();
    expect(manifest.background_color).toBeTruthy();
  });

  it("has icons at required sizes (192 and 512)", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    const sizes = manifest.icons.map((i: { sizes: string }) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
  });

  it("has a maskable icon", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    const maskable = manifest.icons.find(
      (i: { purpose?: string }) => i.purpose?.includes("maskable")
    );
    expect(maskable).toBeTruthy();
  });

  it("icon files actually exist on disk", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    for (const icon of manifest.icons) {
      const iconPath = path.join(__dirname, "../../../public", icon.src);
      expect(fs.existsSync(iconPath)).toBe(true);
    }
  });
});
