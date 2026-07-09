"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, LockKeyhole } from "lucide-react";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  testLLMConnection, saveProfile, triggerAgent, getAppLockStatus,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard, type PasswordPolicy,
} from "@/lib/api";
import {
  createOnboardingDraft,
  LEGACY_ONBOARDING_STORAGE_KEY,
  ONBOARDING_STORAGE_KEY,
  restoreOnboardingDraft,
} from "@/lib/onboardingDraft";
import {
  getOnboardingStepErrors,
  getOnboardingWarnings,
} from "@/lib/onboardingValidation";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { ScreenWelcome } from "@/components/onboarding/ScreenWelcome";
import { ScreenSuccess } from "@/components/onboarding/ScreenSuccess";
import { StepPasswordSetup } from "@/components/onboarding/StepPasswordSetup";
import { StepAboutYou, type CandidateData } from "@/components/onboarding/StepAboutYou";
import { StepMarket } from "@/components/onboarding/StepMarket";
import { StepPay } from "@/components/onboarding/StepPay";
import { StepEligibility } from "@/components/onboarding/StepEligibility";
import {
  StepSkills, type SkillsData, type DomainsData, type ProofPoint,
} from "@/components/onboarding/StepSkills";
import {
  StepAIProvider, LLM_PROVIDERS, type LLMData,
} from "@/components/onboarding/StepAIProvider";
import { StepReview } from "@/components/onboarding/StepReview";
import type {
  SearchData, LocationData, CompensationData,
} from "@/components/onboarding/StepJobSearch";

const WELCOME = 0;
const PASSWORD = 1;
const ABOUT = 2;
const MARKET = 3;
const PAY = 4;
const ELIGIBILITY = 5;
const SKILLS = 6;
const AI_PROVIDER = 7;
const REVIEW = 8;
const SUCCESS = 9;
const PROFILE_FORM_STEPS = 6;

const DEFAULT_LLM: LLMData = {
  provider: "llamacpp",
  triage_model: "qwen3.5-0.8b-q8_0",
  primary_model: "qwen3.5-4b-q4_k_m",
  api_key_env: "",
  base_url: "http://llm-primary:8080/v1",
  triage_base_url: "http://llm-triage:8081/v1",
  temperature: 0.3,
  max_retries: 3,
  track_costs: false,
  monthly_budget: 0,
  currency: "USD",
};

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(WELCOME);
  const [hasSaved, setHasSaved] = useState(false);
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [rolesSkipped, setRolesSkipped] = useState(false);
  const [skillsSkipped, setSkillsSkipped] = useState(false);
  const [aiSetupLater, setAiSetupLater] = useState(false);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [passwordPolicy, setPasswordPolicy] = useState<PasswordPolicy | undefined>();

  const [candidate, setCandidate] = useState<CandidateData>({
    name: "", title: "", years_experience: 0, summary: "",
  });
  const [selectedLocale, setSelectedLocale] = useState("uk");
  const [locales, setLocales] = useState<LocaleSummary[]>([]);
  const [loadingLocales, setLoadingLocales] = useState(true);
  const [search, setSearch] = useState<SearchData>({
    target_roles: [], contract_type: "contract",
  });
  const [locations, setLocations] = useState<LocationData[]>([{
    city: "", country: "", radius_miles: 30, remote_preference: "hybrid",
  }]);
  const [compensation, setCompensation] = useState<CompensationData>({
    min_rate: 0, max_rate: 0, rate_type: "daily", currency: "GBP",
    legal_preferences: {},
  });
  const [legalFields, setLegalFields] = useState<LocaleLegalField[]>([]);
  const [skills, setSkills] = useState<SkillsData>({
    primary: [], secondary: [], certifications: [],
  });
  const [domains, setDomains] = useState<DomainsData>({ preferred: [], excluded: [] });
  const [proofPoints, setProofPoints] = useState<ProofPoint[]>([]);
  const [llm, setLlm] = useState<LLMData>(DEFAULT_LLM);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{
    ok: boolean; error?: string;
  } | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);
  const restoredBoardIds = useRef<string[] | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(ONBOARDING_STORAGE_KEY)
        ?? localStorage.getItem(LEGACY_ONBOARDING_STORAGE_KEY);
      if (raw) {
        const draft = restoreOnboardingDraft(JSON.parse(raw));
        if (draft.search) setSearch(draft.search);
        if (draft.skills) setSkills(draft.skills);
        if (draft.domains) setDomains(draft.domains);
        if (draft.selectedLocale) setSelectedLocale(draft.selectedLocale);
        if (draft.llm) {
          setLlm(draft.llm.provider === "ollama" ? DEFAULT_LLM : draft.llm);
        }
        setRolesSkipped(draft.rolesSkipped === true);
        setSkillsSkipped(draft.skillsSkipped === true);
        setAiSetupLater(draft.aiSetupLater === true);
        if (typeof draft.scrapeIntervalHours === "number") {
          setScrapeIntervalHours(draft.scrapeIntervalHours);
        }
        if (draft.enabledBoardIds) restoredBoardIds.current = draft.enabledBoardIds;
        if (typeof draft.step === "number" && draft.step > 0 && draft.step < SUCCESS) {
          const restoredStep = draft.step >= REVIEW
            ? REVIEW
            : Math.min(AI_PROVIDER, Math.max(ABOUT, draft.step + 1));
          setStep(restoredStep);
        }
        setHasSaved(true);
      }
      localStorage.removeItem(LEGACY_ONBOARDING_STORAGE_KEY);
    } catch {
      localStorage.removeItem(LEGACY_ONBOARDING_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (step === PASSWORD || step === SUCCESS) return;
    try {
      const persistedStep = step >= ABOUT && step <= AI_PROVIDER ? step - 1 : step;
      const draft = createOnboardingDraft({
        step: persistedStep, candidate, search, locations, compensation, skills, domains, proofPoints,
        selectedLocale, llm, rolesSkipped, skillsSkipped, aiSetupLater,
        enabledBoardIds: [...enabledBoards], scrapeIntervalHours,
      });
      localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(draft));
    } catch {}
  }, [
    step, candidate, search, locations, compensation, skills, domains, proofPoints,
    selectedLocale, llm, rolesSkipped, skillsSkipped, aiSetupLater, enabledBoards,
    scrapeIntervalHours,
  ]);

  useEffect(() => {
    if (step === WELCOME || step === SUCCESS) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [step]);

  useEffect(() => {
    fetchLocales()
      .then(setLocales)
      .catch(() => {})
      .finally(() => setLoadingLocales(false));
  }, []);

  useEffect(() => {
    getAppLockStatus()
      .then((status) => {
        setPasswordPolicy(status.password_policy);
        setPasswordRequired(status.enabled && status.configured_source === "none");
      })
      .catch(() => {
        setPasswordRequired(false);
      });
  }, []);

  useEffect(() => {
    fetchLocaleLegalFields(selectedLocale)
      .then((fields) => {
        setLegalFields(fields);
        const defaults: Record<string, string> = {};
        fields.forEach((field) => { defaults[field.id] = field.default; });
        setCompensation((previous) => ({ ...previous, legal_preferences: defaults }));
      })
      .catch(() => setLegalFields([]));

    fetchLocaleBoards(selectedLocale)
      .then((nextBoards) => {
        setBoards(nextBoards);
        const validBoardIds = new Set(nextBoards.map((board) => board.id));
        const restored = restoredBoardIds.current?.filter((id) => validBoardIds.has(id));
        setEnabledBoards(new Set(
          restored?.length
            ? restored
            : nextBoards.filter((board) => board.enabled).map((board) => board.id),
        ));
        restoredBoardIds.current = null;
      })
      .catch(() => setBoards([]));

    const localePack = locales.find((locale) => locale.id === selectedLocale);
    if (localePack) {
      setCompensation((previous) => ({
        ...previous,
        currency: localePack.currency || previous.currency,
        rate_type: localePack.default_rate_type || previous.rate_type,
      }));
    }
  }, [selectedLocale, locales]);

  const validationState = {
    candidate, search, locations, compensation, skills,
    rolesSkipped, skillsSkipped, aiSetupLater,
  };

  const advance = () => {
    if (step === WELCOME) {
      setError("");
      setStep(passwordRequired ? PASSWORD : ABOUT);
      return;
    }
    if (
      step >= ABOUT
      && step <= AI_PROVIDER
      && getOnboardingStepErrors(step - 1, validationState).length > 0
    ) {
      setTried(true);
      return;
    }
    setTried(false);
    setError("");
    setStep((current) => current + 1);
  };

  const back = () => {
    setTried(false);
    setError("");
    setStep((current) => {
      if (current === ABOUT) return passwordRequired ? PASSWORD : WELCOME;
      return Math.max(WELCOME, current - 1);
    });
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setConnectionResult(null);
    const result = await testLLMConnection(llm.provider, "").catch((caught: unknown) => ({
      ok: false,
      error: caught instanceof Error ? caught.message : "Unknown error",
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
    proof_points: proofPoints.filter((point) => point.summary.trim()),
    master_cv_path: "./data/master_cv.json",
    job_boards: boards.map((board) => ({
      name: board.name,
      enabled: enabledBoards.has(board.id),
      scraper: board.scraper,
      search_params: {},
    })),
    scoring: {
      weights: {
        skill_match: 0.35,
        experience_match: 0.30,
        rate_match: 0.20,
        location_match: 0.15,
      },
      shortlist_threshold: 0.75,
    },
    llm,
    preferences: {
      scrape_interval_hours: scrapeIntervalHours,
      max_tailor_batch: 5,
      follow_up_days: [5, 10, 15],
      locale: "en-GB",
      archive_after_days: 30,
    },
  });

  const handleFinish = async () => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await saveProfile(buildProfile());
      await triggerAgent("scout").catch(() => {});
      try {
        localStorage.removeItem(ONBOARDING_STORAGE_KEY);
        localStorage.removeItem(LEGACY_ONBOARDING_STORAGE_KEY);
      } catch {}
      setStep(SUCCESS);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Profile could not be saved.");
      setSaving(false);
    }
  };

  const currentLocale = locales.find((locale) => locale.id === selectedLocale);
  const formStep = step >= ABOUT && step <= AI_PROVIDER ? step - 1 : 0;
  const warnings = getOnboardingWarnings(validationState);

  return (
    <div
      data-onboarding="true"
      className="min-h-[100dvh] overflow-y-auto"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <div className="mx-auto flex min-h-[100dvh] w-full max-w-2xl flex-col">
        <header className="flex items-center justify-between px-5 pt-4">
          <div className="flex items-center gap-2">
            <div
              className="grid h-6 w-6 place-items-center rounded-[7px] text-[13px] font-extrabold text-[var(--bg)]"
              style={{ background: "var(--text)" }}
            >
              H
            </div>
            <span className="text-[14px] font-semibold tracking-[-0.02em] text-[var(--text)]">
              Hatch
            </span>
          </div>
          {step >= ABOUT && step <= AI_PROVIDER && (
            <span className="text-[12px] tabular-nums text-[var(--text-muted)]">
              <strong className="text-[var(--text)]">{formStep}</strong> of {PROFILE_FORM_STEPS}
            </span>
          )}
          {step === PASSWORD && (
            <span className="text-[12px] font-medium text-[var(--text-muted)]">Password</span>
          )}
          {step === REVIEW && (
            <span className="text-[12px] font-medium text-[var(--text-muted)]">Final review</span>
          )}
        </header>

        <OnboardingProgress formStep={formStep} />

        <div className="flex-1 overflow-y-auto">
          {step === WELCOME && <ScreenWelcome hasSaved={hasSaved} onStart={advance} />}
          {step === PASSWORD && (
            <StepPasswordSetup
              onComplete={() => setStep(ABOUT)}
              policy={passwordPolicy}
            />
          )}
          {step === ABOUT && (
            <StepAboutYou candidate={candidate} onChange={setCandidate} tried={tried} />
          )}
          {step === MARKET && (
            <StepMarket
              selectedLocale={selectedLocale}
              locales={locales}
              loadingLocales={loadingLocales}
              onLocaleChange={setSelectedLocale}
              search={search}
              onSearchChange={setSearch}
              tried={tried}
              rolesSkipped={rolesSkipped}
              onRolesSkippedChange={setRolesSkipped}
            />
          )}
          {step === PAY && (
            <StepPay
              locale={currentLocale}
              locations={locations}
              onLocationsChange={setLocations}
              compensation={compensation}
              onCompensationChange={setCompensation}
              tried={tried}
            />
          )}
          {step === ELIGIBILITY && (
            <StepEligibility
              locale={currentLocale}
              legalFields={legalFields}
              compensation={compensation}
              onCompensationChange={setCompensation}
            />
          )}
          {step === SKILLS && (
            <StepSkills
              skills={skills}
              onSkillsChange={setSkills}
              domains={domains}
              onDomainsChange={setDomains}
              proofPoints={proofPoints}
              onProofPointsChange={setProofPoints}
              skillsSkipped={skillsSkipped}
              onSkillsSkippedChange={setSkillsSkipped}
              tried={tried}
            />
          )}
          {step === AI_PROVIDER && (
            <StepAIProvider
              llm={llm}
              onLlmChange={setLlm}
              testApiKey=""
              onTestApiKeyChange={() => setConnectionResult(null)}
              testingConnection={testingConnection}
              connectionResult={connectionResult}
              onTestConnection={handleTestConnection}
              boards={boards}
              enabledBoards={enabledBoards}
              onEnabledBoardsChange={setEnabledBoards}
              scrapeIntervalHours={scrapeIntervalHours}
              onScrapeIntervalChange={setScrapeIntervalHours}
              setupLater={aiSetupLater}
              onSetupLaterChange={setAiSetupLater}
            />
          )}
          {step === REVIEW && (
            <StepReview
              candidate={candidate}
              selectedLocale={selectedLocale}
              locales={locales}
              search={search}
              locations={locations}
              compensation={compensation}
              legalPreferences={compensation.legal_preferences}
              skills={skills}
              domains={domains}
              llm={llm}
              enabledBoardsCount={enabledBoards.size}
              totalBoardsCount={boards.length}
              warnings={warnings}
              error={error}
              saving={saving}
              onFinish={handleFinish}
            />
          )}
          {step === SUCCESS && (
            <ScreenSuccess
              candidate={candidate}
              selectedLocale={selectedLocale}
              locales={locales}
              targetRolesCount={search.target_roles.length}
              minRate={compensation.min_rate}
              providerName={LLM_PROVIDERS.find((provider) => provider.id === llm.provider)?.label ?? llm.provider}
              enabledBoardsCount={enabledBoards.size}
              onDashboard={() => router.push("/?firstRun=true")}
            />
          )}
        </div>

        {step >= ABOUT && step <= REVIEW && (
          <footer
            className="flex flex-shrink-0 gap-2.5 border-t border-[var(--border)] px-5 py-3.5"
            style={{
              background: "var(--bg)",
              paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 14px)",
            }}
          >
            <button
              type="button"
              onClick={back}
              disabled={saving}
              className="min-h-11 px-3.5 text-[14px] font-semibold text-[var(--text-dim)] transition-colors hover:text-[var(--text)] disabled:opacity-50"
            >
              <ChevronLeft className="mr-0.5 inline h-4 w-4" aria-hidden="true" />
              Back
            </button>
            {step <= AI_PROVIDER && (
              <button
                type="button"
                onClick={advance}
                className="min-h-11 flex-1 rounded-[var(--radius-control)] px-4 text-[14px] font-semibold text-[var(--on-accent)] transition-opacity hover:opacity-90"
                style={{ background: "var(--accent)" }}
              >
                {step === AI_PROVIDER ? "Review setup" : "Continue"}
              </button>
            )}
          </footer>
        )}

        {step >= ABOUT && step < SUCCESS && (
          <div className="flex items-center justify-center gap-1.5 px-5 pb-3 text-center text-[11px] text-[var(--text-muted)]">
            <LockKeyhole size={12} aria-hidden="true" />
            Progress and non-sensitive preferences are saved in this browser.
          </div>
        )}
      </div>
    </div>
  );
}
