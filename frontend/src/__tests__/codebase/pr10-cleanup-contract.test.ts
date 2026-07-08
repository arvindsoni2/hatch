import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";

const srcDir = path.join(__dirname, "../../");

function collectFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (["__tests__", "node_modules"].includes(entry.name)) continue;
      results.push(...collectFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

describe("PR10 cleanup contract", () => {
  it("does not use browser alert or confirm in runtime frontend code", () => {
    const offenders = collectFiles(srcDir)
      .filter((file) => !file.includes(`${path.sep}__tests__${path.sep}`))
      .flatMap((file) => {
        const content = fs.readFileSync(file, "utf-8");
        return /\b(window\.)?(alert|confirm)\s*\(/.test(content)
          ? [file.replace(`${srcDir}${path.sep}`, "")]
          : [];
      });

    expect(offenders).toEqual([]);
  });

  it("removes confirmed-unused legacy shell components", () => {
    expect(fs.existsSync(path.join(srcDir, "components/Sidebar.tsx"))).toBe(false);
    expect(fs.existsSync(path.join(srcDir, "components/BottomNav.tsx"))).toBe(false);
  });
});
