import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  WatchedCompaniesClient,
  type CompanyWatchlistItem,
} from "@/app/tracker/watched-companies/WatchedCompaniesClient";

const emptyList = { items: [], total: 0 };

const watchedCompany = {
  id: "watch-1",
  company_name: "Example Cloud",
  company_website: "https://example.com",
  careers_url: "https://example.com/careers",
  source_type: "generic_careers_page",
  status: "active",
  scan_frequency: "daily",
  role_keywords: ["architect"],
  location_preferences: ["London"],
  remote_preference: "any",
  min_match_score: 65,
  last_scanned_at: null,
  last_successful_scan_at: null,
  last_error: null,
  created_at: "2026-07-09T10:00:00Z",
  updated_at: "2026-07-09T10:00:00Z",
  last_scan_new_count: 0,
} satisfies CompanyWatchlistItem;

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("Watched companies page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
  });

  it("shows empty state and creates a watched company without collecting credentials", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response(watchedCompany))
      .mockResolvedValueOnce(response({ items: [watchedCompany], total: 1 }));

    render(<WatchedCompaniesClient initialItems={[]} initialTotal={0} />);

    expect(screen.getByText("Add companies you care about. Hatch will watch for new suitable roles.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Add company/i }));
    fireEvent.change(screen.getByLabelText("Company name"), { target: { value: "Example Cloud" } });
    fireEvent.change(screen.getByLabelText("Careers/job-board URL"), { target: { value: "https://example.com/careers" } });
    fireEvent.change(screen.getByLabelText("Role keywords"), { target: { value: "architect" } });
    fireEvent.click(screen.getByRole("button", { name: /Save company/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/watchlist/companies",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(screen.queryByPlaceholderText(/api key/i)).not.toBeInTheDocument();
  });

  it("runs scans and exposes pause/delete actions", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response({
        id: "run-1",
        watchlist_item_id: "watch-1",
        status: "completed",
        discovered_count: 2,
        new_count: 1,
        duplicate_count: 1,
        imported_count: 1,
        source_provider: "builtin_basic",
      }))
      .mockResolvedValueOnce(response({ items: [watchedCompany], total: 1 }))
      .mockResolvedValueOnce(response({ ...watchedCompany, status: "paused" }))
      .mockResolvedValueOnce(response({ items: [{ ...watchedCompany, status: "paused" }], total: 1 }))
      .mockResolvedValueOnce(response({}))
      .mockResolvedValueOnce(response(emptyList));

    render(<WatchedCompaniesClient initialItems={[watchedCompany]} initialTotal={1} />);

    fireEvent.click(screen.getByRole("button", { name: /Run scan for Example Cloud/i }));
    expect(await screen.findByText(/Scan completed: 1 new, 1 duplicate/i)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Pause Example Cloud/i }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/watchlist/companies/watch-1",
        expect.objectContaining({ method: "PATCH" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /Delete Example Cloud/i }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/watchlist/companies/watch-1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});
