import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("core job-search route states", () => {
  it("renders a named Pipeline loading skeleton", async () => {
    const { default: Loading } = await import("@/app/stream/loading");

    render(<Loading />);

    expect(screen.getByRole("status", { name: "Loading Pipeline" })).toBeVisible();
    expect(screen.getAllByTestId("pipeline-loading-skeleton")).toHaveLength(3);
  });

  it("renders a recoverable Pipeline error with Diagnostics", async () => {
    const { default: ErrorState } = await import("@/app/stream/error");
    const reset = vi.fn();

    render(<ErrorState error={new Error("pipeline unavailable")} reset={reset} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Pipeline could not load");
    expect(screen.getByText("pipeline unavailable")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Open Diagnostics" })).toHaveAttribute("href", "/settings/system");
  });

  it("renders a named Applications loading skeleton", async () => {
    const { default: Loading } = await import("@/app/tracker/loading");

    render(<Loading />);

    expect(screen.getByRole("status", { name: "Loading Applications" })).toBeVisible();
    expect(screen.getAllByTestId("applications-loading-skeleton")).toHaveLength(4);
  });

  it("renders a recoverable Applications error with Diagnostics", async () => {
    const { default: ErrorState } = await import("@/app/tracker/error");
    const reset = vi.fn();

    render(<ErrorState error={new Error("kanban unavailable")} reset={reset} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Applications could not load");
    expect(screen.getByText("kanban unavailable")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Open Diagnostics" })).toHaveAttribute("href", "/settings/system");
  });

  it("renders a named CV Studio loading skeleton", async () => {
    const { default: Loading } = await import("@/app/tailor/loading");

    render(<Loading />);

    expect(screen.getByRole("status", { name: "Loading CV Studio" })).toBeVisible();
    expect(screen.getAllByTestId("cv-studio-loading-skeleton")).toHaveLength(3);
  });

  it("renders a recoverable CV Studio error with Diagnostics", async () => {
    const { default: ErrorState } = await import("@/app/tailor/error");
    const reset = vi.fn();

    render(<ErrorState error={new Error("tailoring unavailable")} reset={reset} />);

    expect(screen.getByRole("alert")).toHaveTextContent("CV Studio could not load");
    expect(screen.getByText("tailoring unavailable")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Open Diagnostics" })).toHaveAttribute("href", "/settings/system");
  });
});
