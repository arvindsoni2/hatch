"use client";

import { CheckCircle2, Cpu, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

export type HatchExperience = "essential" | "full_ai" | "custom";
export type HatchAiModeChoice = "ai-later" | "cloud" | "local" | "advanced";
export type HatchBackendProfile = "core" | "browser" | "local-embeddings" | "full";

export interface ExperienceChoice {
  experience: HatchExperience;
  aiMode: HatchAiModeChoice;
  backendProfile: HatchBackendProfile;
  acknowledgement: boolean;
}

interface StepExperienceChoiceProps {
  value: HatchExperience;
  onChange: (choice: ExperienceChoice) => void;
}

const CHOICES: Array<{
  title: string;
  button: string;
  description: string;
  icon: typeof CheckCircle2;
  choice: ExperienceChoice;
}> = [
  {
    title: "Essential",
    button: "Use Essential",
    description: "Start with tracking, profile setup, applications, CV Studio, and settings. AI can be added later.",
    icon: CheckCircle2,
    choice: {
      experience: "essential",
      aiMode: "ai-later",
      backendProfile: "core",
      acknowledgement: true,
    },
  },
  {
    title: "Full AI",
    button: "Check this computer",
    description: "Prepare the backend profile for browser, local embeddings, and advanced AI workflows.",
    icon: Cpu,
    choice: {
      experience: "full_ai",
      aiMode: "ai-later",
      backendProfile: "full",
      acknowledgement: false,
    },
  },
  {
    title: "Custom",
    button: "Customise capabilities",
    description: "Keep the setup explicit if you want to enable capabilities one group at a time.",
    icon: SlidersHorizontal,
    choice: {
      experience: "custom",
      aiMode: "ai-later",
      backendProfile: "browser",
      acknowledgement: false,
    },
  },
];

export function StepExperienceChoice({ value, onChange }: StepExperienceChoiceProps) {
  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="mb-2 text-[11px] font-[600] uppercase tracking-[0.1em] text-[var(--text-dim)]">
        Hatch setup
      </p>
      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        Choose your Hatch experience
      </h1>
      <p className="mb-4 text-[14px] leading-[1.5] text-[var(--text-dim)]">
        Pick the product shape first. Provider secrets, model downloads, and backend capabilities stay controlled from the host.
      </p>

      <div className="grid gap-3">
        {CHOICES.map(({ title, button, description, icon: Icon, choice }) => {
          const active = value === choice.experience;
          return (
            <article
              className={cn(
                "rounded-[var(--radius-card)] border bg-[var(--surface)] p-4 transition-colors",
                active ? "border-[var(--accent)]" : "border-[var(--border)]",
              )}
              key={choice.experience}
            >
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[var(--radius-control)] bg-[var(--accent-soft)] text-[var(--accent)]">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="font-semibold text-[var(--text)]">{title}</h2>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--text-muted)]">{description}</p>
                  <button
                    type="button"
                    className={cn(
                      "mt-3 min-h-10 rounded-[var(--radius-control)] px-3 text-sm font-semibold transition-opacity hover:opacity-90",
                      active
                        ? "bg-[var(--accent)] text-[var(--on-accent)]"
                        : "border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)]",
                    )}
                    onClick={() => onChange(choice)}
                  >
                    {button}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-4 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface-2)] p-4 text-[12px] leading-relaxed text-[var(--text-muted)]">
        <p>Full AI does not download local models automatically.</p>
        <p className="mt-1">Cloud provider and local model setup stay separate, so no browser flow collects API keys.</p>
      </div>
    </div>
  );
}
