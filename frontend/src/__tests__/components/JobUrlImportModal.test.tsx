import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobUrlImportModal } from "@/components/jobs/JobUrlImportModal";

vi.mock("@/lib/api", () => ({ previewJobUrl: vi.fn(), saveImportedJob: vi.fn() }));

describe("JobUrlImportModal", () => {
  it("renders the extraction entry point", () => {
    render(<JobUrlImportModal onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: "Import job from URL" })).toBeTruthy();
    expect(screen.getByLabelText("Job URL")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Extract" })).toBeTruthy();
  });
});
