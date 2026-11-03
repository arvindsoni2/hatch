import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import NewStoryPage from "../page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams("competency=Data%20migration"),
}));

vi.mock("@/components/coach/StoryEditor", () => ({
  StoryEditor: ({ initialData }: { initialData?: { title?: string } }) => (
    <div data-testid="story-editor-title">{initialData?.title ?? "blank"}</div>
  ),
}));

describe("NewStoryPage", () => {
  it("prefills the editor from the competency query", async () => {
    render(<NewStoryPage />);

    expect(await screen.findByTestId("story-editor-title")).toHaveTextContent(
      "Data migration",
    );
  });
});
