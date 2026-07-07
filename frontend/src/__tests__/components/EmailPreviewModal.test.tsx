import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EmailPreviewModal } from "@/components/EmailPreviewModal";
import {
  getDigestStatus,
  regenerateEmail,
  sendEmail,
  skipEmail,
  type FollowUpEmailRead,
} from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getDigestStatus: vi.fn(),
    regenerateEmail: vi.fn(),
    sendEmail: vi.fn(),
    skipEmail: vi.fn(),
  };
});

const baseEmail: FollowUpEmailRead = {
  id: "email-1",
  application_id: "app-1",
  email_type: "post_application",
  recipient_email: "recruiter@example.com",
  subject: "Following up",
  body_html: "<p>Hello recruiter</p>",
  body_plain: "Hello recruiter",
  status: "draft",
  created_at: "2026-07-07T09:00:00Z",
  job_title: "Delivery Lead",
  company: "Acme",
};

function renderModal(email: FollowUpEmailRead = baseEmail) {
  const onClose = vi.fn();
  const onSent = vi.fn();
  render(<EmailPreviewModal email={email} onClose={onClose} onSent={onSent} />);
  return { onClose, onSent };
}

describe("EmailPreviewModal send safety", () => {
  beforeEach(() => {
    vi.mocked(getDigestStatus).mockResolvedValue({
      enabled: false,
      time: "08:00",
      timezone: "Europe/London",
      frequency: "daily",
      smtp_configured: true,
      recipient: null,
    });
    vi.mocked(sendEmail).mockResolvedValue({ success: true, message: "ok" });
    vi.mocked(regenerateEmail).mockResolvedValue({
      ...baseEmail,
      subject: "Updated subject",
      body_plain: "Updated body",
      body_html: "<p>Updated body</p>",
    });
    vi.mocked(skipEmail).mockResolvedValue({ ...baseEmail, status: "skipped" });
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  it("disables direct send when SMTP readiness is not confirmed", async () => {
    vi.mocked(getDigestStatus).mockResolvedValueOnce({
      enabled: false,
      time: "08:00",
      timezone: "Europe/London",
      frequency: "daily",
      smtp_configured: false,
      recipient: null,
    });

    renderModal();

    expect(await screen.findByText("Direct send is unavailable until SMTP is configured.")).toBeVisible();
    expect(screen.getByRole("button", { name: /Send Directly/i })).toBeDisabled();
  });

  it("blocks invalid recipients and reviews details before direct send", async () => {
    renderModal();

    fireEvent.change(screen.getByLabelText("To"), { target: { value: "not-an-email" } });
    fireEvent.click(await screen.findByRole("button", { name: /Send Directly/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid recipient email address.");
    expect(sendEmail).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("To"), { target: { value: "hiring@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Send Directly/i }));

    expect(await screen.findByRole("heading", { name: "Review before direct send" })).toBeVisible();
    expect(screen.getByText("hiring@example.com")).toBeVisible();
    expect(sendEmail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm direct send" }));

    await waitFor(() => {
      expect(sendEmail).toHaveBeenCalledWith("email-1", {
        send_via: "smtp",
        recipient_email: "hiring@example.com",
        subject: "Following up",
        body: "Hello recruiter",
      });
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Email sent directly.");
  });

  it("asks before discarding edited body changes for regenerate and skip", async () => {
    renderModal();

    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Edited body" } });
    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));

    expect(await screen.findByRole("heading", { name: "Discard unsaved email edits?" })).toBeVisible();
    expect(regenerateEmail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Discard edits and regenerate" }));

    await waitFor(() => {
      expect(regenerateEmail).toHaveBeenCalledWith("email-1");
    });

    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Edited again" } });
    fireEvent.click(screen.getByRole("button", { name: /Skip/i }));

    expect(await screen.findByRole("heading", { name: "Discard unsaved email edits?" })).toBeVisible();
    expect(skipEmail).not.toHaveBeenCalled();
  });

  it("explains the sandboxed HTML preview and keeps the editable plain text fallback", async () => {
    renderModal();

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByText("HTML preview is sandboxed. Switch back to Plain to edit the fallback text.")).toBeVisible();
    expect(screen.getByTitle("Sandboxed email HTML preview")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Plain" }));
    expect(screen.getByLabelText("Body")).toHaveValue("Hello recruiter");
  });
});
