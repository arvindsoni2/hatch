export const ONBOARDING_STORAGE_KEY = "hatch_onboarding_v2";
export const LEGACY_ONBOARDING_STORAGE_KEY = "hatch_onboarding_v1";

type SafeSearch = {
  target_roles: string[];
  contract_type: string;
};

type SafeSkills = {
  primary: string[];
  secondary: string[];
  certifications: string[];
};

type SafeDomains = {
  preferred: string[];
  excluded: string[];
};

type SafeExperienceChoice = {
  experience: "essential" | "full_ai" | "custom";
  aiMode: "ai-later" | "cloud" | "local" | "advanced";
  backendProfile: "core" | "browser" | "local-embeddings" | "full";
  acknowledgement: boolean;
};

export interface OnboardingDraft {
  version: 2;
  step: number;
  selectedLocale: string;
  search: SafeSearch;
  skills: SafeSkills;
  domains: SafeDomains;
  experienceChoice: SafeExperienceChoice;
  rolesSkipped: boolean;
  skillsSkipped: boolean;
  aiSetupLater: boolean;
  enabledBoardIds: string[];
  scrapeIntervalHours: number;
}

interface DraftSource extends Omit<OnboardingDraft, "version" | "experienceChoice"> {
  experienceChoice?: SafeExperienceChoice;
  candidate?: unknown;
  locations?: unknown;
  compensation?: unknown;
  proofPoints?: unknown;
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" ? value as Record<string, unknown> : {};

const experience = (value: unknown): SafeExperienceChoice["experience"] => {
  if (value === "full_ai" || value === "custom") return value;
  return "essential";
};

const aiMode = (value: unknown): SafeExperienceChoice["aiMode"] => {
  if (value === "cloud" || value === "local" || value === "advanced") return value;
  return "ai-later";
};

const backendProfile = (value: unknown): SafeExperienceChoice["backendProfile"] => {
  if (value === "browser" || value === "local-embeddings" || value === "full") return value;
  return "core";
};

export function createOnboardingDraft(source: DraftSource): OnboardingDraft {
  return {
    version: 2,
    step: source.step,
    selectedLocale: source.selectedLocale,
    search: {
      target_roles: [...source.search.target_roles],
      contract_type: source.search.contract_type,
    },
    skills: {
      primary: [...source.skills.primary],
      secondary: [...source.skills.secondary],
      certifications: [...source.skills.certifications],
    },
    domains: {
      preferred: [...source.domains.preferred],
      excluded: [...source.domains.excluded],
    },
    experienceChoice: source.experienceChoice
      ? { ...source.experienceChoice }
      : {
        experience: "essential",
        aiMode: "ai-later",
        backendProfile: "core",
        acknowledgement: true,
      },
    rolesSkipped: source.rolesSkipped,
    skillsSkipped: source.skillsSkipped,
    aiSetupLater: source.aiSetupLater,
    enabledBoardIds: [...source.enabledBoardIds],
    scrapeIntervalHours: source.scrapeIntervalHours,
  };
}

export function restoreOnboardingDraft(value: unknown): Partial<OnboardingDraft> {
  const source = record(value);
  const search = record(source.search);
  const skills = record(source.skills);
  const domains = record(source.domains);
  const nextExperience = record(source.experienceChoice);

  return {
    version: 2,
    step: typeof source.step === "number" ? source.step : 0,
    selectedLocale: typeof source.selectedLocale === "string" ? source.selectedLocale : "uk",
    search: {
      target_roles: strings(search.target_roles),
      contract_type: typeof search.contract_type === "string" ? search.contract_type : "contract",
    },
    skills: {
      primary: strings(skills.primary),
      secondary: strings(skills.secondary),
      certifications: strings(skills.certifications),
    },
    domains: {
      preferred: strings(domains.preferred),
      excluded: strings(domains.excluded),
    },
    experienceChoice: {
      experience: experience(nextExperience.experience),
      aiMode: aiMode(nextExperience.aiMode),
      backendProfile: backendProfile(nextExperience.backendProfile),
      acknowledgement: nextExperience.acknowledgement === true,
    },
    rolesSkipped: source.rolesSkipped === true,
    skillsSkipped: source.skillsSkipped === true,
    aiSetupLater: source.aiSetupLater === true,
    enabledBoardIds: strings(source.enabledBoardIds),
    scrapeIntervalHours: typeof source.scrapeIntervalHours === "number"
      ? source.scrapeIntervalHours
      : 4,
  };
}


export function migrateLegacyOnboardingDraft(): Partial<OnboardingDraft> | null {
  let restored: Partial<OnboardingDraft> | null = null;
  try {
    const raw = localStorage.getItem(ONBOARDING_STORAGE_KEY)
      ?? localStorage.getItem(LEGACY_ONBOARDING_STORAGE_KEY);
    if (raw) {
      restored = restoreOnboardingDraft(JSON.parse(raw));
      sessionStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(restored));
    }
  } catch {
    restored = null;
  } finally {
    try {
      localStorage.removeItem(ONBOARDING_STORAGE_KEY);
      localStorage.removeItem(LEGACY_ONBOARDING_STORAGE_KEY);
    } catch {}
  }
  return restored;
}
