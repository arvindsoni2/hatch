"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Camera, CheckCircle2, RefreshCw } from "lucide-react";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { SectionCard } from "@/components/ui/section-card";
import { Button } from "@/components/ui/button";
import { SettingsSaveBar } from "@/components/settings/SettingsSaveBar";
import { SettingsShell } from "@/components/settings/SettingsShell";
import {
  SettingsTagInput,
  type SettingsTagInputHandle,
} from "@/components/settings/SettingsTagInput";
import {
  fetchProfileSettings,
  firstLocation,
  getPathValue,
  saveProfileSettings,
  type ProfileSettingsData,
  updateFirstLocation,
  updatePathValue,
} from "@/lib/profileSettings";

const LOCALES = [
  { id: "uk", label: "United Kingdom" },
  { id: "in", label: "India" },
  { id: "ie", label: "Ireland" },
  { id: "ae", label: "UAE" },
];

export default function JobPreferencesPage() {
  const [profile, setProfile] = useState<ProfileSettingsData>({});
  const [lastSaved, setLastSaved] = useState<ProfileSettingsData>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const targetRolesRef = useRef<SettingsTagInputHandle>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchProfileSettings();
      setProfile(data);
      setLastSaved(structuredClone(data));
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load job preferences.");
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

  const update = (next: ProfileSettingsData) => {
    setProfile(next);
    setDirty(true);
    setMessage("");
  };

  const updatePath = (path: string[], value: unknown) => {
    update(updatePathValue(profile, path, value));
  };

  const validate = () => {
    const nextErrors: Record<string, string> = {};
    if (getPathValue<string[]>(profile, ["search", "target_roles"], []).length === 0) {
      nextErrors.targetRoles = "Add at least one target role.";
    }
    if (!String(firstLocation(profile).city ?? "").trim()) {
      nextErrors.city = "City is required.";
    }
    const minRate = getPathValue<number>(profile, ["compensation", "min_rate"], 0);
    const maxRate = getPathValue<number>(profile, ["compensation", "max_rate"], 0);
    if (minRate <= 0) nextErrors.minRate = "Minimum rate is required.";
    if (maxRate > 0 && maxRate < minRate) {
      nextErrors.maxRate = "Maximum rate must be greater than or equal to minimum rate.";
    }
    setFieldErrors(nextErrors);
    if (nextErrors.targetRoles) targetRolesRef.current?.focus();
    else if (nextErrors.city) document.getElementById("preferences-city")?.focus();
    else if (nextErrors.minRate) document.getElementById("preferences-min-rate")?.focus();
    else if (nextErrors.maxRate) document.getElementById("preferences-max-rate")?.focus();
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
      setMessage("Job preferences saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const location = firstLocation(profile);
  const boards = getPathValue<Array<Record<string, unknown>>>(profile, ["job_boards"], []);

  return (
    <SettingsShell
      activeHref="/settings/preferences"
      title="Job Preferences"
      description="Control the markets, roles, pay range, skills, scoring, and privacy signals Hatch uses for job discovery."
    >
      {loading ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5 text-sm text-[var(--text-muted)]">
          <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading job preferences…
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
          <SectionCard title="Market" description="Your market controls locale defaults and board selection.">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="preferences-locale" label="Job market">
                <select
                  className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
                  value={getPathValue<string>(profile, ["locale"], "uk")}
                  onChange={(event) => updatePath(["locale"], event.target.value)}
                >
                  {LOCALES.map((locale) => (
                    <option key={locale.id} value={locale.id}>{locale.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField id="preferences-contract-type" label="Employment type">
                <select
                  className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
                  value={getPathValue<string>(profile, ["search", "contract_type"], "contract")}
                  onChange={(event) => updatePath(["search", "contract_type"], event.target.value)}
                >
                  <option value="contract">Contract</option>
                  <option value="permanent">Permanent</option>
                  <option value="any">Either</option>
                </select>
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title="Target roles" description="Scout searches for these titles and close variants.">
            <div role="group" aria-label="Target roles">
              <SettingsTagInput
                invalid={Boolean(fieldErrors.targetRoles)}
                label="Add target role"
                onChange={(tags) => updatePath(["search", "target_roles"], tags)}
                placeholder="Delivery Lead"
                ref={targetRolesRef}
                tags={getPathValue<string[]>(profile, ["search", "target_roles"], [])}
              />
              {fieldErrors.targetRoles ? (
                <p className="mt-2 text-xs font-medium text-[var(--danger)]" role="alert">
                  {fieldErrors.targetRoles}
                </p>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="Location" description="Used by scrapers and scoring to rank nearby or remote-friendly roles.">
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField id="preferences-city" label="City" error={fieldErrors.city} required>
                <Input
                  value={String(location.city ?? "")}
                  onChange={(event) => update(updateFirstLocation(profile, { city: event.target.value }))}
                />
              </FormField>
              <FormField id="preferences-country" label="Country code">
                <Input
                  className="uppercase"
                  value={String(location.country ?? "")}
                  onChange={(event) => update(updateFirstLocation(profile, { country: event.target.value.toUpperCase() }))}
                />
              </FormField>
              <FormField id="preferences-remote" label="Remote preference">
                <select
                  className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
                  value={String(location.remote_preference ?? "any")}
                  onChange={(event) => update(updateFirstLocation(profile, { remote_preference: event.target.value }))}
                >
                  <option value="any">Any</option>
                  <option value="remote">Remote only</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-site only</option>
                </select>
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title="Job boards" description="Toggle which boards Scout scrapes for this market.">
            <div className="divide-y divide-[var(--border)]">
              {boards.length > 0 ? boards.map((board, index) => (
                <div className="flex items-center justify-between gap-3 py-3" key={`${String(board.name)}-${index}`}>
                  <div>
                    <p className="text-sm font-medium text-[var(--text)]">{String(board.name)}</p>
                    <p className="text-xs text-[var(--text-muted)]">{String(board.scraper || "scraper")}</p>
                  </div>
                  <Button
                    type="button"
                    variant={board.enabled ? "secondary" : "outline"}
                    onClick={() => {
                      const nextBoards = structuredClone(boards);
                      nextBoards[index] = { ...nextBoards[index], enabled: !nextBoards[index].enabled };
                      updatePath(["job_boards"], nextBoards);
                    }}
                  >
                    {board.enabled ? "Active" : "Disabled"}
                  </Button>
                </div>
              )) : (
                <p className="text-sm text-[var(--text-muted)]">No job boards are configured yet.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard title="Compensation" description="Used as a hard preference and a scoring signal.">
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField id="preferences-min-rate" label="Minimum rate" error={fieldErrors.minRate} required>
                <Input
                  min={0}
                  type="number"
                  value={String(getPathValue<number>(profile, ["compensation", "min_rate"], 0))}
                  onChange={(event) => updatePath(["compensation", "min_rate"], Number(event.target.value) || 0)}
                />
              </FormField>
              <FormField id="preferences-max-rate" label="Maximum rate" error={fieldErrors.maxRate}>
                <Input
                  min={0}
                  type="number"
                  value={String(getPathValue<number>(profile, ["compensation", "max_rate"], 0))}
                  onChange={(event) => updatePath(["compensation", "max_rate"], Number(event.target.value) || 0)}
                />
              </FormField>
              <FormField id="preferences-currency" label="Currency">
                <Input
                  value={getPathValue<string>(profile, ["compensation", "currency"], "")}
                  onChange={(event) => updatePath(["compensation", "currency"], event.target.value.toUpperCase())}
                />
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title="Skills" description="Primary skills carry the most weight in matching.">
            <div className="grid gap-4">
              <FormField id="preferences-primary-skills" label="Primary skills">
                <SettingsTagInput
                  label="Add primary skill"
                  onChange={(tags) => updatePath(["skills", "primary"], tags)}
                  placeholder="Agile delivery"
                  tags={getPathValue<string[]>(profile, ["skills", "primary"], [])}
                />
              </FormField>
              <FormField id="preferences-secondary-skills" label="Secondary skills">
                <SettingsTagInput
                  label="Add secondary skill"
                  onChange={(tags) => updatePath(["skills", "secondary"], tags)}
                  placeholder="Stakeholder management"
                  tags={getPathValue<string[]>(profile, ["skills", "secondary"], [])}
                />
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title="Scoring" description="Tune when a role is strong enough for shortlist and tailoring.">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="preferences-shortlist" label="Shortlist threshold">
                <Input
                  max={1}
                  min={0}
                  step={0.01}
                  type="number"
                  value={String(getPathValue<number>(profile, ["scoring", "shortlist_threshold"], 0.75))}
                  onChange={(event) => updatePath(["scoring", "shortlist_threshold"], Number(event.target.value) || 0)}
                />
              </FormField>
              <FormField id="preferences-skill-weight" label="Skill match weight">
                <Input
                  max={1}
                  min={0}
                  step={0.05}
                  type="number"
                  value={String(getPathValue<number>(profile, ["scoring", "weights", "skill_match"], 0.35))}
                  onChange={(event) => updatePath(["scoring", "weights", "skill_match"], Number(event.target.value) || 0)}
                />
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title="Coach privacy" description="Camera analysis is optional and processed locally before numeric summaries are saved.">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex gap-3">
                <Camera className="mt-0.5 h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
                <div>
                  <p className="font-medium text-[var(--text)]">Camera-based presence analysis</p>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">
                    Raw video is not uploaded. Hatch stores only local numeric summaries for coaching.
                  </p>
                </div>
              </div>
              <Button
                aria-checked={Boolean(getPathValue<boolean>(profile, ["perception", "face", "enabled"], false))}
                onClick={() => updatePath(["perception", "face", "enabled"], !getPathValue<boolean>(profile, ["perception", "face", "enabled"], false))}
                role="switch"
                type="button"
                variant="outline"
              >
                {getPathValue<boolean>(profile, ["perception", "face", "enabled"], false) ? "Enabled" : "Disabled"}
              </Button>
            </div>
            <Button
              className="mt-4"
              onClick={() => {
                localStorage.removeItem("face_consent_given");
                setMessage("Camera-analysis consent revoked.");
              }}
              type="button"
              variant="link"
            >
              Revoke saved camera-analysis consent
            </Button>
          </SectionCard>

          <SettingsSaveBar
            dirty={dirty}
            onDiscard={discard}
            onSave={() => void save()}
            saveLabel="Save job preferences"
            saving={saving}
          />
        </>
      ) : null}
    </SettingsShell>
  );
}
