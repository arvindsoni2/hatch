import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const repoRoot = path.resolve(__dirname, "../../../..");
const readmePath = path.join(repoRoot, "README.md");
const readme = fs.readFileSync(readmePath, "utf8");

function localMarkdownLinks(markdown: string): string[] {
  return [...markdown.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)]
    .map((match) => match[1])
    .filter((href) => !href.startsWith("http") && !href.startsWith("#") && !href.startsWith("mailto:"));
}

function localImageLinks(markdown: string): string[] {
  return [...markdown.matchAll(/<img\s+[^>]*src="([^"]+)"/g)].map((match) => match[1]);
}

describe("README release contract", () => {
  it("references only local screenshots and docs that exist", () => {
    for (const image of localImageLinks(readme)) {
      const absolute = path.join(repoRoot, image);
      expect(fs.existsSync(absolute), `${image} should exist`).toBe(true);
      expect(fs.statSync(absolute).size, `${image} should not be empty`).toBeGreaterThan(0);
    }

    for (const href of localMarkdownLinks(readme)) {
      const [withoutAnchor] = href.split("#");
      expect(fs.existsSync(path.join(repoRoot, withoutAnchor)), `${href} should exist`).toBe(true);
    }
  });

  it("keeps install commands on the public main branch", () => {
    expect(readme).toContain("raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh");
    expect(readme).toContain("raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1");
    expect(readme).not.toMatch(/raw\.githubusercontent\.com\/arvindsoni2\/hatch\/(?!main\/)/);
  });

  it("names only hatch wrapper commands that are implemented", () => {
    const cli = fs.readFileSync(path.join(repoRoot, "scripts/hatch_cli.py"), "utf8");
    for (const command of ["status", "doctor", "probe", "models", "apply-ai-config", "capabilities"]) {
      expect(cli, `hatch ${command} should exist`).toMatch(new RegExp(`["']${command}["']`));
    }
  });

  it("states the current safety and document-source boundaries", () => {
    expect(readme).toMatch(/never submits applications automatically/i);
    expect(readme).toMatch(/App lock protects/i);
    expect(readme).toMatch(/AI configuration deferred/i);
    expect(readme).toMatch(/DOCX remains the source of truth/i);
  });

  it("includes release governance files for a public portfolio release", () => {
    for (const file of [
      "LICENSE",
      "CHANGELOG.md",
      "CONTRIBUTING.md",
      "SECURITY.md",
      "docs/RELEASE_CHECKLIST.md",
      ".github/ISSUE_TEMPLATE/bug_report.md",
      ".github/ISSUE_TEMPLATE/feature_request.md",
      ".github/pull_request_template.md",
      "scripts/check_readme_contract.py",
    ]) {
      expect(fs.existsSync(path.join(repoRoot, file)), `${file} should exist`).toBe(true);
    }
  });
});
