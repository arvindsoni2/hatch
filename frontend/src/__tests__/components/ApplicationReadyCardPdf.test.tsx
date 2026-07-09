import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const downloadDocument = vi.fn();
const exportPackagePdf = vi.fn();
const downloadDocumentAsset = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    downloadDocument: (...args: unknown[]) => downloadDocument(...args),
    exportPackagePdf: (...args: unknown[]) => exportPackagePdf(...args),
    downloadDocumentAsset: (...args: unknown[]) => downloadDocumentAsset(...args),
  };
});

const READY_JOB = {
  id: "app-1",
  title: "Solutions Architect",
  company: "Hays",
  loc: "London",
  rate: "GBP 650/day",
  score: 1,
  ats: 95,
  state: "ready" as const,
};

const READY_PACKAGE = {
  job_id: "app-1",
  job_url: "https://example.com/apply",
  cv_path: "/tmp/cv.docx",
  cover_letter_path: "/tmp/cl.docx",
  cv_document_id: "cv-doc",
  cl_document_id: "cl-doc",
  prefill_map: {},
  screening_answers: {},
  paste_map: {},
};

describe("ApplicationReadyCard PDF export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  it("keeps DOCX download available when PDF export is unavailable", async () => {
    const { ApplicationReadyCard } = await import("@/components/hatch/ApplicationReadyCard");
    exportPackagePdf.mockRejectedValue(new Error("PDF export is not installed in this setup."));

    render(<ApplicationReadyCard job={READY_JOB} pkg={READY_PACKAGE} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Download CV DOCX/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Download CV PDF/i }));

    await waitFor(() => {
      expect(screen.getByText("PDF export is not installed in this setup.")).toBeTruthy();
    });
    expect(downloadDocument).not.toHaveBeenCalled();
  });

  it("exports a PDF asset before previewing or downloading it", async () => {
    const { ApplicationReadyCard } = await import("@/components/hatch/ApplicationReadyCard");
    exportPackagePdf.mockResolvedValue({
      id: "asset-1",
      application_id: "app-1",
      package_id: "app-1",
      source_document_id: "cv-doc",
      kind: "cv",
      format: "pdf",
      generation_status: "completed",
      created_at: "2026-07-09T10:00:00Z",
    });

    render(<ApplicationReadyCard job={READY_JOB} pkg={READY_PACKAGE} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Preview CV PDF/i }));
    await waitFor(() => {
      expect(exportPackagePdf).toHaveBeenCalledWith("app-1", "cv");
      expect(window.open).toHaveBeenCalledWith("/api/documents/assets/asset-1", "_blank", "noopener,noreferrer");
    });

    fireEvent.click(screen.getByRole("button", { name: /Download CV PDF/i }));
    await waitFor(() => {
      expect(downloadDocumentAsset).toHaveBeenCalledWith("asset-1", "Solutions-Architect-cv.pdf");
    });
  });
});
