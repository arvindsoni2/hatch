"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ATSScoreCard } from "@/components/ATSScoreCard";
import { SkillMatchMatrix } from "@/components/SkillMatchMatrix";
import { DocumentHistory } from "@/components/DocumentHistory";
import {
  analyseJdText,
  streamTailoringProgress,
  getDocumentHistory,
  type JDAnalysisResponse,
  GeneratedDocument,
  TailorProgressEvent,
} from "@/lib/api";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { Loader2, Zap, FileText, ChevronRight } from "lucide-react";

type Stage = "idle" | "analysing" | "analysed" | "generating" | "complete" | "error";

interface ProgressStep {
  stage: string;
  pct: number;
  message: string;
}

const inputStyle = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text)",
  fontSize: 13,
  padding: "8px 12px",
  width: "100%",
  outline: "none",
} as const;

export default function TailorPage() {
  const [jdText, setJdText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [variant, setVariant] = useState<"A" | "B">("A");

  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<JDAnalysisResponse | null>(null);
  const [progress, setProgress] = useState<ProgressStep | null>(null);
  const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
  const [activeTab, setActiveTab] = useState<"analysis" | "history">("analysis");

  const {
    state: analyseState,
    submit: submitAnalyse,
  } = useAsyncJob<JDAnalysisResponse>({
    onComplete: (result) => {
      setAnalysis(result);
      setStage("analysed");
      setActiveTab("analysis");
    },
    onError: (err) => {
      setError(err);
      setStage("error");
    },
  });

  const handleAnalyse = useCallback(async () => {
    if (!jdText.trim() && !jobUrl.trim()) return;
    setError(null);
    setAnalysis(null);
    setStage("analysing");
    await submitAnalyse(() => analyseJdText(jdText, jobUrl || undefined));
  }, [jdText, jobUrl, submitAnalyse]);

  const handleGenerate = useCallback(() => {
    if (!applicationId.trim()) {
      setError("Please enter an Application ID to save documents to.");
      return;
    }
    if (!jdText.trim()) {
      setError("Job description is required for generation.");
      return;
    }
    setStage("generating");
    setError(null);
    setProgress({ stage: "starting", pct: 0, message: "Initialising pipeline..." });

    streamTailoringProgress(
      applicationId,
      jdText,
      variant,
      (event: TailorProgressEvent) => {
        setProgress({ stage: event.stage, pct: event.pct, message: event.message });
      },
      async () => {
        setStage("complete");
        setActiveTab("history");
        try {
          const docs = await getDocumentHistory(applicationId);
          setDocuments(docs);
        } catch {
          // non-fatal
        }
      },
      (err: Error) => {
        setError(err.message);
        setStage("error");
      },
    );
  }, [applicationId, jdText, variant]);

  const handleLoadHistory = useCallback(async () => {
    if (!applicationId.trim()) return;
    try {
      const docs = await getDocumentHistory(applicationId);
      setDocuments(docs);
      setActiveTab("history");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    }
  }, [applicationId]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-[28px] font-semibold" style={{ color: "var(--text)", letterSpacing: "-0.025em" }}>
          Resume tailoring
        </h1>
        <p className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }}>
          AI-powered CV and cover letter generation with ATS optimisation
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── LEFT: Input Panel ── */}
        <div className="space-y-4">
          {/* JD Input */}
          <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Job Description
            </h2>
            <textarea
              style={{ ...inputStyle, resize: "vertical" }}
              rows={10}
              placeholder="Paste the full job description here..."
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
            />
            <input
              type="url"
              style={{ ...inputStyle, marginTop: 8 }}
              placeholder="Or paste a job URL (optional)"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
            />
            {(() => {
              const isAnalysing = stage === "analysing" || analyseState.status === "pending" || analyseState.status === "running";
              return (
                <Button
                  onClick={handleAnalyse}
                  disabled={isAnalysing || (!jdText.trim() && !jobUrl.trim())}
                  className="mt-3 w-full"
                  style={{ background: "var(--accent)", color: "var(--on-accent)", minHeight: 40 }}
                >
                  {isAnalysing ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analysing...</>
                  ) : (
                    <>Analyse JD <ChevronRight className="ml-1 h-4 w-4" /></>
                  )}
                </Button>
              );
            })()}
          </div>

          {/* Generation Controls */}
          <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Generate Documents
            </h2>
            <div className="space-y-2 mb-3">
              <input
                type="text"
                style={inputStyle}
                placeholder="Application ID (from Pipeline)"
                value={applicationId}
                onChange={(e) => setApplicationId(e.target.value)}
              />
              <div className="flex gap-2">
                {(["A", "B"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setVariant(v)}
                    className="flex-1 rounded-lg py-2 text-sm font-medium transition-colors"
                    style={{
                      border: variant === v ? "1px solid var(--accent)" : "1px solid var(--border)",
                      background: variant === v ? "var(--accent-soft)" : "var(--surface-2)",
                      color: variant === v ? "var(--accent)" : "var(--text-dim)",
                    }}
                  >
                    Variant {v}
                    <span className="ml-1 text-xs opacity-60">
                      {v === "A" ? "(formal)" : "(conversational)"}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleGenerate}
                disabled={stage === "generating" || !jdText.trim()}
                className="flex-1"
                style={{ background: "var(--success)", color: "#fff", minHeight: 40 }}
              >
                {stage === "generating" ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
                ) : (
                  <><Zap className="mr-2 h-4 w-4" /> Generate All</>
                )}
              </Button>
              <Button
                variant="outline"
                onClick={handleLoadHistory}
                disabled={!applicationId.trim()}
                style={{ borderColor: "var(--border)", color: "var(--text-dim)", minHeight: 40 }}
                title="Load document history"
              >
                <FileText className="h-4 w-4" />
              </Button>
            </div>

            {/* SSE Progress */}
            {stage === "generating" && progress && (
              <div className="mt-4">
                <div className="mb-2 flex justify-between text-xs" style={{ color: "var(--text-muted)" }}>
                  <span>{progress.message}</span>
                  <span>{progress.pct}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${progress.pct}%`, background: "var(--accent)" }}
                  />
                </div>
              </div>
            )}

            {stage === "complete" && (
              <div className="mt-3 rounded-lg p-3 text-center text-sm" style={{ background: "var(--success-soft)", color: "var(--success)" }}>
                ✓ Documents generated successfully
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg p-3 text-sm" style={{ background: "var(--danger-soft)", border: "1px solid var(--danger)", color: "var(--danger)" }}>
              {error}
            </div>
          )}
        </div>

        {/* ── RIGHT: Results Panel ── */}
        <div className="space-y-4">
          {/* Tabs */}
          <div className="flex rounded-lg p-1" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            {(["analysis", "history"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="flex-1 rounded-md py-1.5 text-sm font-medium capitalize transition-colors"
                style={{
                  background: activeTab === tab ? "var(--accent)" : "transparent",
                  color: activeTab === tab ? "var(--on-accent)" : "var(--text-dim)",
                }}
              >
                {tab === "analysis" ? "JD Analysis" : "Documents"}
              </button>
            ))}
          </div>

          {/* Analysis Tab */}
          {activeTab === "analysis" && analysis && (
            <div className="space-y-4">
              {/* Role overview */}
              <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  Role Overview
                </h3>
                <p className="text-lg font-bold" style={{ color: "var(--text)" }}>{analysis.analysis.role_title}</p>
                {analysis.analysis.seniority_level && (
                  <p className="text-sm mt-0.5" style={{ color: "var(--text-dim)" }}>{analysis.analysis.seniority_level}</p>
                )}
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {analysis.analysis.contract_details.rate_range && (
                    <div className="rounded-lg p-2" style={{ background: "var(--surface-2)" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Rate</p>
                      <p className="text-sm font-medium" style={{ color: "var(--success)" }}>
                        {analysis.analysis.contract_details.rate_range}
                      </p>
                    </div>
                  )}
                  {analysis.analysis.contract_details.ir35_status && (
                    <div className="rounded-lg p-2" style={{ background: "var(--surface-2)" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Contract status</p>
                      <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                        {analysis.analysis.contract_details.ir35_status}
                      </p>
                    </div>
                  )}
                  {analysis.analysis.contract_details.location && (
                    <div className="rounded-lg p-2" style={{ background: "var(--surface-2)" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Location</p>
                      <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                        {analysis.analysis.contract_details.location}
                      </p>
                    </div>
                  )}
                  {analysis.analysis.contract_details.duration && (
                    <div className="rounded-lg p-2" style={{ background: "var(--surface-2)" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Duration</p>
                      <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                        {analysis.analysis.contract_details.duration}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Skill match */}
              {analysis.skill_match && (
                <SkillMatchMatrix skillMatch={analysis.skill_match} />
              )}

              {/* Must-have requirements */}
              {analysis.analysis.requirements.must_have.length > 0 && (
                <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    Must-Have Requirements
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.analysis.requirements.must_have.map((req) => (
                      <span
                        key={req}
                        className="rounded-full px-2.5 py-0.5 text-xs"
                        style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-soft-strong)" }}
                      >
                        {req}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* ATS Keywords */}
              <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  ATS Keywords
                </h3>
                {(["technical", "methodologies", "domain", "certifications"] as const).map((cat) => {
                  const kws = analysis.analysis.ats_keywords[cat];
                  if (!kws.length) return null;
                  return (
                    <div key={cat} className="mb-3">
                      <p className="mb-1.5 text-xs capitalize" style={{ color: "var(--text-muted)" }}>{cat}</p>
                      <div className="flex flex-wrap gap-1">
                        {kws.map((kw) => (
                          <span
                            key={kw}
                            className="rounded px-2 py-0.5 text-xs"
                            style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
                          >
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* History Tab */}
          {activeTab === "history" && (
            <DocumentHistory documents={documents} />
          )}

          {/* Empty state */}
          {activeTab === "analysis" && !analysis && stage !== "analysing" && (
            <div className="rounded-xl p-12 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <FileText className="mx-auto mb-3 h-10 w-10" style={{ color: "var(--border-strong)" }} />
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Paste a job description and click Analyse JD to get started.
              </p>
            </div>
          )}

          {/* Analysing spinner */}
          {activeTab === "analysis" && stage === "analysing" && (
            <div className="rounded-xl p-12 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin" style={{ color: "var(--accent)" }} />
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>Analysing job description…</p>
              {(analyseState.status === "pending" || analyseState.status === "running") && (
                <p className="mt-1 text-xs text-slate-400">
                  {analyseState.status === "pending" ? "Queuing analysis…" : "Analysing job description…"}
                </p>
              )}
            </div>
          )}

          {/* ATS score card — shown after generation completes */}
          {stage === "complete" && documents.length > 0 && (() => {
            const cv = documents.find((d) => d.document_type === "cv");
            return cv?.ats_score != null ? (
              <ATSScoreCard score={cv.ats_score} />
            ) : null;
          })()}
        </div>
      </div>
    </div>
  );
}
