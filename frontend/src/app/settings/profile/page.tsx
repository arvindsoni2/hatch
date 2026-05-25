"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, CheckCircle2, Save, RefreshCw } from "lucide-react";
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
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1 p-2 border rounded-md min-h-[40px]">
        {tags.map((t, i) => (
          <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => remove(i)}>
            {t} ×
          </Badge>
        ))}
        <input
          className="flex-1 min-w-[120px] outline-none text-sm bg-transparent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }}
          placeholder="Type and press Enter"
        />
      </div>
    </div>
  );
}

export default function ProfileSettingsPage() {
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchProfile();
      setProfile(data);
    } catch (e) {
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
      setTimeout(() => setSavedOk(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-8 text-slate-500">Loading profile…</div>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Profile Settings</h1>
          <p className="text-slate-500 text-sm mt-1">Edit your profile.yaml. Changes take effect on the next agent run.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}><RefreshCw className="w-4 h-4 mr-1" />Reload</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
            Save
          </Button>
        </div>
      </div>

      {savedOk && (
        <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
          <CheckCircle2 className="w-4 h-4" /> Profile saved successfully.
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-800 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* ── Identity ──────────────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">Identity</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Name</Label>
            <Input value={String(get(["candidate", "name"]))} onChange={(e) => update(["candidate", "name"], e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Title</Label>
            <Input value={String(get(["candidate", "title"]))} onChange={(e) => update(["candidate", "title"], e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Years experience</Label>
            <Input type="number" value={String(get(["candidate", "years_experience"], 0))} onChange={(e) => update(["candidate", "years_experience"], parseInt(e.target.value) || 0)} />
          </div>
          <div className="col-span-2 space-y-1">
            <Label>Summary</Label>
            <Textarea rows={2} value={String(get(["candidate", "summary"]))} onChange={(e) => update(["candidate", "summary"], e.target.value)} />
          </div>
        </CardContent>
      </Card>

      {/* ── Search ────────────────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">Target Roles</CardTitle><CardDescription className="text-xs">Job titles the Scout agent will search for.</CardDescription></CardHeader>
        <CardContent>
          <TagInput
            tags={(get(["search", "target_roles"], []) as string[])}
            onChange={(v) => update(["search", "target_roles"], v)}
          />
        </CardContent>
      </Card>

      {/* ── Compensation ──────────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">Compensation</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label>Min rate</Label>
            <Input type="number" value={String(get(["compensation", "min_rate"], 0))} onChange={(e) => update(["compensation", "min_rate"], parseFloat(e.target.value) || 0)} />
          </div>
          <div className="space-y-1">
            <Label>Max rate</Label>
            <Input type="number" value={String(get(["compensation", "max_rate"], 0))} onChange={(e) => update(["compensation", "max_rate"], parseFloat(e.target.value) || 0)} />
          </div>
          <div className="space-y-1">
            <Label>Currency</Label>
            <Input value={String(get(["compensation", "currency"], "GBP"))} onChange={(e) => update(["compensation", "currency"], e.target.value)} />
          </div>
        </CardContent>
      </Card>

      {/* ── Skills ────────────────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">Skills</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Primary skills (weighted 35% in scoring)</Label>
            <TagInput tags={(get(["skills", "primary"], []) as string[])} onChange={(v) => update(["skills", "primary"], v)} />
          </div>
          <div className="space-y-1">
            <Label>Secondary skills</Label>
            <TagInput tags={(get(["skills", "secondary"], []) as string[])} onChange={(v) => update(["skills", "secondary"], v)} />
          </div>
        </CardContent>
      </Card>

      {/* ── Scoring thresholds ─────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">Scoring</CardTitle><CardDescription className="text-xs">Jobs above the shortlist threshold get auto-tailored.</CardDescription></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Shortlist threshold (0.0–1.0)</Label>
            <Input type="number" min="0" max="1" step="0.01" value={String(get(["scoring", "shortlist_threshold"], 0.75))} onChange={(e) => update(["scoring", "shortlist_threshold"], parseFloat(e.target.value) || 0.75)} />
          </div>
          <div className="space-y-1">
            <Label>Skill match weight</Label>
            <Input type="number" min="0" max="1" step="0.05" value={String(get(["scoring", "weights", "skill_match"], 0.35))} onChange={(e) => update(["scoring", "weights", "skill_match"], parseFloat(e.target.value))} />
          </div>
        </CardContent>
      </Card>

      {/* ── LLM Provider ──────────────────────────────────────────────── */}
      <Card>
        <CardHeader><CardTitle className="text-base">LLM Provider</CardTitle><CardDescription className="text-xs">Changing provider takes effect on the next agent run. Set the API key in .env.</CardDescription></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Provider</Label>
            <select className="w-full border rounded-md p-2 text-sm" value={String(get(["llm", "provider"], "anthropic"))} onChange={(e) => update(["llm", "provider"], e.target.value)}>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="google">Google</option>
              <option value="ollama">Ollama (local)</option>
              <option value="azure">Azure OpenAI</option>
              <option value="aws_bedrock">AWS Bedrock</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label>API key env var</Label>
            <Input value={String(get(["llm", "api_key_env"], "ANTHROPIC_API_KEY"))} onChange={(e) => update(["llm", "api_key_env"], e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Triage model</Label>
            <Input value={String(get(["llm", "triage_model"], ""))} onChange={(e) => update(["llm", "triage_model"], e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Primary model</Label>
            <Input value={String(get(["llm", "primary_model"], ""))} onChange={(e) => update(["llm", "primary_model"], e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end pt-4">
        <Button onClick={handleSave} disabled={saving} className="gap-2">
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save Profile
        </Button>
      </div>
    </div>
  );
}
