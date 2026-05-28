import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Offline fallback", () => {
  const offlinePath = path.join(__dirname, "../../../public/offline.html");

  it("offline.html exists in public directory", () => {
    expect(fs.existsSync(offlinePath)).toBe(true);
  });

  it("offline.html contains a retry button and offline text", () => {
    const content = fs.readFileSync(offlinePath, "utf-8");
    expect(content).toContain("Retry");
    expect(content.toLowerCase()).toContain("offline");
  });
});
