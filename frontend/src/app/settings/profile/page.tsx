"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { ArrowLeft, Save, RefreshCw, AlertCircle, CheckCircle2, Camera, BrainCircuit } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { API_BASE, recomputeOutcomeLearning, resetOutcomeLearning } from "@/lib/api";
import { TemplateDefaultSetting } from "@/components/TemplateDefaultSetting";
import { ProfileSummaryCard } from "@/components/ProfileSummaryCard";

async function fetchProfile(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/v2/profile`);
  if (!res.ok) throw new Error("Failed to load profile");
  return res.json();
}

async function saveProfile(data: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v2/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Save failed");
  }
}

function TagInput({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [input, setInput] = useState("");
  const add = () => {
    if (input.trim()) {
      onChange([...tags, input.trim()]);
      setInput("");
    }
  };
  const remove = (i: number) => onChange(tags.filter((_, idx) => idx !== i));
  return (
    <div
      className="flex flex-wrap gap-1 p-2 rounded-md min-h-[40px]"
      style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
    >
      {tags.map((t, i) => (
        <Badge
          key={i}
          variant="secondary"
          className="cursor-pointer text-xs"
          style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "none" }}
          onClick={() => remove(i)}
        >
          {t} ×
        </Badge>
      ))}
      <input
        className="flex-1 min-w-[120px] outline-none text-sm bg-transparent"
        style={{ color: "var(--text)" }}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          }
        }}
        placeholder="Type and press Enter"
      />
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="space-y-4 rounded-xl p-4 sm:p-5"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

function Field({ label, children, alignLabel = false }: { label: string; children: React.ReactNode; alignLabel?: boolean }) {
  return (
    <div className="flex h-full flex-col gap-1.5">
      <Label
        className={alignLabel ? "flex min-h-10 items-end leading-5" : "leading-5"}
        style={{ color: "var(--text-dim)", fontSize: 12 }}
      >
        {label}
      </Label>
      {children}
    </div>
  );
}

const inputCls = "text-sm";
const inputStyle = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
} as const;

export default function ProfileSettingsPage() {
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [learningAction, setLearningAction] = useState<"recompute" | "reset" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchProfile();
      setProfile(data);
      setDirty(false);
    } catch {
      setError("Could not load profile.yaml");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = (path: string[], value: unknown) => {
    setProfile((prev) => {
      const next = structuredClone(prev);
      let cur: Record<string, unknown> = next;
      for (let i = 0; i < path.length - 1; i++) {
        if (!cur[path[i]]) cur[path[i]] = {};
        cur = cur[path[i]] as Record<string, unknown>;
      }
      cur[path[path.length - 1]] = value;
      return next;
    });
    setDirty(true);
  };

  const get = (path: string[], fallback: unknown = "") => {
    let cur: unknown = profile;
    for (const key of path) {
      if (cur == null || typeof cur !== "object") return fallback;
      cur = (cur as Record<string, unknown>)[key];
    }
    return cur ?? fallback;
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSavedOk(false);
    try {
      await saveProfile(profile);
      setSavedOk(true);
      setDirty(false);
      setTimeout(() => setSavedOk(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-8 text-sm" style={{ color: "var(--text-muted)" }}>
        <RefreshCw className="w-4 h-4 animate-spin" /> Loading profile…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Back + header */}
      <div>
        <Link
          href="/today"
          className="inline-flex items-center gap-1.5 text-sm mb-4"
          style={{ color: "var(--text-dim)" }}
        >
          <ArrowLeft size={14} /> Back to Today
        </Link>
        <h1
          className="text-[28px] font-semibold"
          style={{ color: "var(--text)", letterSpacing: "-0.025em" }}
        >
          Profile Settings
        </h1>
        <p className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }}>
          Edit your profile.yaml. Changes take effect on the next agent run.
        </p>
      </div>

      {/* Feedback banners */}
      {savedOk && (
        <div
          className="flex items-center gap-2 p-3 rounded-lg text-sm"
          style={{ background: "var(--success-soft)", color: "var(--success)" }}
        >
          <CheckCircle2 className="w-4 h-4" /> Profile saved successfully.
        </div>
      )}
      {error && (
        <div
          className="flex items-center gap-2 p-3 rounded-lg text-sm"
          style={{ background: "var(--danger-soft)", border: "1px solid var(--danger)", color: "var(--danger)" }}
        >
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      <TemplateDefaultSetting />
      <ProfileSummaryCard />

      {/* Identity */}
      <SectionCard title="Identity">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["candidate", "name"]))}
              onChange={(e) => update(["candidate", "name"], e.target.value)}
            />
          </Field>
          <Field label="Title">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["candidate", "title"]))}
              onChange={(e) => update(["candidate", "title"], e.target.value)}
            />
          </Field>
          <Field label="Years experience">
            <Input
              className={inputCls}
              style={inputStyle}
              type="number"
              value={String(get(["candidate", "years_experience"], 0))}
              onChange={(e) => update(["candidate", "years_experience"], parseInt(e.target.value) || 0)}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Summary">
              <Textarea
                className={inputCls}
                style={inputStyle}
                rows={2}
                value={String(get(["candidate", "summary"]))}
                onChange={(e) => update(["candidate", "summary"], e.target.value)}
              />
            </Field>
          </div>
        </div>
      </SectionCard>

      {/* Locale */}
      <SectionCard title="Locale">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Controls job boards, currency format, and compliance fields. Switching does not auto-replace your job boards list.
        </p>
        <div className="flex flex-wrap gap-2">
          {[
            { id: "uk", flag: "🇬🇧", label: "UK" },
            { id: "in", flag: "🇮🇳", label: "India" },
            { id: "ie", flag: "🇮🇪", label: "Ireland" },
            { id: "ae", flag: "🇦🇪", label: "UAE" },
          ].map(({ id, flag, label }) => {
            const active = String(get(["locale"], "uk")) === id;
            return (
              <button
                key={id}
                onClick={() => update(["locale"], id)}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{
                  border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: active ? "var(--accent-soft)" : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text-dim)",
                }}
              >
                {flag} {label}
              </button>
            );
          })}
        </div>
      </SectionCard>

      {/* Location */}
      <SectionCard title="Location">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Primary location used by scrapers for search.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="City">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String((get(["search", "locations"], []) as Array<Record<string, unknown>>)[0]?.city ?? "")}
              onChange={(e) => {
                const locs = structuredClone((get(["search", "locations"], [{ city: "", country: "", remote_preference: "any" }]) as Array<Record<string, unknown>>));
                if (!locs[0]) locs[0] = {};
                locs[0].city = e.target.value;
                update(["search", "locations"], locs);
              }}
              placeholder="City…"
            />
          </Field>
          <Field label="Country code">
            <Input
              className={`${inputCls} uppercase`}
              style={inputStyle}
              value={String((get(["search", "locations"], []) as Array<Record<string, unknown>>)[0]?.country ?? "")}
              onChange={(e) => {
                const locs = structuredClone((get(["search", "locations"], [{ city: "", country: "", remote_preference: "any" }]) as Array<Record<string, unknown>>));
                if (!locs[0]) locs[0] = {};
                locs[0].country = e.target.value.toUpperCase();
                update(["search", "locations"], locs);
              }}
              placeholder="GB, IN, IE, AE…"
            />
          </Field>
          <Field label="Remote preference">
            <select
              className="w-full rounded-md p-2 text-sm"
              style={inputStyle}
              value={String((get(["search", "locations"], []) as Array<Record<string, unknown>>)[0]?.remote_preference ?? "any")}
              onChange={(e) => {
                const locs = structuredClone((get(["search", "locations"], [{ city: "", country: "", remote_preference: "any" }]) as Array<Record<string, unknown>>));
                if (!locs[0]) locs[0] = {};
                locs[0].remote_preference = e.target.value;
                update(["search", "locations"], locs);
              }}
            >
              <option value="any">Any</option>
              <option value="remote">Remote only</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site only</option>
            </select>
          </Field>
        </div>
      </SectionCard>

      {/* Target Roles */}
      <SectionCard title="Target Roles">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Job titles the Scout agent will search for.</p>
        <TagInput
          tags={(get(["search", "target_roles"], []) as string[])}
          onChange={(v) => update(["search", "target_roles"], v)}
        />
      </SectionCard>

      {/* Job Boards */}
      <SectionCard title="Job Boards">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Toggle which boards the Scout agent scrapes.</p>
        <div className="space-y-1 divide-y" style={{ borderColor: "var(--border)" }}>
          {((get(["job_boards"], []) as Array<Record<string, unknown>>)).map((board, idx) => (
            <div key={String(board.name)} className="flex items-center justify-between py-2.5">
              <div className="flex items-center gap-2.5">
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ background: board.enabled ? "var(--success)" : "var(--border)" }}
                />
                <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{String(board.name)}</span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>({String(board.scraper)})</span>
              </div>
              <button
                onClick={() => {
                  const boards = structuredClone(get(["job_boards"], []) as Array<Record<string, unknown>>);
                  boards[idx] = { ...boards[idx], enabled: !boards[idx].enabled };
                  update(["job_boards"], boards);
                }}
                className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
                style={{
                  background: board.enabled ? "var(--success-soft)" : "var(--surface-2)",
                  border: `1px solid ${board.enabled ? "var(--success)" : "var(--border)"}`,
                  color: board.enabled ? "var(--success)" : "var(--text-dim)",
                }}
              >
                {board.enabled ? "Enabled" : "Disabled"}
              </button>
            </div>
          ))}
          {(get(["job_boards"], []) as unknown[]).length === 0 && (
            <p className="text-sm py-2" style={{ color: "var(--text-muted)" }}>
              No boards configured. Save after adding boards manually or via locale.
            </p>
          )}
        </div>
      </SectionCard>

      {/* Compensation */}
      <SectionCard title="Compensation">
        <div className="grid grid-cols-3 gap-4">
          <Field label="Min rate">
            <Input
              className={inputCls}
              style={inputStyle}
              type="number"
              value={String(get(["compensation", "min_rate"], 0))}
              onChange={(e) => update(["compensation", "min_rate"], parseFloat(e.target.value) || 0)}
            />
          </Field>
          <Field label="Max rate">
            <Input
              className={inputCls}
              style={inputStyle}
              type="number"
              value={String(get(["compensation", "max_rate"], 0))}
              onChange={(e) => update(["compensation", "max_rate"], parseFloat(e.target.value) || 0)}
            />
          </Field>
          <Field label="Currency">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["compensation", "currency"], ""))}
              onChange={(e) => update(["compensation", "currency"], e.target.value)}
              placeholder="GBP, INR, EUR, AED…"
            />
          </Field>
        </div>
      </SectionCard>

      {/* Skills */}
      <SectionCard title="Skills">
        <Field label="Primary skills (weighted 35% in scoring)">
          <TagInput
            tags={(get(["skills", "primary"], []) as string[])}
            onChange={(v) => update(["skills", "primary"], v)}
          />
        </Field>
        <Field label="Secondary skills">
          <TagInput
            tags={(get(["skills", "secondary"], []) as string[])}
            onChange={(v) => update(["skills", "secondary"], v)}
          />
        </Field>
      </SectionCard>

      {/* Scoring */}
      <SectionCard title="Scoring">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Jobs above the shortlist threshold get auto-tailored.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Shortlist threshold (0.0–1.0)">
            <Input
              className={inputCls}
              style={inputStyle}
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={String(get(["scoring", "shortlist_threshold"], 0.75))}
              onChange={(e) => update(["scoring", "shortlist_threshold"], parseFloat(e.target.value) || 0.75)}
            />
          </Field>
          <Field label="Skill match weight">
            <Input
              className={inputCls}
              style={inputStyle}
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={String(get(["scoring", "weights", "skill_match"], 0.35))}
              onChange={(e) => update(["scoring", "weights", "skill_match"], parseFloat(e.target.value))}
            />
          </Field>
        </div>
      </SectionCard>

      {/* LLM Provider */}
      <SectionCard title="Coach & Privacy">
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text)" }}>
              <Camera className="h-4 w-4" /> Camera-based presence analysis
            </div>
            <p className="mt-1 max-w-xl text-xs" style={{ color: "var(--text-muted)" }}>
              Makes Video mode available in Coach. MediaPipe processes the webcam locally and uploads only numeric summaries for approximate camera attention and head stability. Raw video is not uploaded.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(get(["perception", "face", "enabled"], false))}
            onClick={() => update(["perception", "face", "enabled"], !Boolean(get(["perception", "face", "enabled"], false)))}
            className="h-11 shrink-0 rounded-full px-4 text-xs font-medium"
            style={{
              background: Boolean(get(["perception", "face", "enabled"], false)) ? "var(--success-soft)" : "var(--surface-2)",
              border: `1px solid ${Boolean(get(["perception", "face", "enabled"], false)) ? "var(--success)" : "var(--border)"}`,
              color: Boolean(get(["perception", "face", "enabled"], false)) ? "var(--success)" : "var(--text-dim)",
            }}
          >
            {Boolean(get(["perception", "face", "enabled"], false)) ? "Enabled" : "Disabled"}
          </button>
        </div>
        <button
          type="button"
          className="text-xs underline"
          style={{ color: "var(--text-dim)" }}
          onClick={() => {
            localStorage.removeItem("face_consent_given");
            setSavedOk(true);
            setTimeout(() => setSavedOk(false), 3000);
          }}
        >
          Revoke saved camera-analysis consent
        </button>
      </SectionCard>

      <SectionCard title="Outcome Learning">
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text)" }}>
              <BrainCircuit className="h-4 w-4" /> Learn from application outcomes
            </div>
            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              Adds a bounded opportunity adjustment to fit scores using only your resolved application history. Calculation is local, deterministic, and never uses protected personal data or an LLM.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(get(["outcome_learning", "enabled"], true))}
            onClick={() => update(["outcome_learning", "enabled"], !Boolean(get(["outcome_learning", "enabled"], true)))}
            className="h-11 shrink-0 rounded-full px-4 text-xs font-medium"
            style={{ background: Boolean(get(["outcome_learning", "enabled"], true)) ? "var(--success-soft)" : "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
          >
            {Boolean(get(["outcome_learning", "enabled"], true)) ? "Enabled" : "Disabled"}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field alignLabel label="Minimum resolved applications"><Input className={inputCls} style={inputStyle} type="number" min="5" value={String(get(["outcome_learning", "minimum_total_applications"], 15))} onChange={(e) => update(["outcome_learning", "minimum_total_applications"], Number(e.target.value))} /></Field>
          <Field alignLabel label="No-response window (days)"><Input className={inputCls} style={inputStyle} type="number" min="14" max="120" value={String(get(["outcome_learning", "no_response_after_days"], 35))} onChange={(e) => update(["outcome_learning", "no_response_after_days"], Number(e.target.value))} /></Field>
          <Field alignLabel label="Recency half-life (days)"><Input className={inputCls} style={inputStyle} type="number" min="30" max="730" value={String(get(["outcome_learning", "recency_half_life_days"], 120))} onChange={(e) => update(["outcome_learning", "recency_half_life_days"], Number(e.target.value))} /></Field>
          <Field alignLabel label="Maximum adjustment"><Input className={inputCls} style={inputStyle} type="number" min="0" max="0.2" step="0.01" value={String(get(["outcome_learning", "maximum_score_adjustment"], 0.1))} onChange={(e) => update(["outcome_learning", "maximum_score_adjustment"], Number(e.target.value))} /></Field>
        </div>
        <Field label="Learning signals">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {["source", "role_family", "seniority", "working_pattern", "employment_type", "freshness"].map((signal) => {
              const enabled = (get(["outcome_learning", "enabled_signals"], []) as string[]).includes(signal);
              return <label key={signal} className="flex min-h-11 items-center gap-2 rounded-md px-3 py-2 text-xs" style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}><input type="checkbox" checked={enabled} onChange={() => { const current = get(["outcome_learning", "enabled_signals"], []) as string[]; update(["outcome_learning", "enabled_signals"], enabled ? current.filter((item) => item !== signal) : [...current, signal]); }} />{signal.replaceAll("_", " ")}</label>;
            })}
          </div>
        </Field>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button type="button" variant="outline" disabled={learningAction !== null || dirty} onClick={async () => { setLearningAction("recompute"); setError(""); try { await recomputeOutcomeLearning(); setSavedOk(true); } catch (e) { setError(e instanceof Error ? e.message : "Recompute failed"); } finally { setLearningAction(null); } }}>{learningAction === "recompute" ? "Recomputing..." : "Recompute now"}</Button>
          <Button type="button" variant="outline" disabled={learningAction !== null || dirty} onClick={async () => { if (!window.confirm("This starts a new learning window. It does not delete applications or documents.")) return; setLearningAction("reset"); setError(""); try { const result = await resetOutcomeLearning(); update(["outcome_learning", "learning_since"], result.learning_since); setDirty(false); setSavedOk(true); } catch (e) { setError(e instanceof Error ? e.message : "Reset failed"); } finally { setLearningAction(null); } }}>{learningAction === "reset" ? "Resetting..." : "Reset learning window"}</Button>
        </div>
      </SectionCard>

      <SectionCard title="LLM Provider">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Changing provider takes effect on the next agent run. Set the API key in .env or via Settings → AI Provider.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Provider">
            <select
              className="w-full rounded-md p-2 text-sm"
              style={inputStyle}
              value={String(get(["llm", "provider"], "anthropic"))}
              onChange={(e) => update(["llm", "provider"], e.target.value)}
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="google_genai">Google Gemini</option>
              <option value="ollama">Ollama (local, free)</option>
              <option value="azure_openai">Azure OpenAI</option>
              <option value="aws_bedrock">AWS Bedrock</option>
            </select>
          </Field>
          <Field label="API key env var">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["llm", "api_key_env"], "ANTHROPIC_API_KEY"))}
              onChange={(e) => update(["llm", "api_key_env"], e.target.value)}
            />
          </Field>
          <Field label="Triage model">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["llm", "triage_model"], ""))}
              onChange={(e) => update(["llm", "triage_model"], e.target.value)}
            />
          </Field>
          <Field label="Primary model">
            <Input
              className={inputCls}
              style={inputStyle}
              value={String(get(["llm", "primary_model"], ""))}
              onChange={(e) => update(["llm", "primary_model"], e.target.value)}
            />
          </Field>
        </div>
      </SectionCard>

      {/* Single save action — sticky bar when dirty */}
      <div
        className={`sticky bottom-0 flex items-center justify-between rounded-xl px-4 py-3 transition-all ${dirty ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-dim)" }}>
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: "var(--warning)" }}
          />
          Unsaved changes
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="text-sm px-3 py-1.5 rounded-lg transition-colors"
            style={{ color: "var(--text-dim)", background: "var(--surface-2)", border: "1px solid var(--border)" }}
          >
            Discard
          </button>
          <Button
            onClick={handleSave}
            disabled={saving}
            style={{ background: "var(--accent)", color: "var(--on-accent)", minHeight: 36 }}
          >
            {saving ? <RefreshCw className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
            Save changes
          </Button>
        </div>
      </div>
    </div>
  );
}
