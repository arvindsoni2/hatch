import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AssistedApplyCard } from "@/components/AssistedApplyCard";
import type { PendingApproval } from "@/lib/api";

// Mock the api module
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    prepareApplication: vi.fn(),
    updateApplicationStatus: vi.fn(),
  };
});

import { prepareApplication, updateApplicationStatus } from "@/lib/api";

function makeApproval(overrides: Partial<PendingApproval> = {}): PendingApproval {
  return {
    application_id: "app-1",
    job_id: "job-1",
    job_title: "Test Engineer",
    company: "Acme",
    rate_text: "£500/day",
    job_url: null,
    overall_score: 0.85,
    skill_match: 0.9,
    experience_match: 0.8,
    rate_match: 0.85,
    location_match: 1.0,
    status: "approved",
    approval_status: "pending",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("AssistedApplyCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows_prepare_button_for_approved_jobs — renders Prepare application button in idle state", () => {
    const app = makeApproval({ status: "approved" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Prepare application/i })).toBeInTheDocument();
  });

  it("shows_ready_card_when_prepared — shows Application ready card when status=ready_to_apply", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByText("Application ready")).toBeInTheDocument();
  });

  it("shows tailored CV ready and cover letter ready in ready state", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Tailored CV ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Cover letter ready/i)).toBeInTheDocument();
  });

  it("mark_as_applied_button_present — Mark as applied button exists in ready card", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Mark as applied/i })).toBeInTheDocument();
  });

  it("Open application button exists in ready card", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Open application/i })).toBeInTheDocument();
  });

  it("no_auto_submit_button — no Auto-submit or Submit automatically button exists", () => {
    const app = makeApproval({ status: "approved" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.queryByText(/Auto-submit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Submit automatically/i)).not.toBeInTheDocument();
  });

  it("no_auto_submit_button in ready state either", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.queryByText(/Auto-submit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Submit automatically/i)).not.toBeInTheDocument();
  });

  it("shows preparing spinner when prepare button clicked", async () => {
    // Return a promise that doesn't resolve immediately
    let resolvePrepare!: (value: unknown) => void;
    const pendingPromise = new Promise((resolve) => { resolvePrepare = resolve; });
    vi.mocked(prepareApplication).mockReturnValue(pendingPromise as ReturnType<typeof prepareApplication>);

    const app = makeApproval({ status: "approved" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Prepare application/i }));

    await waitFor(() => {
      expect(screen.getByText(/Preparing your tailored CV and cover letter/i)).toBeInTheDocument();
    });

    // Clean up
    resolvePrepare({
      job_id: "job-1",
      job_url: "https://example.com",
      cv_path: null,
      cover_letter_path: null,
      prefill_map: {},
    });
  });

  it("transitions to ready after successful prepare", async () => {
    vi.mocked(prepareApplication).mockResolvedValue({
      job_id: "job-1",
      job_url: "https://example.com/apply",
      cv_path: "/tmp/cv.docx",
      cover_letter_path: "/tmp/cl.docx",
      prefill_map: { name: "Alice" },
    });

    const onStatusChange = vi.fn();
    const app = makeApproval({ status: "approved" });
    render(<AssistedApplyCard application={app} onStatusChange={onStatusChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Prepare application/i }));

    await waitFor(() => {
      expect(screen.getByText("Application ready")).toBeInTheDocument();
    });
    expect(onStatusChange).toHaveBeenCalled();
  });

  it("shows reassurance text in ready state", () => {
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Hatch prepared everything/i)).toBeInTheDocument();
    expect(screen.getByText(/you're always in control of the final click/i)).toBeInTheDocument();
  });

  it("calls updateApplicationStatus with 'applied' when Mark as applied clicked", async () => {
    vi.mocked(updateApplicationStatus).mockResolvedValue({} as never);

    const onStatusChange = vi.fn();
    const app = makeApproval({ status: "ready_to_apply" });
    render(<AssistedApplyCard application={app} onStatusChange={onStatusChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Mark as applied/i }));

    await waitFor(() => {
      expect(updateApplicationStatus).toHaveBeenCalledWith("app-1", "applied");
    });
  });
});
