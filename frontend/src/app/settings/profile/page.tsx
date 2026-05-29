"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { ArrowLeft, Save, RefreshCw, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { API_BASE } from "@/lib/api";

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
      className="rounded-xl p-5 space-y-4"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label style={{ color: "var(--text-dim)", fontSize: 12 }}>{label}</Label>
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
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Back + header */}
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm mb-4"
          style={{ color: "var(--text-dim)" }}
        >
          <ArrowLeft size={14} /> Back to Home
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

      {/* Identity */}
      <SectionCard title="Identity">
        <div className="grid grid-cols-2 gap-4">
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
          <div className="col-span-2">
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
        <div className="grid grid-cols-2 gap-4">
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
        <div className="grid grid-cols-2 gap-4">
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
      <SectionCard title="LLM Provider">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Changing provider takes effect on the next agent run. Set the API key in .env or via Settings → AI Provider.
        </p>
        <div className="grid grid-cols-2 gap-4">
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
