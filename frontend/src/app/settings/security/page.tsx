"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Info, Loader2, LockKeyhole, Terminal } from "lucide-react";
import { APP_LOCK_QUERY_KEY } from "@/lib/api";
import { PasswordField } from "@/components/security/PasswordField";
import { PasswordRequirementList } from "@/components/security/PasswordRequirementList";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import {
  changeAppLockPassword,
  getAppLockStatus,
  lockApp,
} from "@/lib/api";
import {
  FALLBACK_PASSWORD_POLICY,
  isPasswordValid,
  passwordError,
} from "@/lib/passwordPolicy";

function apiError(error: unknown): string {
  const message = error instanceof Error ? error.message : "Password change failed.";
  const match = message.match(/"detail":"([^"]+)"/);
  return match?.[1] ?? message;
}

export default function SecuritySettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery({
    queryKey: APP_LOCK_QUERY_KEY,
    queryFn: getAppLockStatus,
  });
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [newPasswordFieldError, setNewPasswordFieldError] = useState("");
  const [confirmError, setConfirmError] = useState("");
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [working, setWorking] = useState(false);
  const policy = status?.password_policy ?? FALLBACK_PASSWORD_POLICY;
  const requirementsId = "change-password-requirements";
  const passwordsMatch = newPassword.length > 0 && newPassword === confirm;
  const newPasswordDiffers = newPassword.length > 0 && newPassword !== currentPassword;
  const formValid =
    currentPassword.length > 0
    && isPasswordValid(newPassword, policy)
    && passwordsMatch
    && newPasswordDiffers;

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    setNewPasswordFieldError("");
    setConfirmError("");
    setFormError("");
    setSuccess("");
    const policyError = passwordError(newPassword, policy);
    if (policyError) {
      setNewPasswordFieldError(policyError);
      return;
    }
    if (!passwordsMatch) {
      setConfirmError("New passwords do not match.");
      return;
    }
    if (!newPasswordDiffers) {
      setNewPasswordFieldError("New password must be different from the current password.");
      return;
    }
    setWorking(true);
    try {
      await changeAppLockPassword(currentPassword, newPassword);
      await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setSuccess("Password changed. Other sessions have been locked.");
    } catch (error) {
      setFormError(apiError(error));
    } finally {
      setWorking(false);
    }
  };

  const lock = async () => {
    setWorking(true);
    setFormError("");
    try {
      await lockApp();
      queryClient.setQueryData(APP_LOCK_QUERY_KEY, { ...status, is_unlocked: false });
      router.replace("/unlock");
    } catch (error) {
      setFormError(apiError(error));
      setWorking(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link className="hatch-interactive inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-control)] text-sm text-[var(--text-muted)] hover:text-[var(--text)]" href="/settings/profile">
        <ArrowLeft aria-hidden="true" className="h-4 w-4" /> Settings
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text)]">Security &amp; App Lock</h1>
        <p className="mt-1 text-sm text-[var(--text-muted)]">Protect access to this single-user Hatch workspace.</p>
      </div>

      <SectionCard>
        {isLoading ? (
          <p className="flex items-center gap-2 text-sm text-[var(--text-muted)]" role="status">
            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            Checking app lock...
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <LockKeyhole aria-hidden="true" className="mt-0.5 h-5 w-5 text-[var(--accent)]" />
              <div>
                <h2 className="font-semibold text-[var(--text)]">
                  {status?.enabled ? "App lock is enabled" : "App lock is disabled"}
                </h2>
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  {status?.configured_source === "env"
                    ? "Password is managed by environment configuration."
                    : "Password is managed in this local Hatch workspace."}
                </p>
              </div>
            </div>
            {!status?.enabled ? (
              <p className="rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text-muted)]">
                App lock is disabled by environment configuration.
              </p>
            ) : null}
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[var(--text-muted)]">Current session</dt>
                <dd className="font-medium text-[var(--text)]">{status?.is_unlocked ? "Unlocked" : "Locked"}</dd>
              </div>
              {status?.last_unlocked_at ? (
                <div>
                  <dt className="text-[var(--text-muted)]">Last unlocked</dt>
                  <dd className="font-medium text-[var(--text)]">{new Date(status.last_unlocked_at).toLocaleString()}</dd>
                </div>
              ) : null}
              {status?.last_password_changed_at ? (
                <div>
                  <dt className="text-[var(--text-muted)]">Last password change</dt>
                  <dd className="font-medium text-[var(--text)]">{new Date(status.last_password_changed_at).toLocaleString()}</dd>
                </div>
              ) : null}
              {status?.failed_attempt_count ? (
                <div>
                  <dt className="text-[var(--text-muted)]">Recent failed attempts</dt>
                  <dd className="font-medium text-[var(--text)]">{status.failed_attempt_count}</dd>
                </div>
              ) : null}
            </dl>
            {status?.enabled ? <Button disabled={working} onClick={lock} variant="outline">Lock Hatch</Button> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h2 className="font-semibold text-[var(--text)]">Change password</h2>
        {status?.configured_source === "env" ? (
          <div className="mt-3 rounded-[var(--radius-control)] bg-[var(--surface-2)] p-4 text-sm text-[var(--text-muted)]">
            <p>In-app password change is disabled.</p>
            <p className="mt-2">Change the environment value and restart Hatch to update it.</p>
          </div>
        ) : (
          <>
            <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
              Choose a new local app-lock password. Keep it somewhere safe because Hatch does not provide email recovery.
            </p>
            <form className="mt-5 grid gap-4" noValidate onSubmit={changePassword}>
              <PasswordField
                autoComplete="current-password"
                label="Current password"
                name="current_password"
                onChange={(value) => {
                  setCurrentPassword(value);
                  setFormError("");
                }}
                value={currentPassword}
              />
              <PasswordField
                autoComplete="new-password"
                describedBy={requirementsId}
                error={newPasswordFieldError}
                label="New password"
                name="new_password"
                onChange={(value) => {
                  setNewPassword(value);
                  setNewPasswordFieldError("");
                  setSuccess("");
                }}
                value={newPassword}
              />
              <PasswordField
                autoComplete="new-password"
                describedBy={requirementsId}
                error={confirmError}
                label="Confirm new password"
                name="confirm_password"
                onChange={(value) => {
                  setConfirm(value);
                  setConfirmError("");
                }}
                value={confirm}
              />
              <PasswordRequirementList
                confirmPassword={confirm}
                id={requirementsId}
                password={newPassword}
                policy={policy}
                showMatch
              />
              {formError ? <p className="text-sm text-[var(--danger)]" role="alert">{formError}</p> : null}
              {success ? <p className="text-sm text-[var(--success)]" role="status">{success}</p> : null}
              <Button disabled={working || !status?.enabled || !formValid} loading={working} type="submit">
                Change password
              </Button>
            </form>
          </>
        )}
      </SectionCard>

      <SectionCard>
        <div className="flex items-start gap-3">
          <Info aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" />
          <div>
            <h2 className="font-semibold text-[var(--text)]">Local recovery</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
              This password protects local workspace access. It is not an online account password, and there is no email reset.
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
              If you forget it, stop Hatch and run the local reset command. This removes the app-lock password and active sessions. Your jobs, profile, CVs, and application data are preserved.
              The next visit to the unlock page will ask you to create a new password.
            </p>
            <div className="mt-3 flex items-center gap-2 rounded-[var(--radius-control)] bg-[var(--surface-2)] px-3 py-2 font-mono text-sm text-[var(--text)]">
              <Terminal aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
              <code>bash scripts/reset-app-lock.sh</code>
            </div>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
