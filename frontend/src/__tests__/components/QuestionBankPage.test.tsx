import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  QuestionBankClient,
  type QuestionBankItem,
} from "@/app/prep/question-bank/QuestionBankClient";

const item = {
  id: "qb-1",
  type: "interview_question",
  question: "Tell me about a complex migration.",
  title: "Complex migration answer",
  answer_draft: "I led a staged migration with stakeholder checkpoints.",
  situation: "Legacy platform",
  task: "Move safely",
  action: "Split work into waves",
  result: "No customer impact",
  skills: ["cloud architecture"],
  tags: ["migration"],
  seniority: "senior",
  role_family: "solutions_architect",
  linked_applications: [],
  source: "manual",
  confidence: "draft",
  source_session_id: null,
  source_question_id: null,
  archived_at: null,
  created_at: "2026-07-09T10:00:00Z",
  updated_at: "2026-07-09T10:00:00Z",
} satisfies QuestionBankItem;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("Question Bank page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
  });

  it("creates and filters reusable answers without requiring AI", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response(item, 201))
      .mockResolvedValueOnce(response({ items: [item], total: 1, skip: 0, limit: 50 }))
      .mockResolvedValueOnce(response({ items: [item], total: 1, skip: 0, limit: 50 }));

    render(<QuestionBankClient initialItems={[]} initialTotal={0} />);

    expect(screen.getByText("Question Bank works in Basic mode without AI.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Add entry/i }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Complex migration answer" } });
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Tell me about a complex migration." } });
    fireEvent.change(screen.getByLabelText("Answer draft"), { target: { value: "I led a staged migration." } });
    fireEvent.change(screen.getByLabelText("Tags"), { target: { value: "migration" } });
    fireEvent.click(screen.getByRole("button", { name: /Save entry/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/question-bank",
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "migration" } });
    fireEvent.click(screen.getByRole("button", { name: /Apply filters/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/question-bank?search=migration", expect.any(Object));
    });
  });

  it("edits and deletes existing entries", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response({ ...item, confidence: "final" }))
      .mockResolvedValueOnce(response({ items: [{ ...item, confidence: "final" }], total: 1, skip: 0, limit: 50 }))
      .mockResolvedValueOnce(response({}, 204))
      .mockResolvedValueOnce(response({ items: [], total: 0, skip: 0, limit: 50 }));

    render(<QuestionBankClient initialItems={[item]} initialTotal={1} />);

    fireEvent.click(screen.getByRole("button", { name: /Edit Complex migration answer/i }));
    fireEvent.change(screen.getByLabelText("Confidence"), { target: { value: "final" } });
    fireEvent.click(screen.getByRole("button", { name: /Save entry/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/question-bank/qb-1",
        expect.objectContaining({ method: "PATCH" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /Delete Complex migration answer/i }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/question-bank/qb-1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});
