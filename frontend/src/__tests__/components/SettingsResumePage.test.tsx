import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResumePage from "@/app/settings/resume/page";
import type { ResumeStatus } from "@/lib/api";

const existingStatus: ResumeStatus = {
  exists: true,
  filename: "current-cv.pdf",
  uploaded_at: "2026-07-01T12:00:00",
  parsed: true,
  sections: {
    personal: true,
    summary: true,
    experience: true,
    skills: true,
    education: false,
    certifications: false,
  },
  skills_count: 12,
  experience_count: 3,
  proof_points_count: 7,
};

const emptyStatus: ResumeStatus = {
  exists: false,
  filename: null,
  uploaded_at: null,
  parsed: false,
  sections: {},
  skills_count: 0,
  experience_count: 0,
  proof_points_count: 0,
};

const preview = {
  filename: "new-cv.pdf",
  raw_text_saved: true,
  warnings: [
    "Could not identify complete contact and employment history. Review the parsed CV before saving.",
    "Skills section was partially identified. Review before saving.",
  ],
  parsed_cv: {
    personal: { full_name: "Avery Stone", email: "avery@example.com" },
    summary_variants: { default: "Delivery leader." },
    experience: [{ role: "Delivery Lead", company: "Acme", period: "2022 - Present", achievements: [{ text: "Led delivery." }] }],
    skills: [{ category: "Delivery", items: ["Agile", "Risk"] }],
    certifications: ["PMP"],
  },
};

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

function mockResumeFetch(status: ResumeStatus = emptyStatus) {
  vi.mocked(global.fetch).mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/resume/status")) return jsonResponse(status);
    if (url.endsWith("/api/resume/upload") && init?.method === "POST") return jsonResponse(preview);
    if (url.endsWith("/api/resume/confirm") && init?.method === "POST") return jsonResponse(existingStatus);
    return jsonResponse({});
  });
}

function makeFile(name: string, type: string, size = 1024) {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("Master CV settings page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    mockResumeFetch();
  });

  it("uses the Settings shell and explains local parsing without overpromising", async () => {
    render(<ResumePage />);

    expect(await screen.findByRole("heading", { name: "Master CV" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Master CV" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Settings section")).toHaveValue("/settings/resume");

    expect(screen.getByText(/stored locally/i)).toBeVisible();
    expect(screen.getByText(/parsed into structured profile fields/i)).toBeVisible();
    expect(screen.getByText(/tailoring, coaching, and matching/i)).toBeVisible();
    expect(screen.getByText(/Hatch will only save what it can extract or what you confirm/i)).toBeVisible();
    expect(screen.queryByText(/never invents content/i)).not.toBeInTheDocument();
  });

  it("rejects oversized and unsupported files before upload", async () => {
    render(<ResumePage />);
    const input = await screen.findByLabelText("Upload Master CV");

    await userEvent.upload(input, makeFile("large.pdf", "application/pdf", 10 * 1024 * 1024 + 1));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a .docx or .pdf file under 10 MB.");

    fireEvent.change(input, { target: { files: [makeFile("notes.txt", "text/plain")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF and DOCX files are supported.");
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("requires explicit confirmation before replacing the current Master CV", async () => {
    mockResumeFetch(existingStatus);
    render(<ResumePage />);

    await userEvent.upload(
      await screen.findByLabelText("Upload Master CV"),
      makeFile("new-cv.pdf", "application/pdf"),
    );

    expect(await screen.findByRole("heading", { name: "Review extracted data" })).toBeVisible();
    expect(screen.getByText("This will replace your current Master CV data after you confirm the parsed preview.")).toBeVisible();

    const confirmButton = screen.getByRole("button", { name: "Confirm save" });
    expect(confirmButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /replace current Master CV/i }));
    expect(confirmButton).toBeEnabled();

    fireEvent.click(confirmButton);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "/api/resume/confirm",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("lets users cancel the preview or upload a different file", async () => {
    render(<ResumePage />);
    const input = await screen.findByLabelText("Upload Master CV");

    await userEvent.upload(input, makeFile("new-cv.pdf", "application/pdf"));
    expect(await screen.findByRole("heading", { name: "Review extracted data" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("heading", { name: "Review extracted data" })).not.toBeInTheDocument();

    await userEvent.upload(input, makeFile("new-cv.pdf", "application/pdf"));
    fireEvent.click(await screen.findByRole("button", { name: "Upload a different file" }));
    expect(screen.queryByRole("heading", { name: "Review extracted data" })).not.toBeInTheDocument();
  });

  it("places parse warnings beside the affected preview sections", async () => {
    render(<ResumePage />);

    await userEvent.upload(
      await screen.findByLabelText("Upload Master CV"),
      makeFile("new-cv.pdf", "application/pdf"),
    );

    const experience = await screen.findByRole("region", { name: "Experience" });
    expect(within(experience).getByText(/Could not identify complete contact and employment history/i)).toBeVisible();

    const skills = screen.getByRole("region", { name: "Skills" });
    expect(within(skills).getByText(/Skills section was partially identified/i)).toBeVisible();
  });
});
