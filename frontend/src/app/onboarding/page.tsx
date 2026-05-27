"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2, ChevronRight, ChevronLeft, User, Globe, Briefcase,
  Star, Cpu, Loader2, CheckCircle, XCircle, Zap,
} from "lucide-react";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  testLLMConnection, saveProfile,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard,
} from "@/lib/api";

const TOTAL_STEPS = 5;

const LLM_PROVIDERS = [
  { id: "anthropic", label: "Anthropic (Claude)", keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001", primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai", label: "OpenAI (GPT)", keyEnv: "OPENAI_API_KEY", triageDefault: "gpt-4o-mini", primaryDefault: "gpt-4o" },
  { id: "google", label: "Google (Gemini)", keyEnv: "GOOGLE_API_KEY", triageDefault: "gemini-3.0-flash", primaryDefault: "gemini-3.0-pro" },
  { id: "ollama", label: "Ollama (local — free)", keyEnv: "", triageDefault: "gemma3:4b", primaryDefault: "qwen3:14b" },
];

// ── Step indicator ───────────────────────────────────────────────────────────

const STEP_LABELS = ["Identity", "Your market", "Compensation", "Skills", "AI & launch"];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-1 mb-8 overflow-x-auto">
      {STEP_LABELS.map((label, i) => (
        <div key={i} className="flex items-center min-w-0">
          <div className="flex flex-col items-center gap-1">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                i + 1 < current
                  ? "bg-green-500 text-white"
                  : i + 1 === current
                  ? "bg-brand-600 text-white"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {i + 1 < current ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs whitespace-nowrap ${i + 1 === current ? "text-brand-700 font-medium" : "text-slate-400"}`}>
              {label}
            </span>
          </div>
          {i < TOTAL_STEPS - 1 && (
            <div className={`w-8 h-0.5 mx-1 mb-4 flex-shrink-0 ${i + 1 < current ? "bg-green-500" : "bg-slate-200"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Reusable tag input ───────────────────────────────────────────────────────

function TagInput({ label, tags, onAdd, onRemove, placeholder }: {
  label: string; tags: string[]; onAdd: (t: string) => void;
  onRemove: (i: number) => void; placeholder?: string;
}) {
  const [input, setInput] = useState("");
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-2 p-2 border rounded-md min-h-[42px] bg-white">
        {tags.map((t, i) => (
          <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => onRemove(i)}>
            {t} ×
          </Badge>
        ))}
        <input
          className="flex-1 min-w-[120px] outline-none text-sm bg-transparent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === ",") && input.trim()) {
              e.preventDefault();
              onAdd(input.trim());
              setInput("");
            }
          }}
          placeholder={placeholder ?? "Type and press Enter"}
        />
      </div>
      <p className="text-xs text-slate-400">Press Enter or comma to add</p>
    </div>
  );
}

// ── Proof point STAR form ────────────────────────────────────────────────────

interface ProofPoint { id: string; summary: string; context: string; metrics: string; tags: string[] }

function ProofPointForm({ point, onChange, onRemove }: {
  point: ProofPoint;
  onChange: (p: ProofPoint) => void;
  onRemove: () => void;
}) {
  const [tagInput, setTagInput] = useState("");
  return (
    <div className="border rounded-lg p-4 space-y-3 bg-slate-50">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">Achievement</p>
        <button onClick={onRemove} className="text-xs text-red-500 hover:underline">Remove</button>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">One-line summary *</Label>
        <Input value={point.summary} onChange={(e) => onChange({ ...point, summary: e.target.value })} placeholder="Led migration of 3 legacy systems to AWS, cutting infra costs 40%" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Context (Situation / Task)</Label>
          <Textarea rows={2} value={point.context} onChange={(e) => onChange({ ...point, context: e.target.value })} placeholder="Inherited a fragile on-prem estate…" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Metrics / Result</Label>
          <Textarea rows={2} value={point.metrics} onChange={(e) => onChange({ ...point, metrics: e.target.value })} placeholder="£1.2M annual saving, 99.9% uptime" />
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Tags (skills demonstrated)</Label>
        <div className="flex flex-wrap gap-1.5 p-2 border rounded-md bg-white min-h-[34px]">
          {point.tags.map((t, i) => (
            <Badge key={i} variant="secondary" className="text-xs cursor-pointer" onClick={() => onChange({ ...point, tags: point.tags.filter((_, j) => j !== i) })}>
              {t} ×
            </Badge>
          ))}
          <input
            className="flex-1 min-w-[80px] outline-none text-xs bg-transparent"
            value={tagInput}
            placeholder="AWS, Cloud…"
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === ",") && tagInput.trim()) {
                e.preventDefault();
                onChange({ ...point, tags: [...point.tags, tagInput.trim()] });
                setTagInput("");
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Step 1 — Identity
  const [candidate, setCandidate] = useState({ name: "", title: "", years_experience: 0, summary: "" });

  // Step 2 — Market
  const [selectedLocale, setSelectedLocale] = useState("uk");
  const [locales, setLocales] = useState<LocaleSummary[]>([]);
  const [loadingLocales, setLoadingLocales] = useState(true);
  const [search, setSearch] = useState({ target_roles: [] as string[], contract_type: "contract" });
  const [locations, setLocations] = useState([{ city: "", country: "", radius_miles: 30, remote_preference: "hybrid" }]);

  // Step 3 — Compensation & legal
  const [compensation, setCompensation] = useState({ min_rate: 0, max_rate: 0, rate_type: "daily", currency: "", legal_preferences: {} as Record<string, string> });
  const [legalFields, setLegalFields] = useState<LocaleLegalField[]>([]);

  // Step 4 — Skills
  const [skills, setSkills] = useState({ primary: [] as string[], secondary: [] as string[], certifications: [] as string[] });
  const [domains, setDomains] = useState({ preferred: [] as string[], excluded: [] as string[] });
  const [proofPoints, setProofPoints] = useState<ProofPoint[]>([]);

  // Step 5 — AI setup
  const [llm, setLlm] = useState({ provider: "anthropic", triage_model: "claude-haiku-4-5-20251001", primary_model: "claude-sonnet-4-20250514", api_key_env: "ANTHROPIC_API_KEY", base_url: null as string | null, temperature: 0.3, max_retries: 3, track_costs: true, monthly_budget: 15, currency: "GBP" });
  const [testApiKey, setTestApiKey] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);

  // Load locales on mount
  useEffect(() => {
    fetchLocales()
      .then((ls) => setLocales(ls))
      .catch(() => {})
      .finally(() => setLoadingLocales(false));
  }, []);

  // Load legal fields + boards when locale changes
  useEffect(() => {
    fetchLocaleLegalFields(selectedLocale)
      .then((fields) => {
        setLegalFields(fields);
        const defaults: Record<string, string> = {};
        fields.forEach((f) => { defaults[f.id] = f.default; });
        setCompensation((prev) => ({ ...prev, legal_preferences: defaults }));
      })
      .catch(() => setLegalFields([]));

    fetchLocaleBoards(selectedLocale)
      .then((bs) => {
        setBoards(bs);
        setEnabledBoards(new Set(bs.filter((b) => b.enabled).map((b) => b.id)));
      })
      .catch(() => setBoards([]));
  }, [selectedLocale]);

  const handleProviderChange = (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (p) {
      setLlm((prev) => ({ ...prev, provider: providerId, triage_model: p.triageDefault, primary_model: p.primaryDefault, api_key_env: p.keyEnv }));
      setConnectionResult(null);
    }
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setConnectionResult(null);
    const result = await testLLMConnection(llm.provider, testApiKey).catch((e: unknown) => ({
      ok: false,
      error: e instanceof Error ? e.message : "Unknown error",
    }));
    setConnectionResult(result);
    setTestingConnection(false);
  };

  const addProofPoint = () => {
    setProofPoints((prev) => [...prev, {
      id: `pp_${Date.now()}`, summary: "", context: "", metrics: "", tags: [],
    }]);
  };

  const buildProfile = () => ({
    locale: selectedLocale,
    candidate,
    search: { ...search, locations },
    compensation: {
      ...compensation,
    },
    skills,
    domains,
    proof_points: proofPoints.filter((p) => p.summary.trim()).map((p) => ({ ...p })),
    master_cv_path: "./data/master_cv.json",
    job_boards: boards.map((b) => ({ name: b.name, enabled: enabledBoards.has(b.id), scraper: b.scraper, search_params: {} })),
    scoring: { weights: { skill_match: 0.35, experience_match: 0.30, rate_match: 0.20, location_match: 0.15 }, shortlist_threshold: 0.75 },
    llm,
    preferences: { scrape_interval_hours: scrapeIntervalHours, max_tailor_batch: 5, follow_up_days: [5, 10, 15], locale: "en-GB", archive_after_days: 30 },
  });

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      await saveProfile(buildProfile());
      router.push("/");
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
          <h1 className="text-3xl font-bold text-slate-900">Welcome to JobPilot</h1>
          <p className="mt-2 text-slate-500">Set up your profile and launch your autonomous job search.</p>
        </div>

        <StepIndicator current={step} />

        <Card>
          <CardContent className="pt-6">

            {/* ── Step 1: Identity ─────────────────────────────────────────── */}
            {step === 1 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><User className="w-5 h-5 text-brand-600" /><CardTitle>Who are you?</CardTitle></div>
                  <CardDescription>Used in CV and cover letter generation — never hardcoded in code.</CardDescription>
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
                  <Input type="number" min={0} value={candidate.years_experience} onChange={(e) => setCandidate({ ...candidate, years_experience: parseInt(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1">
                  <Label>Professional summary (2–3 sentences)</Label>
                  <Textarea rows={3} value={candidate.summary} onChange={(e) => setCandidate({ ...candidate, summary: e.target.value })} placeholder="Senior technology professional with 15 years leading complex transformation programmes…" />
                </div>
              </div>
            )}

            {/* ── Step 2: Market ──────────────────────────────────────────── */}
            {step === 2 && (
              <div className="space-y-5">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Globe className="w-5 h-5 text-brand-600" /><CardTitle>Your market</CardTitle></div>
                  <CardDescription>Pick your job market — this controls which job boards are scraped and how compliance fields are shown.</CardDescription>
                </CardHeader>

                {loadingLocales ? (
                  <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 className="h-4 w-4 animate-spin" /> Loading markets…</div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {locales.map((l) => (
                      <button
                        key={l.id}
                        onClick={() => setSelectedLocale(l.id)}
                        className={`p-4 border-2 rounded-lg text-left transition-colors flex items-center gap-3 ${selectedLocale === l.id ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:border-slate-300"}`}
                      >
                        <span className="text-2xl">{l.flag}</span>
                        <span className="font-medium text-sm">{l.name}</span>
                        {selectedLocale === l.id && <CheckCircle2 className="h-4 w-4 text-brand-600 ml-auto" />}
                      </button>
                    ))}
                  </div>
                )}

                <TagInput label="Target job titles *" tags={search.target_roles}
                  onAdd={(t) => setSearch({ ...search, target_roles: [...search.target_roles, t] })}
                  onRemove={(i) => setSearch({ ...search, target_roles: search.target_roles.filter((_, idx) => idx !== i) })}
                  placeholder="Delivery Lead, Product Manager…" />

                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label>City *</Label>
                    <Input value={locations[0].city} onChange={(e) => setLocations([{ ...locations[0], city: e.target.value }])} placeholder="City" />
                  </div>
                  <div className="space-y-1">
                    <Label>Country *</Label>
                    <Input value={locations[0].country} onChange={(e) => setLocations([{ ...locations[0], country: e.target.value }])} placeholder="Country" />
                  </div>
                  <div className="space-y-1">
                    <Label>Remote preference</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={locations[0].remote_preference} onChange={(e) => setLocations([{ ...locations[0], remote_preference: e.target.value }])}>
                      <option value="remote">Remote</option>
                      <option value="hybrid">Hybrid</option>
                      <option value="onsite">On-site</option>
                      <option value="any">Any</option>
                    </select>
                  </div>
                </div>
                <div className="space-y-1 w-1/2">
                  <Label>Contract type</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={search.contract_type} onChange={(e) => setSearch({ ...search, contract_type: e.target.value })}>
                    <option value="contract">Contract</option>
                    <option value="permanent">Permanent</option>
                    <option value="freelance">Freelance</option>
                    <option value="any">Any</option>
                  </select>
                </div>
              </div>
            )}

            {/* ── Step 3: Compensation & legal ─────────────────────────────── */}
            {step === 3 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Briefcase className="w-5 h-5 text-brand-600" /><CardTitle>Compensation & eligibility</CardTitle></div>
                  <CardDescription>Rate range is used to score job fit. Compliance fields are specific to the {locales.find((l) => l.id === selectedLocale)?.name ?? selectedLocale} market.</CardDescription>
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
                      <option value="monthly">Monthly</option>
                    </select>
                  </div>
                </div>
                <div className="space-y-1 w-1/3">
                  <Label>Currency</Label>
                  <Input value={compensation.currency} onChange={(e) => setCompensation({ ...compensation, currency: e.target.value })} placeholder="Currency (e.g. GBP, USD, INR)" />
                </div>

                {legalFields.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <p className="text-sm font-medium text-slate-700">Eligibility & compliance</p>
                    {legalFields.map((field) => (
                      <div key={field.id} className="space-y-1">
                        <Label>{field.label}</Label>
                        {field.type === "select" && field.options ? (
                          <select
                            className="w-full border rounded-md p-2 text-sm"
                            value={compensation.legal_preferences[field.id] ?? field.default}
                            onChange={(e) => setCompensation({ ...compensation, legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value } })}
                          >
                            {field.options.map((opt) => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        ) : (
                          <Input
                            value={compensation.legal_preferences[field.id] ?? ""}
                            onChange={(e) => setCompensation({ ...compensation, legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value } })}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Step 4: Skills & proof points ────────────────────────────── */}
            {step === 4 && (
              <div className="space-y-4">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Star className="w-5 h-5 text-brand-600" /><CardTitle>Skills & achievements</CardTitle></div>
                  <CardDescription>Primary skills are weighted most heavily. Achievements give the AI concrete proof points for tailoring.</CardDescription>
                </CardHeader>
                <TagInput label="Primary skills *" tags={skills.primary}
                  onAdd={(t) => setSkills({ ...skills, primary: [...skills.primary, t] })}
                  onRemove={(i) => setSkills({ ...skills, primary: skills.primary.filter((_, idx) => idx !== i) })}
                  placeholder="Agile, AWS, Stakeholder management…" />
                <TagInput label="Secondary skills" tags={skills.secondary}
                  onAdd={(t) => setSkills({ ...skills, secondary: [...skills.secondary, t] })}
                  onRemove={(i) => setSkills({ ...skills, secondary: skills.secondary.filter((_, idx) => idx !== i) })}
                  placeholder="Python, Terraform…" />
                <TagInput label="Preferred domains" tags={domains.preferred}
                  onAdd={(t) => setDomains({ ...domains, preferred: [...domains.preferred, t] })}
                  onRemove={(i) => setDomains({ ...domains, preferred: domains.preferred.filter((_, idx) => idx !== i) })}
                  placeholder="FinTech, Energy, Public Sector…" />

                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-700">Achievements (optional — improves CV tailoring)</p>
                    <Button variant="outline" size="sm" onClick={addProofPoint}>+ Add achievement</Button>
                  </div>
                  {proofPoints.map((p, i) => (
                    <ProofPointForm key={p.id} point={p}
                      onChange={(updated) => setProofPoints(proofPoints.map((x, j) => j === i ? updated : x))}
                      onRemove={() => setProofPoints(proofPoints.filter((_, j) => j !== i))}
                    />
                  ))}
                  {proofPoints.length === 0 && (
                    <p className="text-xs text-slate-400 text-center py-4">No achievements added yet. You can add them later in Settings.</p>
                  )}
                </div>
              </div>
            )}

            {/* ── Step 5: AI setup & launch ──────────────────────────────── */}
            {step === 5 && (
              <div className="space-y-5">
                <CardHeader className="px-0 pt-0">
                  <div className="flex items-center gap-2"><Cpu className="w-5 h-5 text-brand-600" /><CardTitle>AI setup & launch</CardTitle></div>
                  <CardDescription>Choose your LLM provider, enable job boards, then launch your pipeline.</CardDescription>
                </CardHeader>

                {/* Provider picker */}
                <div className="grid grid-cols-2 gap-3">
                  {LLM_PROVIDERS.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleProviderChange(p.id)}
                      className={`p-4 border-2 rounded-lg text-left transition-colors ${llm.provider === p.id ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:border-slate-300"}`}
                    >
                      <div className="font-medium text-sm">{p.label}</div>
                      {p.id === "ollama" && <div className="text-xs text-green-600 mt-1">No API key needed</div>}
                    </button>
                  ))}
                </div>

                {/* API key setup + test */}
                {llm.provider !== "ollama" && (
                  <div className="space-y-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm font-medium text-amber-800">API key setup</p>
                    <p className="text-xs text-amber-700">
                      Set <code className="bg-amber-100 px-1 rounded">{llm.api_key_env}</code> in your{" "}
                      <code className="bg-amber-100 px-1 rounded">.env</code> file. Your key is never stored in profile.yaml.
                    </p>
                    <div className="flex gap-2">
                      <Input
                        type="password"
                        className="flex-1 text-sm"
                        placeholder="Paste key to test (not saved)"
                        value={testApiKey}
                        onChange={(e) => { setTestApiKey(e.target.value); setConnectionResult(null); }}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleTestConnection}
                        disabled={!testApiKey || testingConnection}
                      >
                        {testingConnection ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
                      </Button>
                    </div>
                    {connectionResult && (
                      <div className={`flex items-center gap-2 text-sm ${connectionResult.ok ? "text-green-700" : "text-red-700"}`}>
                        {connectionResult.ok
                          ? <><CheckCircle className="h-4 w-4" /> Connection successful</>
                          : <><XCircle className="h-4 w-4" /> {connectionResult.error ?? "Connection failed"}</>}
                      </div>
                    )}
                  </div>
                )}

                {llm.provider === "ollama" && (
                  <div className="space-y-1">
                    <Label>Ollama base URL</Label>
                    <Input value={llm.base_url || ""} onChange={(e) => setLlm({ ...llm, base_url: e.target.value || null })} placeholder="http://localhost:11434" />
                  </div>
                )}

                {/* Job board toggles */}
                {boards.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-slate-700">Job boards to scrape</p>
                    <div className="grid grid-cols-2 gap-2">
                      {boards.map((b) => (
                        <label key={b.id} className="flex items-center gap-2 p-2 border rounded-md cursor-pointer hover:bg-slate-50">
                          <input
                            type="checkbox"
                            checked={enabledBoards.has(b.id)}
                            onChange={() => {
                              const next = new Set(enabledBoards);
                              if (next.has(b.id)) next.delete(b.id); else next.add(b.id);
                              setEnabledBoards(next);
                            }}
                          />
                          <span className="text-sm">{b.name}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Scrape interval */}
                <div className="space-y-1 w-1/3">
                  <Label>Scrape interval (hours)</Label>
                  <Input type="number" min={1} max={24} value={scrapeIntervalHours} onChange={(e) => setScrapeIntervalHours(parseInt(e.target.value) || 4)} />
                </div>

                {/* Summary */}
                <div className="space-y-2 pt-2 border-t">
                  <p className="text-xs font-medium text-slate-600 uppercase tracking-wide">Ready to launch</p>
                  {[
                    { label: "Name", value: candidate.name || "—" },
                    { label: "Market", value: locales.find((l) => l.id === selectedLocale)?.name ?? selectedLocale },
                    { label: "Target roles", value: search.target_roles.join(", ") || "—" },
                    { label: "Rate", value: compensation.min_rate ? `${compensation.currency} ${compensation.min_rate}–${compensation.max_rate}/${compensation.rate_type}` : "—" },
                    { label: "AI provider", value: `${llm.provider} · ${llm.primary_model}` },
                    { label: "Boards enabled", value: `${enabledBoards.size} of ${boards.length}` },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex justify-between py-1 text-sm border-b last:border-0">
                      <span className="text-slate-500">{label}</span>
                      <span className="font-medium text-right max-w-xs truncate">{value}</span>
                    </div>
                  ))}
                </div>

                <p className="text-xs text-slate-400">
                  Everything can be changed later via Settings or by editing <code>data/profile.yaml</code>.
                </p>

                {error && <p className="text-sm text-red-600 p-3 bg-red-50 rounded">{error}</p>}
              </div>
            )}

            {/* ── Navigation ───────────────────────────────────────────────── */}
            {(() => {
              const stepErrors: Record<number, string> = {
                1: !candidate.name.trim() ? "Name is required." : "",
                2: search.target_roles.length === 0 ? "Add at least one target job title to continue." : "",
              };
              const blockMsg = stepErrors[step] ?? "";
              return (
              <div className="mt-8 pt-4 border-t space-y-3">
                {blockMsg && (
                  <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    {blockMsg}
                  </p>
                )}
                <div className="flex justify-between">
                  <Button variant="outline" onClick={() => setStep(step - 1)} disabled={step === 1}>
                    <ChevronLeft className="w-4 h-4 mr-1" /> Back
                  </Button>
                  {step < TOTAL_STEPS ? (
                    <Button onClick={() => setStep(step + 1)} disabled={!!blockMsg}>
                      Continue <ChevronRight className="w-4 h-4 ml-1" />
                    </Button>
                  ) : (
                    <Button onClick={handleFinish} disabled={saving} className="bg-brand-600 hover:bg-brand-700 text-white gap-2">
                      {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : <><Zap className="h-4 w-4" /> Start JobPilot</>}
                    </Button>
                  )}
                </div>
              </div>
              );
            })()}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
