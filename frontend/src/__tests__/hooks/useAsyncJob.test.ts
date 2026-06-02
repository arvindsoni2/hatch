import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useAsyncJob } from "@/hooks/useAsyncJob";

const mockFetch = vi.fn();
global.fetch = mockFetch;

function makeJobResponse(status: string, result: unknown = null, error: string | null = null) {
  return {
    ok: true,
    json: async () => ({
      id: "job-123",
      type: "tailor_analyse",
      status,
      result,
      error,
      created_at: new Date().toISOString(),
    }),
  };
}

describe("useAsyncJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts idle", () => {
    const { result } = renderHook(() => useAsyncJob());
    expect(result.current.state.status).toBe("idle");
    expect(result.current.state.jobId).toBeNull();
  });

  it("transitions to pending then running after submit", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValue(makeJobResponse("running"));

    const { result } = renderHook(() => useAsyncJob());

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    expect(result.current.state.jobId).toBe("job-123");
  });

  it("transitions to done when poll returns status=done", async () => {
    const resultData = { analysis: { role_title: "Dev" } };
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValueOnce(makeJobResponse("running"))
      .mockResolvedValue(makeJobResponse("done", resultData));

    const onComplete = vi.fn();
    const { result } = renderHook(() => useAsyncJob({ onComplete }));

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.state.status).toBe("done"));
    expect(result.current.state.result).toEqual(resultData);
    expect(onComplete).toHaveBeenCalledWith(resultData);
  });

  it("transitions to failed when poll returns status=failed", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValue(makeJobResponse("failed", null, "LLM timeout"));

    const onError = vi.fn();
    const { result } = renderHook(() => useAsyncJob({ onError }));

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.state.status).toBe("failed"));
    expect(result.current.state.error).toBe("LLM timeout");
    expect(onError).toHaveBeenCalledWith("LLM timeout");
  });

  it("reset returns state to idle", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
    });

    const { result } = renderHook(() => useAsyncJob());

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    act(() => result.current.reset());

    expect(result.current.state.status).toBe("idle");
    expect(result.current.state.jobId).toBeNull();
  });
});
