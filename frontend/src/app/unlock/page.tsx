"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Loader2, LockKeyhole } from "lucide-react";
import { APP_LOCK_QUERY_KEY } from "@/components/AppLockGate";
import { PasswordField } from "@/components/security/PasswordField";
import { PasswordRequirementList } from "@/components/security/PasswordRequirementList";
import { Button } from "@/components/ui/button";
import { getAppLockStatus, setupAppLock, unlockApp } from "@/lib/api";
import {
  FALLBACK_PASSWORD_POLICY,
  isPasswordValid,
  passwordError,
} from "@/lib/passwordPolicy";

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
  const [fieldError, setFieldError] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const firstRun = status?.configured_source === "none";
  const policy = status?.password_policy ?? FALLBACK_PASSWORD_POLICY;
  const requirementsId = "setup-password-requirements";
  const matches = password.length > 0 && password === confirm;
  const setupValid = isPasswordValid(password, policy) && matches;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFieldError("");
    setFormError("");
    if (firstRun) {
      const policyError = passwordError(password, policy);
      if (policyError) {
        setFieldError(policyError);
        return;
      }
      if (!matches) {
        setFieldError("Passwords do not match.");
        return;
      }
    }
    setSubmitting(true);
    try {
      if (firstRun) await setupAppLock(password);
      else await unlockApp(password);
      await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
      router.replace(searchParams.get("next") || "/today");
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-[100dvh] place-items-center bg-[var(--bg)] px-4 py-8">
      <div className="w-full max-w-md rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)] sm:p-7">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-[var(--radius-control)] bg-[var(--accent-soft)] text-[var(--accent)]">
          <LockKeyhole aria-hidden="true" className="h-5 w-5" />
        </div>
        <h1 className="text-2xl font-semibold text-[var(--text)]">
          {firstRun ? "Protect your Hatch workspace" : "Unlock Hatch"}
        </h1>
        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
          {firstRun
            ? "Create a local app-lock password. This protects the job-search data stored in this Hatch workspace."
            : "Enter your local app-lock password to continue."}
        </p>

        {isLoading ? (
          <p className="mt-8 flex items-center gap-2 text-sm text-[var(--text-muted)]" role="status">
            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            Checking app lock...
          </p>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
            <PasswordField
              autoComplete={firstRun ? "new-password" : "current-password"}
              autoFocus
              describedBy={firstRun ? requirementsId : undefined}
              error={fieldError}
              label="Password"
              name="password"
              onChange={(value) => {
                setPassword(value);
                setFieldError("");
              }}
              value={password}
            />
            {firstRun ? (
              <>
                <PasswordField
                  autoComplete="new-password"
                  describedBy={requirementsId}
                  label="Confirm password"
                  name="confirm_password"
                  onChange={(value) => {
                    setConfirm(value);
                    setFieldError("");
                  }}
                  value={confirm}
                />
                <PasswordRequirementList
                  confirmPassword={confirm}
                  id={requirementsId}
                  password={password}
                  policy={policy}
                  showMatch
                />
                <div className="flex gap-3 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text-muted)]">
                  <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent)]" />
                  <p>
                    This is not a Hatch cloud account. There is no email recovery. If you forget the password, use the local reset script. Your job-search data is preserved.
                  </p>
                </div>
              </>
            ) : null}
            {!firstRun && status?.retry_after_seconds ? (
              <p className="rounded-[var(--radius-control)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]" role="status">
                Too many failed attempts. Try again in {status.retry_after_seconds} seconds.
              </p>
            ) : !firstRun && status?.failed_attempt_count ? (
              <p className="text-sm text-[var(--text-muted)]" role="status">
                Recent failed attempts: {status.failed_attempt_count}
              </p>
            ) : null}
            {formError ? <p className="text-sm text-[var(--danger)]" role="alert">{formError}</p> : null}
            <Button
              className="w-full"
              disabled={submitting || Boolean(status?.retry_after_seconds) || (firstRun ? !setupValid : password.length === 0)}
              loading={submitting}
              type="submit"
            >
              {firstRun ? "Set password and continue" : "Unlock"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function UnlockPage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-[var(--bg)]" />}>
      <UnlockForm />
    </Suspense>
  );
}
