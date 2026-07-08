import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentQualityAcknowledgementRequiredError, downloadDocument } from "@/lib/api";

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

  it("throws a typed error when quality warnings need acknowledgement", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        post_generation: {
          export_confidence: "acknowledge_required",
        },
        pack_version: "pack-v1",
      }),
    } as Response);

    await expect(downloadDocument("cv-id")).rejects.toBeInstanceOf(
      DocumentQualityAcknowledgementRequiredError,
    );
    expect(sessionStorage.getItem("quality-ack:cv-id:pack-v1")).toBeNull();
  });

  it("records acknowledgement and downloads when the caller confirms quality warnings inline", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        post_generation: {
          export_confidence: "acknowledge_required",
        },
        pack_version: "pack-v1",
      }),
    } as Response);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await downloadDocument("cv-id", { acknowledgeQualityWarnings: true });

    expect(sessionStorage.getItem("quality-ack:cv-id:pack-v1")).toBeTruthy();
    expect(click).toHaveBeenCalledOnce();
    click.mockRestore();
  });
});
