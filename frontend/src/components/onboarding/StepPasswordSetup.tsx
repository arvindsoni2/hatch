"use client";

import { FormEvent, useState } from "react";
import { Info, LockKeyhole } from "lucide-react";
import { PasswordField } from "@/components/security/PasswordField";
import { PasswordRequirementList } from "@/components/security/PasswordRequirementList";
import { Button } from "@/components/ui/button";
import { setupAppLock, type PasswordPolicy } from "@/lib/api";
import {
  FALLBACK_PASSWORD_POLICY,
  isPasswordValid,
  passwordError,
} from "@/lib/passwordPolicy";

interface StepPasswordSetupProps {
  onComplete: () => void;
  policy?: PasswordPolicy;
}

function errorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "Unable to set the local password.";
  const match = message.match(/"detail":"([^"]+)"/);
  return match?.[1] ?? message;
}

export function StepPasswordSetup({
  onComplete,
  policy = FALLBACK_PASSWORD_POLICY,
}: StepPasswordSetupProps) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const requirementsId = "onboarding-password-requirements";
  const matches = password.length > 0 && password === confirm;
  const valid = isPasswordValid(password, policy) && matches;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFieldError("");
    setFormError("");
    const policyFailure = passwordError(password, policy);
    if (policyFailure) {
      setFieldError(policyFailure);
      return;
    }
    if (!matches) {
      setFieldError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await setupAppLock(password);
      onComplete();
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="px-5 py-6">
      <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-[var(--radius-control)] bg-[var(--accent-soft)] text-[var(--accent)]">
        <LockKeyhole aria-hidden="true" className="h-5 w-5" />
      </div>
      <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        Local workspace security
      </p>
      <h1 className="mt-2 text-2xl font-semibold text-[var(--text)]">
        Protect your Hatch workspace
      </h1>
      <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
        Create the local app-lock password before adding job-search data. This is stored as a hash and is not a Hatch cloud account.
      </p>

      <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
        <PasswordField
          autoComplete="new-password"
          autoFocus
          describedBy={requirementsId}
          error={fieldError}
          label="Password"
          name="onboarding_password"
          onChange={(value) => {
            setPassword(value);
            setFieldError("");
            setFormError("");
          }}
          value={password}
        />
        <PasswordField
          autoComplete="new-password"
          describedBy={requirementsId}
          label="Confirm password"
          name="onboarding_confirm_password"
          onChange={(value) => {
            setConfirm(value);
            setFieldError("");
            setFormError("");
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
          <p>If you forget this password, use the local app-lock reset command. Resetting the app lock preserves your job-search data.</p>
        </div>
        {formError ? <p className="text-sm text-[var(--danger)]" role="alert">{formError}</p> : null}
        <Button className="w-full" disabled={!valid || submitting} loading={submitting} type="submit">
          Set password and continue
        </Button>
      </form>
    </section>
  );
}
