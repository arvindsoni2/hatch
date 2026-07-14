"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, LockKeyhole } from "lucide-react";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  APP_LOCK_QUERY_KEY, triggerAgent, getAppLockStatus, finalizeOnboarding,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard, type PasswordPolicy,
} from "@/lib/api";
import {
  createOnboardingDraft,
  migrateLegacyOnboardingDraft,
  ONBOARDING_STORAGE_KEY,
  restoreOnboardingDraft,
} from "@/lib/onboardingDraft";
import { Button } from "@/components/ui/button";
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
import { StepReview } from "@/components/onboarding/StepReview";
import { AiCapabilitiesForm } from "@/components/setup/AiCapabilitiesForm";
import type { SetupIntent } from "@/lib/setup";
import type {
  SearchData, LocationData, CompensationData,
} from "@/components/onboarding/StepJobSearch";

const WELCOME = 0;
const ABOUT = 1;
const MARKET = 2;
const PAY = 3;
const ELIGIBILITY = 4;
const SKILLS = 5;
const EXPERIENCE = 6;
const REVIEW = 8;
const PROTECT_WORKSPACE = 9;
const SUCCESS = 10;
const PROFILE_FORM_STEPS = 6;
const FINALIZATION_ID_KEY = "hatch_onboarding_finalization_id";

type LLMData = {
  provider: string;
  triage_model: string;
  primary_model: string;
  api_key_env: string;
  base_url: string | null;
  triage_base_url: string;
  temperature: number;
  max_retries: number;
  track_costs: boolean;
  monthly_budget: number;
  currency: string;
};

type ExperienceChoice = {
  experience: "essential" | "full_ai" | "custom";
  aiMode: "ai-later" | "cloud" | "local" | "advanced";
  backendProfile: "core" | "browser" | "local-embeddings" | "full";
  acknowledgement: boolean;
};

const DEFAULT_LLM: LLMData = {
  provider: "llamacpp",
  triage_model: "",
  primary_model: "",
  api_key_env: "",
  base_url: "http://llm-primary:8080/v1",
  triage_base_url: "http://llm-triage:8081/v1",
  temperature: 0.3,
  max_retries: 3,
  track_costs: false,
  monthly_budget: 0,
  currency: "USD",
};

const DEFAULT_EXPERIENCE: ExperienceChoice = {
  experience: "essential",
  aiMode: "ai-later",
  backendProfile: "core",
  acknowledgement: true,
};

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(WELCOME);
  const [hasSaved, setHasSaved] = useState(false);
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [rolesSkipped, setRolesSkipped] = useState(false);
  const [skillsSkipped, setSkillsSkipped] = useState(false);
  const [aiSetupLater, setAiSetupLater] = useState(false);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [passwordConfigured, setPasswordConfigured] = useState(false);
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
  const [experienceChoice, setExperienceChoice] = useState<ExperienceChoice>(DEFAULT_EXPERIENCE);
  const [setupIntent, setSetupIntent] = useState<SetupIntent | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);
  const restoredBoardIds = useRef<string[] | null>(null);
  const finalizationIdRef = useRef("");

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(ONBOARDING_STORAGE_KEY);
      const draft = raw
        ? restoreOnboardingDraft(JSON.parse(raw))
        : migrateLegacyOnboardingDraft();
      if (draft) {
        if (draft.search) setSearch(draft.search);
        if (draft.skills) setSkills(draft.skills);
        if (draft.domains) setDomains(draft.domains);
        if (draft.selectedLocale) setSelectedLocale(draft.selectedLocale);
        if (draft.llm) {
          setLlm(draft.llm.provider === "ollama" ? DEFAULT_LLM : draft.llm);
        }
        if (draft.experienceChoice) {
          setExperienceChoice(draft.experienceChoice);
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
            : Math.min(EXPERIENCE, Math.max(ABOUT, draft.step));
          setStep(restoredStep);
        }
        setHasSaved(true);
      }
    } catch {
      sessionStorage.removeItem(ONBOARDING_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (step === PROTECT_WORKSPACE || step === SUCCESS) return;
    try {
      const draft = createOnboardingDraft({
        step, candidate, search, locations, compensation, skills, domains, proofPoints,
        selectedLocale, llm, experienceChoice, rolesSkipped, skillsSkipped, aiSetupLater,
        enabledBoardIds: [...enabledBoards], scrapeIntervalHours,
      });
      sessionStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(draft));
    } catch {}
  }, [
    step, candidate, search, locations, compensation, skills, domains, proofPoints,
    selectedLocale, llm, experienceChoice, rolesSkipped, skillsSkipped, aiSetupLater, enabledBoards,
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
        setPasswordConfigured(status.onboarding.status === "finalization_pending");
        if (status.onboarding.status === "finalization_pending") {
          setStep(PROTECT_WORKSPACE);
        } else if (status.onboarding.status === "complete") {
          setStep(SUCCESS);
        }
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
      setStep(ABOUT);
      return;
    }
    if (
      step >= ABOUT
      && step <= SKILLS
      && getOnboardingStepErrors(step, validationState).length > 0
    ) {
      setTried(true);
      return;
    }
    if (step === EXPERIENCE && !setupIntent) {
      setError("Save an AI and capability choice, or choose Finish setup later.");
      return;
    }
    setTried(false);
    setError("");
    setStep((current) => current === EXPERIENCE ? REVIEW : current + 1);
  };

  const back = () => {
    setTried(false);
    setError("");
    setStep((current) => {
      if (current === ABOUT) return WELCOME;
      if (current === REVIEW) return EXPERIENCE;
      return Math.max(WELCOME, current - 1);
    });
  };

  const acceptSetupIntent = (intent: SetupIntent) => {
    setSetupIntent(intent);
    const cloudEnv: Record<string, string> = {
      anthropic: "ANTHROPIC_API_KEY",
      openai: "OPENAI_API_KEY",
      google_genai: "GOOGLE_API_KEY",
      openrouter: "OPENROUTER_API_KEY",
    };
    if (intent.ai_mode === "cloud" && intent.cloud_provider) {
      const provider = intent.cloud_provider;
      setLlm((current) => ({
        ...current,
        provider,
        primary_model: intent.cloud_primary_model ?? "",
        triage_model: intent.cloud_triage_model ?? "",
        api_key_env: cloudEnv[provider] ?? "",
        base_url: null,
        triage_base_url: "",
        track_costs: true,
      }));
    } else if (intent.ai_mode === "local") {
      setLlm((current) => ({
        ...current,
        provider: "llamacpp",
        primary_model: intent.local_primary_model ?? "",
        triage_model: intent.local_triage_model ?? "",
        api_key_env: "",
        base_url: "http://llm-primary:8080/v1",
        triage_base_url: "http://llm-triage:8081/v1",
        track_costs: false,
      }));
    }
    setExperienceChoice({
      experience: intent.experience,
      aiMode: intent.ai_mode === "cloud" || intent.ai_mode === "local"
        ? intent.ai_mode
        : intent.ai_mode === "custom" ? "advanced" : "ai-later",
      backendProfile: intent.backend_profile,
      acknowledgement: true,
    });
    setAiSetupLater(intent.ai_mode === "none");
    setError("");
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

  const getFinalizationId = () => {
    if (finalizationIdRef.current) return finalizationIdRef.current;
    const existing = sessionStorage.getItem(FINALIZATION_ID_KEY);
    const generated = existing
      || (typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `00000000-0000-4000-8000-${Date.now().toString(16).padStart(12, "0").slice(-12)}`);
    finalizationIdRef.current = generated;
    sessionStorage.setItem(FINALIZATION_ID_KEY, generated);
    return generated;
  };

  const handleFinalize = async () => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      const result = await finalizeOnboarding(getFinalizationId(), buildProfile());
      if (result.onboarding.status !== "complete") {
        throw new Error("The backend did not confirm onboarding completion.");
      }
      await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
      await triggerAgent("scout").catch(() => {});
      sessionStorage.removeItem(ONBOARDING_STORAGE_KEY);
      sessionStorage.removeItem(FINALIZATION_ID_KEY);
      setStep(SUCCESS);
    } catch (caught: unknown) {
      setPasswordConfigured(true);
      setStep(PROTECT_WORKSPACE);
      setError(caught instanceof Error ? caught.message : "Profile finalization failed.");
    } finally {
      setSaving(false);
    }
  };

  const handleReviewComplete = async () => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      if (passwordRequired && !passwordConfigured) {
        setStep(PROTECT_WORKSPACE);
        setSaving(false);
        return;
      }
      setSaving(false);
      await handleFinalize();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Setup choices could not be saved.");
      setSaving(false);
    }
  };

  const currentLocale = locales.find((locale) => locale.id === selectedLocale);
  const formStep = step >= ABOUT && step <= EXPERIENCE ? step : 0;
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
          {step >= ABOUT && step <= EXPERIENCE && (
            <span className="text-[12px] tabular-nums text-[var(--text-muted)]">
              <strong className="text-[var(--text)]">{formStep}</strong> of {PROFILE_FORM_STEPS}
            </span>
          )}
          {step === PROTECT_WORKSPACE && (
            <span className="text-[12px] font-medium text-[var(--text-muted)]">Protect workspace</span>
          )}
          {step === REVIEW && (
            <span className="text-[12px] font-medium text-[var(--text-muted)]">Final review</span>
          )}
        </header>

        <OnboardingProgress formStep={formStep} />

        <div className="flex-1 overflow-y-auto">
          {step === WELCOME && <ScreenWelcome hasSaved={hasSaved} onStart={advance} />}
          {step === PROTECT_WORKSPACE && !passwordConfigured && (
            <StepPasswordSetup
              onComplete={async () => {
                setPasswordConfigured(true);
                await queryClient.invalidateQueries({ queryKey: APP_LOCK_QUERY_KEY });
                await handleFinalize();
              }}
              policy={passwordPolicy}
            />
          )}
          {step === PROTECT_WORKSPACE && passwordConfigured && (
            <section className="px-5 py-8" aria-labelledby="finalization-recovery-title">
              <LockKeyhole className="h-8 w-8 text-[var(--accent)]" aria-hidden="true" />
              <h1 id="finalization-recovery-title" className="mt-4 text-2xl font-semibold text-[var(--text)]">
                Finish saving your setup
              </h1>
              <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
                Your workspace password is already configured. Retry the final profile save without entering it again.
              </p>
              {error ? <p className="mt-4 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
              <Button className="mt-6 w-full" loading={saving} onClick={handleFinalize} type="button">
                Retry finalization
              </Button>
            </section>
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
          {step === EXPERIENCE && (
            <section className="px-5 pb-5" aria-labelledby="ai-capabilities-title">
              <h1 className="mb-2 text-3xl font-semibold text-[var(--text)]" id="ai-capabilities-title">AI & capabilities</h1>
              <p className="mb-5 text-sm text-[var(--text-muted)]">Choose independently. Local model discovery appears only when Local is selected.</p>
              <AiCapabilitiesForm context="onboarding" onSaved={acceptSetupIntent} />
              {error ? <p className="mt-3 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
            </section>
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
              onFinish={handleReviewComplete}
            />
          )}
          {step === SUCCESS && (
            <ScreenSuccess
              candidate={candidate}
              selectedLocale={selectedLocale}
              locales={locales}
              targetRolesCount={search.target_roles.length}
              minRate={compensation.min_rate}
              providerName={setupIntent?.ai_mode === "none" ? "No AI" : llm.provider}
              enabledBoardsCount={enabledBoards.size}
              onDashboard={() => router.push("/?firstRun=true")}
            />
          )}
        </div>

        {step >= ABOUT && step <= PROTECT_WORKSPACE && (
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
            {step <= EXPERIENCE && (
              <button
                type="button"
                onClick={advance}
                className="min-h-11 flex-1 rounded-[var(--radius-control)] px-4 text-[14px] font-semibold text-[var(--on-accent)] transition-opacity hover:opacity-90"
                style={{ background: "var(--accent)" }}
              >
                {step === EXPERIENCE ? "Review setup" : "Continue"}
              </button>
            )}
          </footer>
        )}

        {step >= ABOUT && step < SUCCESS && (
          <div className="flex items-center justify-center gap-1.5 px-5 pb-3 text-center text-[11px] text-[var(--text-muted)]">
            <LockKeyhole size={12} aria-hidden="true" />
            Progress and non-sensitive preferences are kept for this browser session only.
          </div>
        )}
      </div>
    </div>
  );
}
