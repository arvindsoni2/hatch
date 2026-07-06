import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadDocument } from "@/lib/api";

describe("downloadDocument", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    sessionStorage.clear();
  });

  it("starts the download when a cover letter has no CV quality gate", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);
    let clickedLink: HTMLAnchorElement | undefined;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clickedLink = this;
    });

    await downloadDocument("cover-letter-id");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/tailor/quality/document/cover-letter-id",
      expect.any(Object),
    );
    expect(click).toHaveBeenCalledOnce();
    if (!clickedLink) throw new Error("Expected a download link to be clicked.");
    expect(clickedLink.href).toContain("/api/tailor/document/cover-letter-id/download");
    expect(clickedLink.download).toBe("");
    expect(document.body.contains(clickedLink)).toBe(false);
    click.mockRestore();
  });
});
