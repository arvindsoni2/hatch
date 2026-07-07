"use client";

import { CheckCircle2, Clock, FileText, XCircle, Zap } from "lucide-react";

export type CVStudioStage = "idle" | "analysing" | "analysed" | "generating" | "complete" | "error";

type StepKey = "job" | "analysis" | "cv" | "pack";
type StepState = "pending" | "active" | "complete" | "error";

const STEPS: Array<{ key: StepKey; label: string; description: string }> = [
  { key: "job", label: "Add job", description: "Paste a role or job URL" },
  { key: "analysis", label: "Analyse fit", description: "Extract requirements and evidence" },
  { key: "cv", label: "Choose CV", description: "Pick template and writing style" },
  { key: "pack", label: "Create pack", description: "Generate CV and cover letter" },
];

function stateFor(step: StepKey, stage: CVStudioStage): StepState {
  if (stage === "error") return step === "pack" ? "error" : "complete";
  if (stage === "complete") return "complete";

  if (stage === "idle") return step === "job" ? "active" : "pending";
  if (stage === "analysing") {
    if (step === "job") return "complete";
    return step === "analysis" ? "active" : "pending";
  }
  if (stage === "analysed") {
    if (step === "job" || step === "analysis") return "complete";
    return step === "cv" ? "active" : "pending";
  }
  if (stage === "generating") {
    if (step === "pack") return "active";
    return "complete";
  }

  return "pending";
}

function StepIcon({ state, activeWork }: { state: StepState; activeWork: boolean }) {
  if (state === "complete") return <CheckCircle2 className="h-4 w-4" aria-hidden="true" />;
  if (state === "error") return <XCircle className="h-4 w-4" aria-hidden="true" />;
  if (activeWork) return <Zap className="h-4 w-4" aria-hidden="true" />;
  if (state === "active") return <FileText className="h-4 w-4" aria-hidden="true" />;
  return <Clock className="h-4 w-4" aria-hidden="true" />;
}

export function CVStudioProgress({ stage }: { stage: CVStudioStage }) {
  const activeWork = stage === "analysing" || stage === "generating";

  return (
    <ol aria-label="CV Studio progress" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {STEPS.map((step) => {
        const state = stateFor(step.key, stage);
        const showPulse = activeWork && state === "active";
        return (
          <li
            key={step.key}
            data-state={state}
            className="rounded-xl border p-3"
            style={{
              background: state === "active" ? "var(--accent-soft)" : "var(--surface)",
              borderColor:
                state === "error" ? "var(--danger)" : state === "active" ? "var(--accent)" : "var(--border)",
              color: state === "error" ? "var(--danger)" : state === "active" ? "var(--accent)" : "var(--text)",
            }}
          >
            <div className="flex items-start gap-3">
              <span
                className={["mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full", showPulse ? "animate-pulse" : ""].join(" ")}
                style={{
                  background: state === "complete" ? "var(--success-soft)" : "var(--surface-2)",
                  color:
                    state === "complete" ? "var(--success)" : state === "error" ? "var(--danger)" : "currentColor",
                }}
              >
                <StepIcon state={state} activeWork={showPulse} />
              </span>
              <span>
                <span className="block text-sm font-semibold">{step.label}</span>
                <span className="mt-0.5 block text-xs" style={{ color: "var(--text-muted)" }}>
                  {step.description}
                </span>
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
