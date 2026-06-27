import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FilterPanel, type FilterValues } from "@/components/FilterPanel";

const filters: FilterValues = {
  search: "",
  ir35_status: "",
  source: "",
  min_rate: "",
  hide_ghosts: true,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("FilterPanel manual scrape", () => {
  it("shows that an accepted background scrape has started", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ agent: "scout", status: "started" }),
    } as Response);

    render(
      <FilterPanel
        filters={filters}
        onFilterChange={vi.fn()}
        onScrapeComplete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /scrape now/i }));

    await waitFor(() => {
      expect(screen.getByText(/scrape started/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/scrape failed/i)).not.toBeInTheDocument();
  });
});
