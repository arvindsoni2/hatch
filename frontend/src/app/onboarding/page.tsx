"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  testLLMConnection, saveProfile, saveApiKey, triggerAgent,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard,
} from "@/lib/api";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { ScreenWelcome } from "@/components/onboarding/ScreenWelcome";
import { ScreenSuccess } from "@/components/onboarding/ScreenSuccess";
import { StepAboutYou, type CandidateData } from "@/components/onboarding/StepAboutYou";
import { StepMarket } from "@/components/onboarding/StepMarket";
import { StepPay } from "@/components/onboarding/StepPay";
import { StepEligibility } from "@/components/onboarding/StepEligibility";
import { StepSkills, type SkillsData, type DomainsData, type ProofPoint } from "@/components/onboarding/StepSkills";
import { StepAIProvider, LLM_PROVIDERS, type LLMData } from "@/components/onboarding/StepAIProvider";
import type { SearchData, LocationData, CompensationData } from "@/components/onboarding/StepJobSearch";
import { ChevronLeft } from "lucide-react";

const FORM_STEPS = 6;
const WELCOME = 0;
const SUCCESS = 7;
const STORAGE_KEY = "hatch_onboarding_v1";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(WELCOME);
  const [hasSaved, setHasSaved] = useState(false);
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Step 1 — About you
  const [candidate, setCandidate] = useState<CandidateData>({ name: "", title: "", years_experience: 0, summary: "" });

  // Steps 2–4 — Market, Pay, Eligibility
  const [selectedLocale, setSelectedLocale] = useState("uk");
  const [locales, setLocales] = useState<LocaleSummary[]>([]);
  const [loadingLocales, setLoadingLocales] = useState(true);
  const [search, setSearch] = useState<SearchData>({ target_roles: [], contract_type: "contract" });
  const [locations, setLocations] = useState<LocationData[]>([{ city: "", country: "", radius_miles: 30, remote_preference: "hybrid" }]);
  const [compensation, setCompensation] = useState<CompensationData>({ min_rate: 0, max_rate: 0, rate_type: "daily", currency: "GBP", legal_preferences: {} });
  const [legalFields, setLegalFields] = useState<LocaleLegalField[]>([]);

  // Step 5 — Skills
  const [skills, setSkills] = useState<SkillsData>({ primary: [], secondary: [], certifications: [] });
  const [domains, setDomains] = useState<DomainsData>({ preferred: [], excluded: [] });
  const [proofPoints, setProofPoints] = useState<ProofPoint[]>([]);

  // Step 6 — AI provider
  const [llm, setLlm] = useState<LLMData>({
    provider: "llamacpp",
    triage_model: "qwen3-0.6b-q8_0",
    primary_model: "qwen3-8b-q5_k_m",
    api_key_env: "",
    base_url: "http://llm-primary:8080/v1",
    triage_base_url: "http://llm-triage:8081/v1",
    temperature: 0.3, max_retries: 3,
    track_costs: false, monthly_budget: 0, currency: "USD",
  });
  const [testApiKey, setTestApiKey] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);

  // ── Restore from localStorage ────────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        // Restore preferences but NOT personal identity fields (name/title)
        // so the form always starts blank for those fields
        if (parsed.search) setSearch(parsed.search);
        if (parsed.locations) setLocations(parsed.locations);
        if (parsed.compensation) setCompensation(parsed.compensation);
        if (parsed.skills) setSkills(parsed.skills);
        if (parsed.domains) setDomains(parsed.domains);
        if (parsed.proofPoints) setProofPoints(parsed.proofPoints);
        if (parsed.selectedLocale) setSelectedLocale(parsed.selectedLocale);
        if (parsed.llm) {
          // Migrate old "ollama" sessions to the bundled llamacpp provider.
          const restoredLlm = parsed.llm.provider === "ollama"
            ? { ...parsed.llm, provider: "llamacpp", base_url: "http://llm-primary:8080/v1", triage_base_url: "http://llm-triage:8081/v1", primary_model: "qwen3-8b-q5_k_m", triage_model: "qwen3-0.6b-q8_0", api_key_env: "" }
            : parsed.llm;
          setLlm(restoredLlm);
        }
        if (typeof parsed.step === "number" && parsed.step > 0 && parsed.step < SUCCESS) {
          setStep(parsed.step);
        }
        setHasSaved(true);
      }
    } catch {}
  }, []);

  // ── Persist to localStorage on every change ──────────────────────────────
  useEffect(() => {
    if (step === SUCCESS) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        step, candidate, search, locations, compensation, skills, domains, proofPoints, selectedLocale, llm,
      }));
    } catch {}
  }, [step, candidate, search, locations, compensation, skills, domains, proofPoints, selectedLocale, llm]);

  // ── Fetch locales ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchLocales()
      .then((ls) => setLocales(ls))
      .catch(() => {})
      .finally(() => setLoadingLocales(false));
  }, []);

  // ── Fetch legal fields + boards + auto-derive currency when locale changes ─
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

    const localePack = locales.find((l) => l.id === selectedLocale);
    if (localePack) {
      setCompensation((prev) => ({
        ...prev,
        currency: localePack.currency || prev.currency,
        rate_type: localePack.default_rate_type || prev.rate_type,
      }));
    }
  }, [selectedLocale, locales]);

  // ── Validation per step ──────────────────────────────────────────────────
  const isStepValid = (s: number): boolean => {
    switch (s) {
      case 1: return !!candidate.name.trim() && !!candidate.title.trim();
      case 2: return search.target_roles.length > 0;
      case 3: return !!locations[0].city.trim() && compensation.min_rate > 0;
      default: return true;
    }
  };

  const advance = () => {
    if (step > WELCOME && step < SUCCESS && !isStepValid(step)) {
      setTried(true);
      return;
    }
    setTried(false);
    setStep((s) => s + 1);
  };

  const back = () => { setTried(false); setStep((s) => Math.max(WELCOME, s - 1)); };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setConnectionResult(null);
    const result = await testLLMConnection(llm.provider, testApiKey).catch((e: unknown) => ({
      ok: false, error: e instanceof Error ? e.message : "Unknown error",
    }));
    setConnectionResult(result);
    setTestingConnection(false);
  };

  const buildProfile = () => ({
    locale: selectedLocale,
    candidate,
    search: { ...search, locations },
    compensation,
    skills,
    domains,
    proof_points: proofPoints.filter((p) => p.summary.trim()),
    master_cv_path: "./data/master_cv.json",
    job_boards: boards.map((b) => ({
      name: b.name, enabled: enabledBoards.has(b.id), scraper: b.scraper, search_params: {},
    })),
    scoring: {
      weights: { skill_match: 0.35, experience_match: 0.30, rate_match: 0.20, location_match: 0.15 },
      shortlist_threshold: 0.75,
    },
    llm,
    preferences: {
      scrape_interval_hours: scrapeIntervalHours, max_tailor_batch: 5,
      follow_up_days: [5, 10, 15], locale: "en-GB", archive_after_days: 30,
    },
  });

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      await saveProfile(buildProfile());
      if (testApiKey && llm.provider !== "llamacpp") {
        const keyResult = await saveApiKey(llm.api_key_env, testApiKey);
        if (!keyResult.valid) {
          throw new Error(keyResult.error || "API key could not be saved");
        }
      }
      await triggerAgent("scout").catch(() => {});
      try { localStorage.removeItem(STORAGE_KEY); } catch {}
      setStep(SUCCESS);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setSaving(false);
    }
  };

  const currentLocale = locales.find((l) => l.id === selectedLocale);
  const formStep = step === WELCOME || step === SUCCESS ? 0 : step;

  return (
    <div
      data-onboarding="true"
      className="fixed inset-0 z-50 overflow-y-auto"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <div className="w-full max-w-lg mx-auto min-h-screen flex flex-col">
        {/* Header row */}
        <div className="flex items-center justify-between px-5 pt-4">
          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-[7px] grid place-items-center font-[800] text-[13px] text-[var(--bg)]"
              style={{ background: "var(--text)" }}
            >
              H
            </div>
            <span className="text-[14px] font-[650] tracking-[-0.02em] text-[var(--text)]">Hatch</span>
          </div>
          {step > WELCOME && step < SUCCESS && (
            <span className="text-[12px] text-[var(--text-muted)] tabular-nums">
              <strong className="text-[var(--text)]">{formStep}</strong> of {FORM_STEPS}
            </span>
          )}
        </div>

        {/* Numeral progress */}
        <OnboardingProgress formStep={formStep} />

        {/* Screen content */}
        <div className="flex-1 overflow-y-auto">
          {step === WELCOME && <ScreenWelcome hasSaved={hasSaved} onStart={advance} />}
          {step === 1 && <StepAboutYou candidate={candidate} onChange={setCandidate} tried={tried} />}
          {step === 2 && (
            <StepMarket
              selectedLocale={selectedLocale} locales={locales} loadingLocales={loadingLocales}
              onLocaleChange={setSelectedLocale} search={search} onSearchChange={setSearch} tried={tried}
            />
          )}
          {step === 3 && (
            <StepPay
              locale={currentLocale} locations={locations} onLocationsChange={setLocations}
              compensation={compensation} onCompensationChange={setCompensation} tried={tried}
            />
          )}
          {step === 4 && (
            <StepEligibility
              locale={currentLocale} legalFields={legalFields}
              compensation={compensation} onCompensationChange={setCompensation}
            />
          )}
          {step === 5 && (
            <StepSkills
              skills={skills} onSkillsChange={setSkills}
              domains={domains} onDomainsChange={setDomains}
              proofPoints={proofPoints} onProofPointsChange={setProofPoints}
            />
          )}
          {step === 6 && (
            <StepAIProvider
              llm={llm} onLlmChange={setLlm}
              testApiKey={testApiKey} onTestApiKeyChange={(k) => { setTestApiKey(k); setConnectionResult(null); }}
              testingConnection={testingConnection} connectionResult={connectionResult} onTestConnection={handleTestConnection}
              boards={boards} enabledBoards={enabledBoards} onEnabledBoardsChange={setEnabledBoards}
              scrapeIntervalHours={scrapeIntervalHours} onScrapeIntervalChange={setScrapeIntervalHours}
            />
          )}
          {step === SUCCESS && (
            <ScreenSuccess
              candidate={candidate} selectedLocale={selectedLocale} locales={locales}
              targetRolesCount={search.target_roles.length} minRate={compensation.min_rate}
              providerName={LLM_PROVIDERS.find((p) => p.id === llm.provider)?.label ?? llm.provider}
              enabledBoardsCount={enabledBoards.size}
              onDashboard={() => router.push("/?firstRun=true")}
            />
          )}
        </div>

        {/* Footer navigation */}
        {step > WELCOME && step < SUCCESS && (
          <div
            className="flex-shrink-0 flex gap-2.5 px-5 py-3.5 border-t border-[var(--border)]"
            style={{ background: "var(--bg)", paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 14px)" }}
          >
            <button
              type="button" onClick={back}
              className="px-3.5 py-3 text-[14px] font-[600] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors"
            >
              <ChevronLeft className="w-4 h-4 inline mr-0.5" /> Back
            </button>
            {step < FORM_STEPS ? (
              <button
                type="button" onClick={advance}
                className="flex-1 py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] transition-colors hover:opacity-90"
                style={{ background: "var(--accent)" }}
              >
                Continue →
              </button>
            ) : (
              <button
                type="button" onClick={handleFinish} disabled={saving}
                className="flex-1 py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] disabled:opacity-50 transition-colors hover:opacity-90"
                style={{ background: "var(--accent)" }}
              >
                {saving ? "Saving…" : "Start Hatch →"}
              </button>
            )}
          </div>
        )}

        {/* Inline error (step 6 only) */}
        {error && step === FORM_STEPS && (
          <p
            className="mx-5 mb-3 text-sm text-[var(--danger)] px-3 py-2 rounded border border-[var(--danger-soft)]"
            style={{ background: "var(--danger-soft)" }}
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
