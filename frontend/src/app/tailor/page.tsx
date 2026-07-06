"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ATSScoreCard } from "@/components/ATSScoreCard";
import { SkillMatchMatrix } from "@/components/SkillMatchMatrix";
import { DocumentHistory } from "@/components/DocumentHistory";
import {
  analyseJdText,
  generateAll,
  getDocumentHistory,
  listTailorHistory,
  fetchResumeTemplates,
  fetchTailoringReview,
  fetchQualityPrecheck,
  type TailoringReview,
  type JDAnalysisResponse,
  type AsyncJobResponse,
  GeneratedDocument,
  type ResumeDesignSettings,
} from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { ProfileSummaryCard } from "@/components/ProfileSummaryCard";
import { TailoringReviewPanel } from "@/components/TailoringReviewPanel";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { CheckCircle2, ChevronRight, Clock, ExternalLink, FileText, Loader2, XCircle, Zap } from "lucide-react";
import { ResumeStudio } from "@/components/tailor/ResumeStudio";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

type Stage = "idle" | "analysing" | "analysed" | "generating" | "complete" | "error";

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

function synthesiseJdText(r: JDAnalysisResponse): string {
  const a = r.analysis;
  const parts: string[] = [`Role: ${a.role_title}`];
  if (a.seniority_level) parts.push(`Level: ${a.seniority_level}`);
  if (a.requirements.must_have.length)
    parts.push(`\nRequired:\n${a.requirements.must_have.map((x) => `- ${x}`).join("\n")}`);
  if (a.requirements.nice_to_have.length)
    parts.push(`\nNice to have:\n${a.requirements.nice_to_have.map((x) => `- ${x}`).join("\n")}`);
  const kws = [
    ...a.ats_keywords.technical,
    ...a.ats_keywords.methodologies,
    ...a.ats_keywords.domain,
    ...a.ats_keywords.certifications,
    ...a.ats_keywords.soft_skills,
  ];
  if (kws.length) parts.push(`\nKey skills: ${kws.join(", ")}`);
  if (a.responsibilities.length)
    parts.push(`\nResponsibilities:\n${a.responsibilities.slice(0, 6).map((x) => `- ${x}`).join("\n")}`);
  return parts.join("\n");
}

const LS_JD_PREFIX = "tailor_jd_";

export default function TailorPage() {
  const [jdText, setJdText] = useState("");
  const [jobUrl, setJobUrl] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("jobUrl") ?? "";
  });
  const [variant, setVariant] = useState<"A" | "B">("A");
  const [designSettings, setDesignSettings] = useState<ResumeDesignSettings>({
    template_id: "ats_classic", page_target: "two_page", density: "standard",
    section_order_preset: "standard", accent_color: "navy", font_family: "aptos",
  });
  const { data: templateData } = useQuery({
    queryKey: ["resume-templates"],
    queryFn: fetchResumeTemplates,
  });
  useEffect(() => {
    if (templateData?.default_design_settings) setDesignSettings(templateData.default_design_settings);
  }, [templateData]);
  const selectedTemplateId = designSettings.template_id;

  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<JDAnalysisResponse | null>(null);
  const [synthJdText, setSynthJdText] = useState("");
  const [autoApplicationId, setAutoApplicationId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
  const [review, setReview] = useState<TailoringReview | null>(null);
  const [precheck, setPrecheck] = useState<{ status: string; keyword_gaps: string[] } | null>(null);
  const [activeTab, setActiveTab] = useState<"analysis" | "review" | "history">("analysis");
  const [analysisHistory, setAnalysisHistory] = useState<AsyncJobResponse<JDAnalysisResponse>[]>([]);

  const jdTextRef = useRef(jdText);
  useEffect(() => { jdTextRef.current = jdText; }, [jdText]);

  const refreshHistory = useCallback(() => {
    listTailorHistory().then(setAnalysisHistory).catch(() => {});
  }, []);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  const {
    state: analyseState,
    submit: submitAnalyse,
  } = useAsyncJob<JDAnalysisResponse>({
    onComplete: (result) => {
      setAnalysis(result);
      setSynthJdText(synthesiseJdText(result));
      setStage("analysed");
      setActiveTab("analysis");
      refreshHistory();
    },
    onError: (err) => {
      setError(err);
      setStage("error");
      refreshHistory();
    },
  });

  const {
    state: generateState,
    submit: submitGenerate,
  } = useAsyncJob<{ application_id: string; review?: TailoringReview }>({
    onComplete: async (result) => {
      const appId = result?.application_id ?? null;
      setAutoApplicationId(appId);
      setStage("complete");
      setReview(result?.review ?? null);
      setActiveTab("review");
      if (appId) {
        try {
          const [docs, persistedReview] = await Promise.all([
            getDocumentHistory(appId),
            result?.review ? Promise.resolve(result.review) : fetchTailoringReview(appId),
          ]);
          setDocuments(docs);
          setReview(persistedReview);
        } catch {
          // non-fatal
        }
      }
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
    setSynthJdText("");
    setAutoApplicationId(null);
    setStage("analysing");
    await submitAnalyse(async () => {
      const ref = await analyseJdText(jdText, jobUrl || undefined);
      try {
        localStorage.setItem(
          `${LS_JD_PREFIX}${ref.job_id}`,
          JSON.stringify({ jdText, jobUrl })
        );
      } catch {
        // localStorage might be blocked; this is not critical.
      }
      return ref;
    });
  }, [jdText, jobUrl, submitAnalyse]);

  const handleGenerate = useCallback(async () => {
    const effectiveJd = jdText.trim() || synthJdText;
    if (!effectiveJd) {
      setError("Run a JD analysis first before generating documents.");
      return;
    }
    setStage("generating");
    setError(null);
    await submitGenerate(() =>
      generateAll(effectiveJd, variant, {
        jobTitle: analysis?.analysis?.role_title ?? undefined,
        companyName: undefined,
        jobUrl: jobUrl || undefined,
        templateId: selectedTemplateId,
        designSettings,
      })
    );
  }, [jdText, jobUrl, synthJdText, variant, analysis, selectedTemplateId, designSettings, submitGenerate]);

  const handleLoadHistory = useCallback(async () => {
    const appId = autoApplicationId;
    if (!appId) return;
    try {
      const [docs, persistedReview] = await Promise.all([
        getDocumentHistory(appId),
        fetchTailoringReview(appId),
      ]);
      setDocuments(docs);
      setReview(persistedReview);
      setActiveTab("history");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    }
  }, [autoApplicationId]);

  const handleRegenerate = useCallback(async (instruction: string) => {
    const effectiveJd = jdText.trim() || synthJdText;
    if (!effectiveJd || !autoApplicationId) return;
    setStage("generating");
    await submitGenerate(() => generateAll(effectiveJd, variant, {
      applicationId: autoApplicationId,
      jobUrl: jobUrl || undefined,
      templateId: selectedTemplateId,
      designSettings,
      regenerationInstruction: instruction,
    }));
  }, [autoApplicationId, jdText, jobUrl, selectedTemplateId, designSettings, submitGenerate, synthJdText, variant]);

  const restoreAnalysis = useCallback((job: AsyncJobResponse<JDAnalysisResponse>) => {
    if (!job.result) return;
    try {
      const saved = localStorage.getItem(`${LS_JD_PREFIX}${job.id}`);
      if (saved) {
        const { jdText: savedJd, jobUrl: savedUrl } = JSON.parse(saved) as { jdText: string; jobUrl: string };
        if (savedJd) setJdText(savedJd);
        if (savedUrl) setJobUrl(savedUrl);
      }
    } catch {
      // ignore parse errors
    }
    setAnalysis(job.result);
    setSynthJdText(synthesiseJdText(job.result));
    setStage("analysed");
    setActiveTab("analysis");
    setError(null);
  }, []);

  const isAnalysing =
    stage === "analysing" ||
    analyseState.status === "pending" ||
    analyseState.status === "running";

  const canGenerate = !!(jdText.trim() || synthJdText.trim());
  useEffect(() => {
    if (!analysis) { setPrecheck(null); return; }
    fetchQualityPrecheck(analysis.analysis, designSettings).then(setPrecheck).catch(() => setPrecheck(null));
  }, [analysis, designSettings]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold" style={{ color: "var(--text)", letterSpacing: "-0.025em" }}>
            CV Studio
          </h1>
          <p className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }}>
            Turn a job description into an evidence-led CV and application pack.
          </p>
        </div>
        <Link
          href="/settings/resume"
          className="hatch-interactive inline-flex min-h-10 items-center justify-center rounded-lg border px-3 text-sm font-medium sm:justify-start"
          style={{ borderColor: "var(--border)", color: "var(--text-dim)", textDecoration: "none" }}
        >
          <FileText className="mr-2 h-4 w-4" /> Manage master CV
        </Link>
      </div>

      <ProfileSummaryCard compact />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── LEFT: Input Panel ── */}
        <div className="space-y-4">
          {/* JD Input */}
          <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>
              1. Add the job
            </h2>
            <p className="mb-4 mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              Paste the description or use the original job URL.
            </p>
            <label htmlFor="cv-studio-job-description" className="mb-1.5 block text-xs font-medium" style={{ color: "var(--text-dim)" }}>
              Job description
            </label>
            <textarea
              id="cv-studio-job-description"
              style={{ ...inputStyle, resize: "vertical" }}
              rows={10}
              placeholder="Paste the full job description"
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
            />
            <label htmlFor="cv-studio-job-url" className="mb-1.5 mt-3 block text-xs font-medium" style={{ color: "var(--text-dim)" }}>
              Job URL <span style={{ color: "var(--text-muted)" }}>(optional)</span>
            </label>
            <input
              id="cv-studio-job-url"
              type="url"
              style={inputStyle}
              placeholder="https://example.com/jobs/role"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
            />
            <Button
              onClick={handleAnalyse}
              disabled={isAnalysing || (!jdText.trim() && !jobUrl.trim())}
              className="mt-3 w-full"
              style={{ background: "var(--accent)", color: "var(--on-accent)", minHeight: 40 }}
            >
              {isAnalysing ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analysing...</>
              ) : (
                <>Analyse job <ChevronRight className="ml-1 h-4 w-4" /></>
              )}
            </Button>
          </div>

          {/* Generation Controls */}
          <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>
              2. Choose your CV
            </h2>
            <p className="mb-4 mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              Set the writing style and ATS-safe presentation for this application.
            </p>
            {!canGenerate && stage === "idle" && (
              <p className="mb-3 text-xs rounded-lg px-3 py-2" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                Analyse a job first. The completed pack will be saved to Applications.
              </p>
            )}
            <fieldset className="mb-4">
              <legend className="mb-2 text-xs font-medium" style={{ color: "var(--text-dim)" }}>Writing style</legend>
              <div className="grid grid-cols-2 gap-2">
              {(["A", "B"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVariant(v)}
                  aria-pressed={variant === v}
                  className="rounded-lg px-3 py-2 text-sm font-medium transition-colors"
                  style={{
                    border: variant === v ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: variant === v ? "var(--accent-soft)" : "var(--surface-2)",
                    color: variant === v ? "var(--accent)" : "var(--text-dim)",
                  }}
                >
                  {v === "A" ? "Formal" : "Conversational"}
                </button>
              ))}
              </div>
            </fieldset>
            <ResumeStudio data={templateData} value={designSettings} analysis={analysis}
              generated={stage === "complete"} onChange={setDesignSettings} />
            {precheck?.keyword_gaps.length ? <div className="my-3 rounded-lg p-3 text-xs" style={{ background: "var(--surface-2)", color: "var(--warning)" }}>
              Pre-generation quality check: review missing evidence for {precheck.keyword_gaps.join(", ")}.
            </div> : null}

            <div className="flex gap-2">
              <Button
                onClick={handleGenerate}
                disabled={stage === "generating" || !canGenerate}
                className="flex-1"
                style={{ background: "var(--success)", color: "#fff", minHeight: 40 }}
              >
                {stage === "generating" ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
                ) : (
                  <><Zap className="mr-2 h-4 w-4" /> Create application pack</>
                )}
              </Button>
              {autoApplicationId && (
                <Button
                  variant="outline"
                  onClick={handleLoadHistory}
                  style={{ borderColor: "var(--border)", color: "var(--text-dim)", minHeight: 40 }}
                  title="Load document history"
                >
                  <FileText className="h-4 w-4" />
                </Button>
              )}
            </div>

            {stage === "generating" && (
              <div className="mt-3 rounded-lg border p-3" style={{ background: "var(--surface-2)", borderColor: "var(--border)" }}>
                <p className="text-xs text-center" style={{ color: "var(--text)" }}>
                  Creating your CV and cover letter. This takes a few minutes.
                </p>
                <p className="mt-1 text-xs text-center" style={{ color: "var(--text-muted)" }}>
                  {generateState.status === "pending" ? "Queuing…" : "Running pipeline…"}{" "}
                  Check the <span className="font-medium">notification bell</span> when ready.
                </p>
              </div>
            )}

            {stage === "complete" && autoApplicationId && (
              <div className="mt-3 rounded-lg p-3" style={{ background: "var(--success-soft)", border: "1px solid var(--success)", color: "var(--success)" }}>
                <p className="text-sm font-medium text-center">✓ Documents generated</p>
                <p className="mt-1 text-xs text-center" style={{ color: "var(--text-muted)" }}>
                  Saved to Applications.{" "}
                  <a
                    href={PRODUCT_ROUTES.applications.href}
                    className="inline-flex items-center gap-0.5 font-medium underline"
                    style={{ color: "var(--accent)" }}
                  >
                    View application <ExternalLink className="h-3 w-3" />
                  </a>
                </p>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg p-3 text-sm" style={{ background: "var(--danger-soft)", border: "1px solid var(--danger)", color: "var(--danger)" }}>
              {error}
            </div>
          )}

          {/* Analysis history */}
          {analysisHistory.length > 0 && (
            <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                Recent job analyses
              </h2>
              <div className="space-y-1.5">
                {analysisHistory.map((job) => {
                  const isRunning = job.status === "pending" || job.status === "running";
                  const isFailed = job.status === "failed";
                  const roleTitle = job.result?.analysis?.role_title;
                  const matchPct = job.result?.skill_match?.match_pct;
                  return (
                    <button
                      key={job.id}
                      onClick={() => !isRunning && !isFailed && restoreAnalysis(job)}
                      disabled={isRunning || isFailed}
                      className="w-full text-left rounded-lg px-3 py-2.5 transition-colors"
                      style={{
                        border: "1px solid var(--border)",
                        background: "var(--surface-2)",
                        cursor: isRunning || isFailed ? "default" : "pointer",
                        opacity: isFailed ? 0.6 : 1,
                      }}
                    >
                      <div className="flex items-center gap-2">
                        {isRunning ? (
                          <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" style={{ color: "var(--accent)" }} />
                        ) : isFailed ? (
                          <XCircle className="h-3.5 w-3.5 flex-shrink-0 text-red-500" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
                        )}
                        <p className="flex-1 truncate text-sm font-medium" style={{ color: "var(--text)" }}>
                          {isRunning ? "Analysing…" : isFailed ? "Analysis failed" : (roleTitle ?? "Untitled")}
                        </p>
                        {matchPct != null && !isRunning && !isFailed && (
                          <span className={`flex-shrink-0 text-xs font-semibold ${matchPct >= 70 ? "text-emerald-600" : matchPct >= 40 ? "text-amber-500" : "text-red-500"}`}>
                            {matchPct}%
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 pl-5.5 text-xs" style={{ color: "var(--text-muted)" }}>
                        <Clock className="mr-1 inline h-3 w-3" />
                        {new Date(job.created_at).toLocaleDateString("en-GB", {
                          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                        })}
                        {!isRunning && !isFailed && " - select to restore"}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT: Results Panel ── */}
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>3. Review and create</h2>
            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              Check the match evidence, then create and review the finished documents.
            </p>
          </div>
          {/* Tabs */}
          <div className="flex rounded-lg p-1" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            {(["analysis", "review", "history"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="flex-1 rounded-md py-1.5 text-sm font-medium capitalize transition-colors"
                style={{
                  background: activeTab === tab ? "var(--accent)" : "transparent",
                  color: activeTab === tab ? "var(--on-accent)" : "var(--text-dim)",
                }}
              >
                {tab === "analysis" ? "Job analysis" : tab === "review" ? "Review" : "Documents"}
              </button>
            ))}
          </div>

          {/* Analysis Tab */}
          {activeTab === "analysis" && analysis && (
            <div className="space-y-4">
              {/* Role overview */}
              <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  Role overview
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
                    Essential requirements
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
                  ATS keywords
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
          {activeTab === "review" && (
            <TailoringReviewPanel review={review} regenerating={stage === "generating"} onRegenerate={handleRegenerate} />
          )}

          {/* Empty state */}
          {activeTab === "analysis" && !analysis && !isAnalysing && (
            <div className="rounded-xl p-12 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <FileText className="mx-auto mb-3 h-10 w-10" style={{ color: "var(--border-strong)" }} />
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Add a job description, then select Analyse job to get started.
              </p>
              {analysisHistory.length > 0 && (
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  Or click a recent analysis on the left to restore it.
                </p>
              )}
            </div>
          )}

          {/* Analysing spinner */}
          {activeTab === "analysis" && isAnalysing && (
            <div className="rounded-xl p-12 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin" style={{ color: "var(--accent)" }} />
              <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                {analyseState.status === "pending" ? "Queuing analysis…" : "Extracting requirements…"}
              </p>
              <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                Results usually appear in 1-3 minutes. You can navigate away. The{" "}
                <span className="font-medium" style={{ color: "var(--text)" }}>notification bell</span>{" "}
                will alert you when done.
              </p>
            </div>
          )}

          {/* ATS score card */}
          {stage === "complete" && documents.length > 0 && (() => {
            const cv = documents.find((d) => d.document_type === "cv");
            return cv?.ats_score != null ? <ATSScoreCard score={cv.ats_score} /> : null;
          })()}
        </div>
      </div>
    </div>
  );
}
