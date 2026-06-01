"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ChevronRight, ChevronLeft } from "lucide-react";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  testLLMConnection, saveProfile, saveApiKey, triggerAgent,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard,
} from "@/lib/api";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { StepAboutYou, type CandidateData } from "@/components/onboarding/StepAboutYou";
import { StepJobSearch, type SearchData, type LocationData, type CompensationData } from "@/components/onboarding/StepJobSearch";
import { StepSkills, type SkillsData, type DomainsData, type ProofPoint } from "@/components/onboarding/StepSkills";
import { StepAIProvider, type LLMData } from "@/components/onboarding/StepAIProvider";
import { StepReview } from "@/components/onboarding/StepReview";

const TOTAL_STEPS = 5;

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [triedStep1, setTriedStep1] = useState(false);

  // Step 1 — About you
  const [candidate, setCandidate] = useState<CandidateData>({ name: "", title: "", years_experience: 0, summary: "" });

  // Step 2 — Job search + compensation
  const [selectedLocale, setSelectedLocale] = useState("uk");
  const [locales, setLocales] = useState<LocaleSummary[]>([]);
  const [loadingLocales, setLoadingLocales] = useState(true);
  const [search, setSearch] = useState<SearchData>({ target_roles: [], contract_type: "contract" });
  const [locations, setLocations] = useState<LocationData[]>([{ city: "", country: "", radius_miles: 30, remote_preference: "hybrid" }]);
  const [compensation, setCompensation] = useState<CompensationData>({ min_rate: 0, max_rate: 0, rate_type: "daily", currency: "", legal_preferences: {} });
  const [legalFields, setLegalFields] = useState<LocaleLegalField[]>([]);

  // Step 3 — Skills
  const [skills, setSkills] = useState<SkillsData>({ primary: [], secondary: [], certifications: [] });
  const [domains, setDomains] = useState<DomainsData>({ preferred: [], excluded: [] });
  const [proofPoints, setProofPoints] = useState<ProofPoint[]>([]);

  // Step 4 — AI provider
  const [llm, setLlm] = useState<LLMData>({
    provider: "google", triage_model: "gemini-2.5-flash-lite", primary_model: "gemini-2.5-flash",
    api_key_env: "GOOGLE_API_KEY", base_url: null, temperature: 0.3, max_retries: 3,
    track_costs: true, monthly_budget: 15, currency: "USD",
  });
  const [testApiKey, setTestApiKey] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);

  useEffect(() => {
    fetchLocales()
      .then((ls) => setLocales(ls))
      .catch(() => {})
      .finally(() => setLoadingLocales(false));
  }, []);

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

  const buildProfile = () => ({
    locale: selectedLocale,
    candidate,
    search: { ...search, locations },
    compensation,
    skills,
    domains,
    proof_points: proofPoints.filter((p) => p.summary.trim()),
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
      if (testApiKey && llm.provider !== "ollama") {
        await saveApiKey(llm.api_key_env, testApiKey).catch(() => {});
      }
      await triggerAgent("scout").catch(() => {});
      router.push("/?firstRun=true");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setSaving(false);
    }
  };

  const localeName = locales.find((l) => l.id === selectedLocale)?.name ?? selectedLocale;

  const stepValidation: Record<number, string> = {
    1: !candidate.name.trim() || !candidate.title.trim() ? "Name and title are required." : "",
    2: search.target_roles.length === 0 ? "Add at least one target job title to continue."
      : !locations[0].city.trim() ? "City is required."
      : compensation.min_rate <= 0 ? "Minimum rate must be greater than 0."
      : "",
    3: "",
    4: "",
  };

  const blockMsg = stepValidation[step] ?? "";

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold text-slate-900">Welcome to Hatch</h1>
          <p className="mt-2 text-slate-500">Set up your profile and launch your autonomous job search.</p>
        </div>

        <OnboardingProgress current={step} />

        <Card>
          <CardContent className="pt-6">
            {step === 1 && (
              <StepAboutYou candidate={candidate} onChange={setCandidate} tried={triedStep1} />
            )}
            {step === 2 && (
              <StepJobSearch
                selectedLocale={selectedLocale}
                locales={locales}
                loadingLocales={loadingLocales}
                onLocaleChange={setSelectedLocale}
                search={search}
                onSearchChange={setSearch}
                locations={locations}
                onLocationsChange={setLocations}
                compensation={compensation}
                onCompensationChange={setCompensation}
                legalFields={legalFields}
                localeName={localeName}
              />
            )}
            {step === 3 && (
              <StepSkills
                skills={skills}
                onSkillsChange={setSkills}
                domains={domains}
                onDomainsChange={setDomains}
                proofPoints={proofPoints}
                onProofPointsChange={setProofPoints}
              />
            )}
            {step === 4 && (
              <StepAIProvider
                llm={llm}
                onLlmChange={setLlm}
                testApiKey={testApiKey}
                onTestApiKeyChange={(k) => { setTestApiKey(k); setConnectionResult(null); }}
                testingConnection={testingConnection}
                connectionResult={connectionResult}
                onTestConnection={handleTestConnection}
                boards={boards}
                enabledBoards={enabledBoards}
                onEnabledBoardsChange={setEnabledBoards}
                scrapeIntervalHours={scrapeIntervalHours}
                onScrapeIntervalChange={setScrapeIntervalHours}
              />
            )}
            {step === 5 && (
              <StepReview
                candidate={candidate}
                selectedLocale={selectedLocale}
                locales={locales}
                search={search}
                compensation={compensation}
                skills={skills}
                llm={llm}
                enabledBoardsCount={enabledBoards.size}
                totalBoardsCount={boards.length}
                error={error}
                saving={saving}
                onFinish={handleFinish}
              />
            )}

            {/* Navigation */}
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
                {step < TOTAL_STEPS && (
                  <Button onClick={() => { if (step === 1) setTriedStep1(true); if (!blockMsg) setStep(step + 1); }} disabled={!!blockMsg}>
                    Continue <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
