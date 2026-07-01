"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole, Loader2 } from "lucide-react";
import { APP_LOCK_QUERY_KEY } from "@/components/AppLockGate";
import { getAppLockStatus, setupAppLock, unlockApp } from "@/lib/api";

function errorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "Unable to unlock Hatch.";
  const match = message.match(/"detail":"([^"]+)"/);
  return match?.[1] ?? message;
}

function UnlockForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery({
    queryKey: APP_LOCK_QUERY_KEY,
    queryFn: getAppLockStatus,
  });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const firstRun = status?.configured_source === "none";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (firstRun && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      if (firstRun) await setupAppLock(password);
      else await unlockApp(password);
      await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
      router.replace(searchParams.get("next") || "/today");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center px-4" style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-md rounded-2xl p-7 shadow-xl" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
          <LockKeyhole className="h-5 w-5" />
        </div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text)" }}>
          {firstRun ? "Protect your Hatch workspace" : "Unlock Hatch"}
        </h1>
        <p className="mt-2 text-sm leading-6" style={{ color: "var(--text-muted)" }}>
          {firstRun
            ? "Create an app password to protect the job-search data stored in this workspace."
            : "Hatch is locked to protect your job-search data. Enter your app password to continue."}
        </p>

        {isLoading ? (
          <div className="mt-8 flex justify-center"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={submit}>
            <label className="block text-sm font-medium">
              Password
              <input
                autoFocus
                type="password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-lg px-3 py-2.5 outline-none"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
              />
            </label>
            {firstRun ? (
              <label className="block text-sm font-medium">
                Confirm password
                <input
                  type="password"
                  minLength={8}
                  required
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  className="mt-2 w-full rounded-lg px-3 py-2.5 outline-none"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                />
              </label>
            ) : null}
            {error ? <p role="alert" className="text-sm text-red-500">{error}</p> : null}
            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
              style={{ background: "var(--accent)", color: "var(--on-accent)" }}
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : firstRun ? "Set password and continue" : "Unlock"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function UnlockPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" style={{ background: "var(--bg)" }} />}>
      <UnlockForm />
    </Suspense>
  );
}
