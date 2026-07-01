"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, LockKeyhole, Loader2 } from "lucide-react";
import { APP_LOCK_QUERY_KEY } from "@/components/AppLockGate";
import {
  changeAppLockPassword,
  getAppLockStatus,
  lockApp,
} from "@/lib/api";

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
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirm) {
      setMessage("New passwords do not match.");
      return;
    }
    setWorking(true);
    setMessage("");
    try {
      await changeAppLockPassword(currentPassword, newPassword);
      await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setMessage("Password changed. Other sessions were locked.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Password change failed.");
    } finally {
      setWorking(false);
    }
  };

  const lock = async () => {
    setWorking(true);
    await lockApp();
    queryClient.setQueryData(APP_LOCK_QUERY_KEY, { ...status, is_unlocked: false });
    router.replace("/unlock");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link href="/settings/profile" className="inline-flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
        <ArrowLeft className="h-4 w-4" /> Settings
      </Link>
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text)" }}>Security &amp; App Lock</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>Protect this single-user Hatch workspace.</p>
      </div>

      <section className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <LockKeyhole className="h-5 w-5" style={{ color: "var(--accent)" }} />
              <div>
                <p className="font-medium" style={{ color: "var(--text)" }}>
                  {status?.enabled ? "App lock enabled" : "App lock disabled"}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Source: {status?.configured_source ?? "none"} · Session: {status?.is_unlocked ? "unlocked" : "locked"}
                </p>
              </div>
            </div>
            {!status?.enabled ? (
              <p className="rounded-lg p-3 text-sm" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                App lock is disabled by environment configuration.
              </p>
            ) : null}
            {status?.last_unlocked_at ? <p className="text-sm" style={{ color: "var(--text-muted)" }}>Last unlocked: {new Date(status.last_unlocked_at).toLocaleString()}</p> : null}
            {status?.last_password_changed_at ? <p className="text-sm" style={{ color: "var(--text-muted)" }}>Last password change: {new Date(status.last_password_changed_at).toLocaleString()}</p> : null}
            {status?.enabled ? (
              <button onClick={lock} disabled={working} className="rounded-lg border px-4 py-2 text-sm" style={{ borderColor: "var(--border)", color: "var(--text)" }}>
                Lock Hatch
              </button>
            ) : null}
          </div>
        )}
      </section>

      <section className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <h2 className="font-semibold" style={{ color: "var(--text)" }}>Change password</h2>
        {status?.configured_source === "env" ? (
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>App lock password is controlled by environment configuration.</p>
        ) : (
          <form onSubmit={changePassword} className="mt-4 grid gap-4">
            {[
              ["Current password", currentPassword, setCurrentPassword],
              ["New password", newPassword, setNewPassword],
              ["Confirm new password", confirm, setConfirm],
            ].map(([label, value, setter]) => (
              <label key={label as string} className="text-sm font-medium">
                {label as string}
                <input
                  type="password"
                  required
                  minLength={8}
                  value={value as string}
                  onChange={(event) => (setter as (value: string) => void)(event.target.value)}
                  className="mt-2 w-full rounded-lg px-3 py-2 outline-none"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                />
              </label>
            ))}
            {message ? <p className="text-sm" style={{ color: "var(--text-muted)" }}>{message}</p> : null}
            <button disabled={working || !status?.enabled} className="rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50" style={{ background: "var(--accent)", color: "var(--on-accent)" }}>
              Change password
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
