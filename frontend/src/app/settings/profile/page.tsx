"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SectionCard } from "@/components/ui/section-card";
import { SettingsSaveBar } from "@/components/settings/SettingsSaveBar";
import { SettingsShell } from "@/components/settings/SettingsShell";
import {
  fetchProfileSettings,
  getPathValue,
  saveProfileSettings,
  type ProfileSettingsData,
  updatePathValue,
} from "@/lib/profileSettings";

export default function ProfileSettingsPage() {
  const [profile, setProfile] = useState<ProfileSettingsData>({});
  const [lastSaved, setLastSaved] = useState<ProfileSettingsData>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchProfileSettings();
      setProfile(data);
      setLastSaved(structuredClone(data));
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load profile.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const update = (path: string[], value: unknown) => {
    setProfile((current) => updatePathValue(current, path, value));
    setDirty(true);
    setMessage("");
  };

  const validate = () => {
    const nextErrors: Record<string, string> = {};
    if (!getPathValue<string>(profile, ["candidate", "name"], "").trim()) {
      nextErrors.name = "Full name is required.";
    }
    if (!getPathValue<string>(profile, ["candidate", "title"], "").trim()) {
      nextErrors.title = "Current or target title is required.";
    }
    setFieldErrors(nextErrors);
    if (nextErrors.name) document.getElementById("profile-name")?.focus();
    else if (nextErrors.title) document.getElementById("profile-title")?.focus();
    return Object.keys(nextErrors).length === 0;
  };

  const discard = () => {
    setProfile(structuredClone(lastSaved));
    setDirty(false);
    setFieldErrors({});
    setMessage("");
    setError("");
  };

  const save = async () => {
    if (!validate()) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveProfileSettings(profile);
      setLastSaved(structuredClone(profile));
      setDirty(false);
      setMessage("Profile saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsShell
      activeHref="/settings/profile"
      title="Profile"
      description="Manage the identity details Hatch uses in CVs, cover letters, and interview preparation."
    >
      {loading ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5 text-sm text-[var(--text-muted)]">
          <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading profile…
        </div>
      ) : null}

      {message && !dirty ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-control)] bg-[var(--success-soft)] p-3 text-sm text-[var(--success)]" role="status">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-control)] border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]" role="alert">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {!loading ? (
        <>
          <SectionCard
            title="Identity"
            description="These fields are written into generated documents and used to calibrate role seniority."
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField id="profile-name" label="Full name" error={fieldErrors.name} required>
                <Input
                  value={getPathValue<string>(profile, ["candidate", "name"], "")}
                  onChange={(event) => update(["candidate", "name"], event.target.value)}
                />
              </FormField>
              <FormField id="profile-title" label="Current or target title" error={fieldErrors.title} required>
                <Input
                  value={getPathValue<string>(profile, ["candidate", "title"], "")}
                  onChange={(event) => update(["candidate", "title"], event.target.value)}
                />
              </FormField>
              <FormField
                id="profile-years"
                label="Years of experience"
                description="Used to tune seniority and interview coaching."
              >
                <Input
                  min={0}
                  type="number"
                  value={String(getPathValue<number>(profile, ["candidate", "years_experience"], 0))}
                  onChange={(event) => update(["candidate", "years_experience"], Number(event.target.value) || 0)}
                />
              </FormField>
              <div className="sm:col-span-2">
                <FormField
                  id="profile-summary"
                  label="Professional summary"
                  description="Use two or three sentences in your voice. Hatch adapts this for each application."
                >
                  <Textarea
                    className="min-h-[112px] border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)] placeholder:text-[var(--text-muted)]"
                    value={getPathValue<string>(profile, ["candidate", "summary"], "")}
                    onChange={(event) => update(["candidate", "summary"], event.target.value)}
                  />
                </FormField>
              </div>
            </div>
          </SectionCard>

          <SettingsSaveBar
            dirty={dirty}
            onDiscard={discard}
            onSave={() => void save()}
            saveLabel="Save profile"
            saving={saving}
          />
        </>
      ) : null}
    </SettingsShell>
  );
}
