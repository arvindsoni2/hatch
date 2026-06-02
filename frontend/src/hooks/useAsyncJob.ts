"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAsyncJob, AsyncJobResponse } from "@/lib/api";

export interface AsyncJobState<T> {
  jobId: string | null;
  status: "idle" | "pending" | "running" | "done" | "failed";
  result: T | null;
  error: string | null;
}

interface UseAsyncJobOptions<T> {
  pollIntervalMs?: number;
  onComplete?: (result: T) => void;
  onError?: (err: string) => void;
}

export function useAsyncJob<T = unknown>(options?: UseAsyncJobOptions<T>) {
  const { pollIntervalMs = 3000, onComplete, onError } = options ?? {};

  const [state, setState] = useState<AsyncJobState<T>>({
    jobId: null,
    status: "idle",
    result: null,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    const jobId = jobIdRef.current;
    if (!jobId) return;

    try {
      const job = await getAsyncJob<T>(jobId);
      setState((prev) => ({
        ...prev,
        status: job.status as AsyncJobState<T>["status"],
      }));

      if (job.status === "done") {
        stopPolling();
        setState((prev) => ({ ...prev, result: job.result }));
        onComplete?.(job.result as T);
      } else if (job.status === "failed") {
        stopPolling();
        setState((prev) => ({ ...prev, error: job.error }));
        onError?.(job.error ?? "Job failed");
      }
    } catch {
      // Network error during poll — keep trying
    }
  }, [stopPolling, onComplete, onError]);

  const submit = useCallback(
    async (postFn: () => Promise<{ job_id: string }>) => {
      stopPolling();
      setState({ jobId: null, status: "pending", result: null, error: null });

      try {
        const ref = await postFn();
        jobIdRef.current = ref.job_id;
        setState((prev) => ({ ...prev, jobId: ref.job_id, status: "pending" }));

        await poll();
        intervalRef.current = setInterval(() => void poll(), pollIntervalMs);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Request failed";
        setState({ jobId: null, status: "failed", result: null, error: msg });
        onError?.(msg);
      }
    },
    [stopPolling, poll, pollIntervalMs, onError]
  );

  const reset = useCallback(() => {
    stopPolling();
    jobIdRef.current = null;
    setState({ jobId: null, status: "idle", result: null, error: null });
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  return { state, submit, reset };
}
