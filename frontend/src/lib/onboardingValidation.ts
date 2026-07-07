interface OnboardingValidationState {
  candidate: { name: string; title: string };
  search: { target_roles: string[] };
  locations: Array<{ city: string }>;
  compensation: { min_rate: number; max_rate: number };
  skills: { primary: string[] };
  rolesSkipped: boolean;
  skillsSkipped: boolean;
  aiSetupLater: boolean;
}

export function getOnboardingStepErrors(
  step: number,
  state: OnboardingValidationState,
): string[] {
  if (step === 1) {
    return [
      !state.candidate.name.trim() ? "Full name is required." : "",
      !state.candidate.title.trim() ? "Current or target title is required." : "",
    ].filter(Boolean);
  }

  if (step === 2 && state.search.target_roles.length === 0 && !state.rolesSkipped) {
    return ["Add at least one target role or choose to add roles later."];
  }

  if (step === 3) {
    return [
      !state.locations[0]?.city.trim() ? "City is required." : "",
      state.compensation.min_rate <= 0 ? "Minimum rate must be greater than zero." : "",
      state.compensation.max_rate > 0
        && state.compensation.max_rate < state.compensation.min_rate
        ? "Maximum rate must be greater than or equal to minimum rate."
        : "",
    ].filter(Boolean);
  }

  if (step === 5 && state.skills.primary.length === 0 && !state.skillsSkipped) {
    return ["Add at least one core skill or choose to add skills later."];
  }

  return [];
}

export function getOnboardingWarnings(state: OnboardingValidationState): string[] {
  const warnings: string[] = [];

  if (state.rolesSkipped || state.search.target_roles.length === 0) {
    warnings.push("No target roles yet. Job discovery will be broad until you add them.");
  }
  if (state.skillsSkipped || state.skills.primary.length === 0) {
    warnings.push("No core skills yet. Match scores will be less precise until you add them.");
  } else if (state.skills.primary.length < 5) {
    warnings.push("Fewer than five core skills. Adding more will improve match quality.");
  }
  if (state.aiSetupLater) {
    warnings.push("AI-assisted tailoring and coaching will be limited until a provider is configured.");
  }

  return warnings;
}
