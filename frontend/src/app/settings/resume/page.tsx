"use client";

import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  Save,
  TriangleAlert,
  Upload,
  XCircle,
} from "lucide-react";
import { SettingsShell } from "@/components/settings/SettingsShell";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { cn } from "@/lib/utils";
import {
  confirmCv,
  fetchResumeStatus,
  uploadResume,
  type ParsePreviewResponse,
  type ResumeStatus,
} from "@/lib/api";

const API_BASE = "";
const MAX_RESUME_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Map([
  [".pdf", "application/pdf"],
  [".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
]);

type FlowStep = "select" | "uploading" | "parsing" | "review" | "confirm";

interface ExperienceEntry {
  role?: string;
  company?: string;
  period?: string;
  achievements?: Array<{ text: string } | string>;
}

interface SkillGroup {
  category?: string;
  items?: string[];
}

const SECTION_LABELS: Record<string, string> = {
  personal: "Contact information",
  summary: "Professional summary",
  experience: "Work experience",
  skills: "Skills",
  education: "Education",
  certifications: "Certifications",
};

const FLOW_STEPS: Array<{ key: FlowStep; label: string }> = [
  { key: "select", label: "Select file" },
  { key: "uploading", label: "Uploading" },
  { key: "parsing", label: "Parsing" },
  { key: "review", label: "Review extracted data" },
  { key: "confirm", label: "Confirm save" },
];

function fileExtension(filename: string) {
  const index = filename.lastIndexOf(".");
  return index >= 0 ? filename.slice(index).toLowerCase() : "";
}

function validateResumeFile(file: File): string | null {
  const extension = fileExtension(file.name);
  const expectedType = ALLOWED_TYPES.get(extension);
  if (!expectedType || file.type !== expectedType) {
    return "Only PDF and DOCX files are supported.";
  }
  if (file.size > MAX_RESUME_BYTES) {
    return "Choose a .docx or .pdf file under 10 MB.";
  }
  return null;
}

function SectionRow({ label, present }: { label: string; present: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      {present ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--success)]" aria-hidden="true" />
      ) : (
        <AlertCircle className="h-4 w-4 shrink-0 text-[var(--warning)]" aria-hidden="true" />
      )}
      <span className="text-sm text-[var(--text)]">{label}</span>
    </div>
  );
}

function FlowStepper({ activeStep }: { activeStep: FlowStep }) {
  const activeIndex = FLOW_STEPS.findIndex((step) => step.key === activeStep);
  return (
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="Master CV upload progress">
      {FLOW_STEPS.map((step, index) => {
        const complete = index < activeIndex;
        const active = index === activeIndex;
        return (
          <li
            className={cn(
              "min-h-16 rounded-[var(--radius-control)] border px-3 py-2 text-sm",
              complete ? "border-[var(--success)] bg-[var(--success-soft)] text-[var(--success)]" : null,
              active ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]" : null,
              !complete && !active ? "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)]" : null,
            )}
            key={step.key}
          >
            <span className="block text-xs font-semibold">{index + 1}</span>
            <span className="block font-medium">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function fieldWarnings(warnings: string[], section: "contact" | "experience" | "skills" | "summary") {
  return warnings.filter((warning) => {
    const lower = warning.toLowerCase();
    if (section === "skills") return lower.includes("skill");
    if (section === "experience") return lower.includes("employment") || lower.includes("experience") || lower.includes("history");
    if (section === "contact") return lower.includes("contact") || lower.includes("candidate");
    return lower.includes("summary") || lower.includes("structure");
  });
}

function WarningCallout({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <div className="mt-2 rounded-[var(--radius-control)] border border-[var(--warning)] bg-[var(--warning-soft)] px-3 py-2 text-xs text-[var(--warning)]">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <ul className="space-y-1">
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      </div>
    </div>
  );
}

function ParsePreviewCard({
  confirming,
  isReplacing,
  onCancel,
  onConfirm,
  onUploadDifferent,
  preview,
  replacementAccepted,
  setReplacementAccepted,
}: {
  confirming: boolean;
  isReplacing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onUploadDifferent: () => void;
  preview: ParsePreviewResponse;
  replacementAccepted: boolean;
  setReplacementAccepted: (accepted: boolean) => void;
}) {
  const cv = preview.parsed_cv;
  const personal = cv.personal as Record<string, string> | undefined;
  const summary = (cv.summary_variants as Record<string, string> | undefined)?.default ?? "";
  const experience = (cv.experience as ExperienceEntry[]) ?? [];
  const skills = (cv.skills as SkillGroup[]) ?? [];
  const certs = (cv.certifications as string[]) ?? [];
  const hasWarnings = preview.warnings.length > 0;
  const confirmDisabled = confirming || (isReplacing && !replacementAccepted);

  return (
    <SectionCard
      title="Review extracted data"
      description="Check the parsed profile fields before saving them as your Master CV."
      actions={<FileText className="h-5 w-5 text-[var(--text-muted)]" aria-hidden="true" />}
    >
      <div className="space-y-5">
        <div className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3">
          <p className="text-sm font-semibold text-[var(--text)]">{preview.filename}</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Hatch will only save what it can extract or what you confirm.
          </p>
        </div>

        {isReplacing ? (
          <div className="rounded-[var(--radius-control)] border border-[var(--warning)] bg-[var(--warning-soft)] px-4 py-3">
            <p className="text-sm font-medium text-[var(--warning)]">
              This will replace your current Master CV data after you confirm the parsed preview.
            </p>
            <label className="mt-3 flex items-start gap-2 text-sm text-[var(--text)]">
              <input
                checked={replacementAccepted}
                className="mt-1"
                onChange={(event) => setReplacementAccepted(event.target.checked)}
                type="checkbox"
              />
              I understand this will replace current Master CV data after I confirm save.
            </label>
          </div>
        ) : null}

        {hasWarnings ? (
          <div className="rounded-[var(--radius-control)] border border-[var(--warning)] bg-[var(--warning-soft)] px-4 py-3 text-sm text-[var(--warning)]">
            <div className="flex items-center gap-2 font-medium">
              <TriangleAlert className="h-4 w-4" aria-hidden="true" />
              {preview.warnings.length} parse warning{preview.warnings.length === 1 ? "" : "s"} need review
            </div>
          </div>
        ) : null}

        {personal ? (
          <section aria-label="Contact" className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">Contact</h3>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              {Object.entries(personal).map(([key, value]) => value ? (
                <div key={key} className="min-w-0 rounded-[var(--radius-control)] bg-[var(--surface-2)] px-3 py-2">
                  <dt className="text-xs text-[var(--text-muted)]">{key.replace("_", " ")}</dt>
                  <dd className="truncate text-[var(--text)]">{value}</dd>
                </div>
              ) : null)}
            </dl>
            <WarningCallout warnings={fieldWarnings(preview.warnings, "contact")} />
          </section>
        ) : null}

        {summary ? (
          <section aria-label="Summary" className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">Summary</h3>
            <p className="rounded-[var(--radius-control)] bg-[var(--surface-2)] px-3 py-2 text-sm leading-relaxed text-[var(--text)]">
              {summary}
            </p>
            <WarningCallout warnings={fieldWarnings(preview.warnings, "summary")} />
          </section>
        ) : null}

        {experience.length > 0 ? (
          <section aria-label="Experience" className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">Experience</h3>
            <WarningCallout warnings={fieldWarnings(preview.warnings, "experience")} />
            <div className="space-y-3">
              {experience.map((exp, index) => (
                <div key={`${exp.role ?? "role"}-${index}`} className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5">
                  <p className="text-sm font-medium text-[var(--text)]">
                    {exp.role || <span className="text-[var(--warning)]">Role missing</span>}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {exp.company || <span className="text-[var(--warning)]">Company missing</span>}
                    {exp.period ? ` - ${exp.period}` : ""}
                  </p>
                  {exp.achievements?.length ? (
                    <ul className="ml-4 mt-2 list-disc space-y-1 text-xs text-[var(--text-muted)]">
                      {exp.achievements.slice(0, 3).map((achievement, itemIndex) => (
                        <li key={itemIndex}>{typeof achievement === "string" ? achievement : achievement.text}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {skills.length > 0 ? (
          <section aria-label="Skills" className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">Skills</h3>
            <WarningCallout warnings={fieldWarnings(preview.warnings, "skills")} />
            <div className="space-y-2">
              {skills.map((group, index) => (
                <div key={`${group.category ?? "skills"}-${index}`}>
                  {group.category ? <p className="mb-1 text-xs font-medium text-[var(--text-muted)]">{group.category}</p> : null}
                  <div className="flex flex-wrap gap-1.5">
                    {(group.items ?? []).map((item) => (
                      <span key={item} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--text)]">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {certs.length > 0 ? (
          <section aria-label="Certifications" className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">Certifications</h3>
            <div className="flex flex-wrap gap-1.5">
              {certs.map((cert) => (
                <span key={cert} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--text)]">
                  {cert}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-4">
          <Button onClick={onConfirm} disabled={confirmDisabled}>
            {confirming ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
            Confirm save
          </Button>
          <Button type="button" variant="outline" onClick={onUploadDifferent}>
            <Upload className="h-4 w-4" aria-hidden="true" />
            Upload a different file
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            <XCircle className="h-4 w-4" aria-hidden="true" />
            Cancel
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}

export default function ResumePage() {
  const [status, setStatus] = useState<ResumeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<ParsePreviewResponse | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [replacementAccepted, setReplacementAccepted] = useState(false);
  const [flowStep, setFlowStep] = useState<FlowStep>("select");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const currentStatus = await fetchResumeStatus();
      setStatus(currentStatus);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const resetInput = () => {
    if (inputRef.current) inputRef.current.value = "";
  };

  const clearPreview = () => {
    setPreview(null);
    setReplacementAccepted(false);
    setConfirmError(null);
    setFlowStep("select");
    resetInput();
  };

  const handleFile = async (file: File) => {
    const validationError = validateResumeFile(file);
    if (validationError) {
      setUploadError(validationError);
      setPreview(null);
      setFlowStep("select");
      resetInput();
      return;
    }

    setUploading(true);
    setUploadError(null);
    setConfirmError(null);
    setPreview(null);
    setReplacementAccepted(false);
    setFlowStep("uploading");
    try {
      setFlowStep("parsing");
      const result = await uploadResume(file);
      setPreview(result);
      setFlowStep("review");
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
      setFlowStep("select");
    } finally {
      setUploading(false);
      resetInput();
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(true);
    setConfirmError(null);
    setFlowStep("confirm");
    try {
      const saved = await confirmCv(preview.parsed_cv, preview.filename);
      setStatus(saved);
      clearPreview();
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : "Save failed.");
      setFlowStep("review");
    } finally {
      setConfirming(false);
    }
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void handleFile(file);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files[0];
    if (file) void handleFile(file);
  };

  const hasConfirmedCv = Boolean(status?.exists);

  return (
    <SettingsShell
      activeHref="/settings/resume"
      title="Master CV"
      description="Upload the CV Hatch keeps stored locally, parsed into structured profile fields, and used for tailoring, coaching, and matching."
    >
      {loading ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5 text-sm text-[var(--text-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading Master CV…
        </div>
      ) : null}

      {!loading ? (
        <>
          <SectionCard
            title="Upload and parse"
            description="Hatch will only save what it can extract or what you confirm."
          >
            <div className="space-y-4">
              <FlowStepper activeStep={flowStep} />

              {hasConfirmedCv && !preview ? (
                <div className="rounded-[var(--radius-control)] border border-[var(--warning)] bg-[var(--warning-soft)] px-4 py-3 text-sm text-[var(--warning)]">
                  This will replace your current Master CV data after you confirm the parsed preview.
                </div>
              ) : null}

              <div
                className={cn(
                  "cursor-pointer rounded-[var(--radius-card)] border-2 border-dashed p-8 text-center transition-colors",
                  dragOver ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)]",
                  uploading ? "pointer-events-none opacity-80" : null,
                )}
                onClick={() => inputRef.current?.click()}
                onDragLeave={() => setDragOver(false)}
                onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
                onDrop={onDrop}
              >
                <input
                  accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  aria-label="Upload Master CV"
                  className="sr-only"
                  disabled={uploading}
                  onChange={onInputChange}
                  ref={inputRef}
                  type="file"
                />
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
                  {uploading ? (
                    <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="h-6 w-6" aria-hidden="true" />
                  )}
                </div>
                {uploading ? (
                  <div>
                    <p className="text-sm font-medium text-[var(--text)]">Uploading and parsing…</p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">Extracting profile fields for review.</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-medium text-[var(--text)]">Drag and drop your CV here, or click to browse</p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">PDF or DOCX, under 10 MB.</p>
                  </div>
                )}
              </div>

              {uploadError ? (
                <div className="flex items-center gap-2 rounded-[var(--radius-control)] border border-[var(--danger)] bg-[var(--danger-soft)] px-4 py-3 text-sm text-[var(--danger)]" role="alert">
                  <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {uploadError}
                </div>
              ) : null}

              {confirmError ? (
                <div className="flex items-center gap-2 rounded-[var(--radius-control)] border border-[var(--danger)] bg-[var(--danger-soft)] px-4 py-3 text-sm text-[var(--danger)]" role="alert">
                  <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {confirmError}
                </div>
              ) : null}
            </div>
          </SectionCard>

          {preview ? (
            <ParsePreviewCard
              confirming={confirming}
              isReplacing={hasConfirmedCv}
              onCancel={clearPreview}
              onConfirm={() => void handleConfirm()}
              onUploadDifferent={() => {
                clearPreview();
                inputRef.current?.click();
              }}
              preview={preview}
              replacementAccepted={replacementAccepted}
              setReplacementAccepted={setReplacementAccepted}
            />
          ) : null}

          {!preview && hasConfirmedCv && status ? (
            <SectionCard
              title="Current Master CV"
              description={status.filename ?? "master_cv.json"}
              actions={(
                <Button variant="outline" size="sm" onClick={() => void load()}>
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Refresh
                </Button>
              )}
            >
              {status.uploaded_at ? (
                <p className="mb-4 text-xs text-[var(--text-muted)]">
                  Confirmed {new Date(status.uploaded_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </p>
              ) : null}

              {status.parsed ? (
                <div className="space-y-4">
                  <div className="grid gap-x-6 sm:grid-cols-2">
                    {Object.entries(status.sections).map(([key, present]) => (
                      <SectionRow key={key} label={SECTION_LABELS[key] ?? key} present={present} />
                    ))}
                  </div>

                  <div className="grid gap-3 border-t border-[var(--border)] pt-4 sm:grid-cols-3">
                    <div>
                      <p className="text-2xl font-bold text-[var(--text)]">{status.skills_count}</p>
                      <p className="text-xs text-[var(--text-muted)]">Skills</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-[var(--text)]">{status.experience_count}</p>
                      <p className="text-xs text-[var(--text-muted)]">Experience roles</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-[var(--text)]">{status.proof_points_count}</p>
                      <p className="text-xs text-[var(--text-muted)]">Proof points</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-4">
                    <Link href="/tailor">
                      <Button size="sm">
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        Open CV Studio
                      </Button>
                    </Link>
                    <Link href="/settings/profile">
                      <Button variant="outline" size="sm">Edit proof points</Button>
                    </Link>
                  </div>

                  <details className="border-t border-[var(--border)] pt-4">
                    <summary className="cursor-pointer text-xs font-medium text-[var(--text-muted)]">Advanced</summary>
                    <a
                      className="mt-3 inline-flex items-center text-xs font-medium text-[var(--accent)]"
                      href={`${API_BASE}/api/resume/json`}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <ExternalLink className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      View CV data as JSON
                    </a>
                  </details>
                </div>
              ) : (
                <div className="text-sm text-[var(--warning)]">CV file exists but could not be parsed. Try uploading again.</div>
              )}
            </SectionCard>
          ) : null}

          {!preview && !hasConfirmedCv ? (
            <SectionCard>
              <div className="text-center">
                <AlertCircle className="mx-auto mb-2 h-6 w-6 text-[var(--warning)]" aria-hidden="true" />
                <p className="text-sm font-medium text-[var(--text)]">No Master CV confirmed</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Upload your CV above. Tailoring is available after you review and confirm the parsed data.
                </p>
              </div>
            </SectionCard>
          ) : null}
        </>
      ) : null}
    </SettingsShell>
  );
}
