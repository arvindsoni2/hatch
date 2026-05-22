"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, ChevronRight, ChevronLeft, User, Search, Briefcase, Star, Cpu } from "lucide-react";

const TOTAL_STEPS = 6;

const LLM_PROVIDERS = [
  { id: "anthropic", label: "Anthropic (Claude)", keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001", primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai", label: "OpenAI (GPT)", keyEnv: "OPENAI_API_KEY", triageDefault: "gpt-4o-mini", primaryDefault: "gpt-4o" },
  { id: "google", label: "Google (Gemini)", keyEnv: "GOOGLE_API_KEY", triageDefault: "gemini-2.0-flash", primaryDefault: "gemini-2.5-pro" },
  { id: "ollama", label: "Ollama (local — free)", keyEnv: "", triageDefault: "gemma3:4b", primaryDefault: "qwen3:14b" },
];

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
              i + 1 < current
                ? "bg-green-500 text-white"
                : i + 1 === current
                ? "bg-blue-600 text-white"
                : "bg-slate-200 text-slate-500"
            }`}
          >
            {i + 1 < current ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
          </div>
          {i < total - 1 && (
            <div className={`w-8 h-0.5 mx-1 ${i + 1 < current ? "bg-green-500" : "bg-slate-200"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

function TagInput({
  label,
  tags,
  onAdd,
  onRemove,
  placeholder,
}: {
  label: string;
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (i: number) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === "Enter" || e.key === ",") && input.trim()) {
      e.preventDefault();
      onAdd(input.trim());
      setInput("");
    }
  };
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-2 p-2 border rounded-md min-h-[42px]">
        {tags.map((t, i) => (
          <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => onRemove(i)}>
            {t} ×
          </Badge>
        ))}
        <input
          className="flex-1 min-w-[120px] outline-none text-sm bg-transparent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Type and press Enter"}
        />
      </div>
      <p className="text-xs text-slate-500">Press Enter or comma to add each item</p>
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // ── Form state ───────────────────────────────────────────────────────────
  const [candidate, setCandidate] = useState({ name: "", title: "", years_experience: 0, summary: "" });
  const [search, setSearch] = useState({ target_roles: [] as string[], contract_type: "any" });
  const [locations, setLocations] = useState([{ city: "", country: "", radius_miles: 30, remote_preference: "any" }]);
  const [compensation, setCompensation] = useState({ min_rate: 0, max_rate: 0, rate_type: "daily", currency: "GBP", ir35_preference: "any" });
  const [skills, setSkills] = useState({ primary: [] as string[], secondary: [] as string[], certifications: [] as string[] });
  const [domains, setDomains] = useState({ preferred: [] as string[], excluded: [] as string[] });
  const [llm, setLlm] = useState({ provider: "anthropic", triage_model: "claude-haiku-4-5-20251001", primary_model: "claude-sonnet-4-20250514", api_key_env: "ANTHROPIC_API_KEY", base_url: null as string | null, temperature: 0.3, max_retries: 3, track_costs: true, monthly_budget: 15, currency: "GBP" });
  const [scoring, setScoring] = useState({ weights: { skill_match: 0.35, experience_match: 0.30, rate_match: 0.20, location_match: 0.15 }, shortlist_threshold: 0.75 });

  const handleProviderChange = (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (p) {
      setLlm((prev) => ({ ...prev, provider: providerId, triage_model: p.triageDefault, primary_model: p.primaryDefault, api_key_env: p.keyEnv }));
    }
  };

  const buildProfile = () => ({
    candidate,
    search: { ...search, locations },
    compensation,
    skills,
    domains,
    proof_points: [],
    master_cv_path: "./data/master_cv.json",
    job_boards: [],
    scoring,
    llm,
    preferences: { scrape_interval_hours: 4, max_tailor_batch: 5, follow_up_days: [5, 10, 15], locale: "en-GB" },
  });

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/v2/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildProfile()),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to save profile");
      }
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold text-slate-900">Welcome to JobPilot v2</h1>
          <p className="mt-2 text-slate-500">Set up your profile to start your autonomous job search.</p>
        </div>

        <StepIndicator current={step} total={TOTAL_STEPS} />

        <Card>
          <CardContent className="pt-6">
            {/* ── Step 1: Identity ─────────────────────────────────────────── */}
            {step === 1 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><User className="w-5 h-5 text-blue-600" /><CardTitle>Who are you?</CardTitle></div>
                  <CardDescription>Basic identity used in CV and cover letter generation.</CardDescription>
                </CardHeader>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Full name *</Label>
                    <Input value={candidate.name} onChange={(e) => setCandidate({ ...candidate, name: e.target.value })} placeholder="Alex Johnson" />
                  </div>
                  <div className="space-y-1">
                    <Label>Current / target title *</Label>
                    <Input value={candidate.title} onChange={(e) => setCandidate({ ...candidate, title: e.target.value })} placeholder="Senior Delivery Lead" />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label>Years of experience</Label>
                  <Input type="number" value={candidate.years_experience} onChange={(e) => setCandidate({ ...candidate, years_experience: parseInt(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1">
                  <Label>Professional summary (2-3 sentences)</Label>
                  <Textarea rows={3} value={candidate.summary} onChange={(e) => setCandidate({ ...candidate, summary: e.target.value })} placeholder="Senior technology professional with 15 years..." />
                </div>
              </div>
            )}

            {/* ── Step 2: Search parameters ─────────────────────────────────── */}
            {step === 2 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Search className="w-5 h-5 text-blue-600" /><CardTitle>What are you looking for?</CardTitle></div>
                  <CardDescription>Target roles and location preferences.</CardDescription>
                </CardHeader>
                <TagInput label="Target job titles *" tags={search.target_roles} onAdd={(t) => setSearch({ ...search, target_roles: [...search.target_roles, t] })} onRemove={(i) => setSearch({ ...search, target_roles: search.target_roles.filter((_, idx) => idx !== i) })} placeholder="Delivery Lead, Product Manager..." />
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label>City *</Label>
                    <Input value={locations[0].city} onChange={(e) => setLocations([{ ...locations[0], city: e.target.value }])} placeholder="Newcastle" />
                  </div>
                  <div className="space-y-1">
                    <Label>Country *</Label>
                    <Input value={locations[0].country} onChange={(e) => setLocations([{ ...locations[0], country: e.target.value }])} placeholder="UK" />
                  </div>
                  <div className="space-y-1">
                    <Label>Remote preference</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={locations[0].remote_preference} onChange={(e) => setLocations([{ ...locations[0], remote_preference: e.target.value }])}>
                      <option value="any">Any</option>
                      <option value="remote">Remote</option>
                      <option value="hybrid">Hybrid</option>
                      <option value="onsite">On-site</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Contract type</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={search.contract_type} onChange={(e) => setSearch({ ...search, contract_type: e.target.value })}>
                      <option value="any">Any</option>
                      <option value="contract">Contract</option>
                      <option value="permanent">Permanent</option>
                      <option value="freelance">Freelance</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 3: Compensation ─────────────────────────────────────── */}
            {step === 3 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Briefcase className="w-5 h-5 text-blue-600" /><CardTitle>Compensation range</CardTitle></div>
                  <CardDescription>Used to score rate match. Rates outside your range score lower.</CardDescription>
                </CardHeader>
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-1">
                    <Label>Min rate</Label>
                    <Input type="number" value={compensation.min_rate} onChange={(e) => setCompensation({ ...compensation, min_rate: parseFloat(e.target.value) || 0 })} />
                  </div>
                  <div className="space-y-1">
                    <Label>Max rate</Label>
                    <Input type="number" value={compensation.max_rate} onChange={(e) => setCompensation({ ...compensation, max_rate: parseFloat(e.target.value) || 0 })} />
                  </div>
                  <div className="space-y-1">
                    <Label>Rate type</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={compensation.rate_type} onChange={(e) => setCompensation({ ...compensation, rate_type: e.target.value })}>
                      <option value="daily">Daily</option>
                      <option value="hourly">Hourly</option>
                      <option value="annual">Annual</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Currency</Label>
                    <Input value={compensation.currency} onChange={(e) => setCompensation({ ...compensation, currency: e.target.value })} placeholder="GBP" />
                  </div>
                  <div className="space-y-1">
                    <Label>IR35 preference (UK contracts)</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={compensation.ir35_preference} onChange={(e) => setCompensation({ ...compensation, ir35_preference: e.target.value })}>
                      <option value="any">Any</option>
                      <option value="outside">Outside IR35</option>
                      <option value="inside">Inside IR35</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 4: Skills & domains ──────────────────────────────────── */}
            {step === 4 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Star className="w-5 h-5 text-blue-600" /><CardTitle>Skills & domains</CardTitle></div>
                  <CardDescription>Primary skills are weighted 35% in scoring. Add your strongest first.</CardDescription>
                </CardHeader>
                <TagInput label="Primary skills *" tags={skills.primary} onAdd={(t) => setSkills({ ...skills, primary: [...skills.primary, t] })} onRemove={(i) => setSkills({ ...skills, primary: skills.primary.filter((_, idx) => idx !== i) })} placeholder="Agile delivery, AWS, Stakeholder management..." />
                <TagInput label="Secondary skills" tags={skills.secondary} onAdd={(t) => setSkills({ ...skills, secondary: [...skills.secondary, t] })} onRemove={(i) => setSkills({ ...skills, secondary: skills.secondary.filter((_, idx) => idx !== i) })} placeholder="Python, Terraform..." />
                <TagInput label="Preferred domains" tags={domains.preferred} onAdd={(t) => setDomains({ ...domains, preferred: [...domains.preferred, t] })} onRemove={(i) => setDomains({ ...domains, preferred: domains.preferred.filter((_, idx) => idx !== i) })} placeholder="Energy, FinTech, Public Sector..." />
                <TagInput label="Excluded domains" tags={domains.excluded} onAdd={(t) => setDomains({ ...domains, excluded: [...domains.excluded, t] })} onRemove={(i) => setDomains({ ...domains, excluded: domains.excluded.filter((_, idx) => idx !== i) })} placeholder="Gambling, Defense..." />
              </div>
            )}

            {/* ── Step 5: LLM provider ─────────────────────────────────────── */}
            {step === 5 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Cpu className="w-5 h-5 text-blue-600" /><CardTitle>AI provider</CardTitle></div>
                  <CardDescription>JobPilot uses LangChain so you can swap providers any time in profile.yaml.</CardDescription>
                </CardHeader>
                <div className="grid grid-cols-2 gap-3">
                  {LLM_PROVIDERS.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleProviderChange(p.id)}
                      className={`p-4 border-2 rounded-lg text-left transition-colors ${llm.provider === p.id ? "border-blue-600 bg-blue-50" : "border-slate-200 hover:border-slate-300"}`}
                    >
                      <div className="font-medium text-sm">{p.label}</div>
                      {p.id === "ollama" && <div className="text-xs text-green-600 mt-1">No API key needed</div>}
                    </button>
                  ))}
                </div>
                {llm.provider !== "ollama" && (
                  <div className="space-y-2 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm font-medium text-amber-800">API key setup</p>
                    <p className="text-xs text-amber-700">
                      Set <code className="bg-amber-100 px-1 rounded">{llm.api_key_env}</code> in your <code className="bg-amber-100 px-1 rounded">.env</code> file.
                      Never put your API key in profile.yaml — it's stored securely in .env only.
                    </p>
                  </div>
                )}
                {llm.provider === "ollama" && (
                  <div className="space-y-1">
                    <Label>Ollama base URL</Label>
                    <Input value={llm.base_url || ""} onChange={(e) => setLlm({ ...llm, base_url: e.target.value || null })} placeholder="http://localhost:11434" />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Triage model (fast/cheap)</Label>
                    <Input value={llm.triage_model} onChange={(e) => setLlm({ ...llm, triage_model: e.target.value })} />
                  </div>
                  <div className="space-y-1">
                    <Label>Primary model (strong)</Label>
                    <Input value={llm.primary_model} onChange={(e) => setLlm({ ...llm, primary_model: e.target.value })} />
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 6: Review & launch ───────────────────────────────────── */}
            {step === 6 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <CardTitle>Ready to launch</CardTitle>
                  <CardDescription>Review your setup and save profile to start the autonomous pipeline.</CardDescription>
                </CardHeader>
                <div className="space-y-3 text-sm">
                  {[
                    { label: "Name", value: candidate.name || "—" },
                    { label: "Title", value: candidate.title || "—" },
                    { label: "Target roles", value: search.target_roles.join(", ") || "—" },
                    { label: "Location", value: locations[0].city ? `${locations[0].city}, ${locations[0].country} (${locations[0].remote_preference})` : "—" },
                    { label: "Rate", value: compensation.min_rate ? `${compensation.currency} ${compensation.min_rate}–${compensation.max_rate}/${compensation.rate_type}` : "—" },
                    { label: "Primary skills", value: skills.primary.slice(0, 4).join(", ") || "—" },
                    { label: "LLM provider", value: `${llm.provider} (triage: ${llm.triage_model})` },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex justify-between py-2 border-b last:border-0">
                      <span className="text-slate-500">{label}</span>
                      <span className="font-medium text-right max-w-xs truncate">{value}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  You can edit any of this later via <strong>Settings → Profile</strong> or by editing <code>data/profile.yaml</code> directly.
                </p>
                {error && <p className="text-sm text-red-600 p-3 bg-red-50 rounded">{error}</p>}
              </div>
            )}

            {/* ── Navigation ───────────────────────────────────────────────── */}
            <div className="flex justify-between mt-8 pt-4 border-t">
              <Button variant="outline" onClick={() => setStep(step - 1)} disabled={step === 1}>
                <ChevronLeft className="w-4 h-4 mr-1" /> Back
              </Button>
              {step < TOTAL_STEPS ? (
                <Button onClick={() => setStep(step + 1)}>
                  Continue <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              ) : (
                <Button onClick={handleFinish} disabled={saving} className="bg-green-600 hover:bg-green-700">
                  {saving ? "Saving…" : "Launch JobPilot →"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
