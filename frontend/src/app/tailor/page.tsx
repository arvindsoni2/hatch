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
  JDAnalysisResponse,
  GeneratedDocument,
  TailorProgressEvent,
} from "@/lib/api";
import { Loader2, Zap, FileText, Download, ChevronRight } from "lucide-react";

type Stage = "idle" | "analysing" | "analysed" | "generating" | "complete" | "error";

interface ProgressStep {
  stage: string;
  pct: number;
  message: string;
}

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

  const handleAnalyse = useCallback(async () => {
    if (!jdText.trim() && !jobUrl.trim()) return;
    setStage("analysing");
    setError(null);
    setAnalysis(null);
    try {
      const result = await analyseJdText(jdText, jobUrl || undefined);
      setAnalysis(result);
      setStage("analysed");
      setActiveTab("analysis");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setStage("error");
    }
  }, [jdText, jobUrl]);

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

    const cleanup = streamTailoringProgress(
      applicationId,
      jdText,
      variant,
      (event: TailorProgressEvent) => {
        setProgress({ stage: event.stage, pct: event.pct, message: event.message });
      },
      async () => {
        setStage("complete");
        setActiveTab("history");
        // Refresh document history
        try {
          const docs = await getDocumentHistory(applicationId);
          setDocuments(docs);
        } catch {
          // Non-fatal
        }
      },
      (err: Error) => {
        setError(err.message);
        setStage("error");
      },
    );

    return cleanup;
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
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Tailor</h1>
          <p className="mt-1 text-sm text-slate-400">
            AI-powered CV and cover letter generation — 3-stage Claude pipeline with ATS optimisation
          </p>
        </div>

        <div className="grid grid-cols-2 gap-6 lg:grid-cols-2">
          {/* ── LEFT: Input Panel ── */}
          <div className="space-y-4">
            {/* JD Input */}
            <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                Job Description
              </h2>
              <textarea
                className="mb-3 w-full rounded-lg border border-slate-600 bg-slate-700 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                rows={10}
                placeholder="Paste the full job description here..."
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
              />
              <input
                type="url"
                className="mb-3 w-full rounded-lg border border-slate-600 bg-slate-700 p-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                placeholder="Or paste a job URL (optional)"
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
              />
              <Button
                onClick={handleAnalyse}
                disabled={stage === "analysing" || (!jdText.trim() && !jobUrl.trim())}
                className="w-full bg-indigo-600 hover:bg-indigo-700"
              >
                {stage === "analysing" ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analysing...</>
                ) : (
                  <>Analyse JD <ChevronRight className="ml-1 h-4 w-4" /></>
                )}
              </Button>
            </div>

            {/* Generation Controls */}
            <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                Generate Documents
              </h2>
              <div className="mb-3 space-y-2">
                <input
                  type="text"
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 p-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                  placeholder="Application ID (from Tracker)"
                  value={applicationId}
                  onChange={(e) => setApplicationId(e.target.value)}
                />
                <div className="flex gap-2">
                  {(["A", "B"] as const).map((v) => (
                    <button
                      key={v}
                      onClick={() => setVariant(v)}
                      className={`flex-1 rounded-lg border py-1.5 text-sm font-medium transition-colors ${
                        variant === v
                          ? "border-indigo-500 bg-indigo-600 text-white"
                          : "border-slate-600 bg-slate-700 text-slate-400 hover:border-slate-500"
                      }`}
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
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700"
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
                  className="border-slate-600 text-slate-300"
                >
                  <FileText className="h-4 w-4" />
                </Button>
              </div>

              {/* SSE Progress */}
              {stage === "generating" && progress && (
                <div className="mt-4">
                  <div className="mb-2 flex justify-between text-xs text-slate-400">
                    <span>{progress.message}</span>
                    <span>{progress.pct}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                      style={{ width: `${progress.pct}%` }}
                    />
                  </div>
                </div>
              )}

              {stage === "complete" && (
                <div className="mt-3 rounded-lg bg-emerald-900/30 p-3 text-center text-sm text-emerald-400">
                  ✓ Documents generated successfully
                </div>
              )}
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg border border-red-700 bg-red-900/20 p-3 text-sm text-red-300">
                {error}
              </div>
            )}
          </div>

          {/* ── RIGHT: Results Panel ── */}
          <div className="space-y-4">
            {/* Tabs */}
            <div className="flex rounded-lg border border-slate-700 bg-slate-800 p-1">
              {(["analysis", "history"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 rounded-md py-1.5 text-sm font-medium capitalize transition-colors ${
                    activeTab === tab
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {tab === "analysis" ? "JD Analysis" : "Documents"}
                </button>
              ))}
            </div>

            {/* Analysis Tab */}
            {activeTab === "analysis" && analysis && (
              <div className="space-y-4">
                {/* Role info */}
                <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                    Role Overview
                  </h3>
                  <p className="text-lg font-bold text-white">{analysis.analysis.role_title}</p>
                  {analysis.analysis.seniority_level && (
                    <p className="text-sm text-slate-400">{analysis.analysis.seniority_level}</p>
                  )}
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    {analysis.analysis.contract_details.rate_range && (
                      <div className="rounded-lg bg-slate-700/50 p-2">
                        <p className="text-xs text-slate-500">Rate</p>
                        <p className="text-sm font-medium text-emerald-400">
                          {analysis.analysis.contract_details.rate_range}
                        </p>
                      </div>
                    )}
                    {analysis.analysis.contract_details.ir35_status && (
                      <div className="rounded-lg bg-slate-700/50 p-2">
                        <p className="text-xs text-slate-500">Contract status</p>
                        <p className="text-sm font-medium text-slate-200">
                          {analysis.analysis.contract_details.ir35_status}
                        </p>
                      </div>
                    )}
                    {analysis.analysis.contract_details.location && (
                      <div className="rounded-lg bg-slate-700/50 p-2">
                        <p className="text-xs text-slate-500">Location</p>
                        <p className="text-sm font-medium text-slate-200">
                          {analysis.analysis.contract_details.location}
                        </p>
                      </div>
                    )}
                    {analysis.analysis.contract_details.duration && (
                      <div className="rounded-lg bg-slate-700/50 p-2">
                        <p className="text-xs text-slate-500">Duration</p>
                        <p className="text-sm font-medium text-slate-200">
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
                  <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
                    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                      Must-Have Requirements
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {analysis.analysis.requirements.must_have.map((req) => (
                        <span
                          key={req}
                          className="rounded-full border border-indigo-700 bg-indigo-900/30 px-2.5 py-0.5 text-xs text-indigo-300"
                        >
                          {req}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* ATS Keywords */}
                <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                    ATS Keywords
                  </h3>
                  {(["technical", "methodologies", "domain", "certifications"] as const).map((cat) => {
                    const kws = analysis.analysis.ats_keywords[cat];
                    if (!kws.length) return null;
                    return (
                      <div key={cat} className="mb-2">
                        <p className="mb-1 text-xs capitalize text-slate-500">{cat}</p>
                        <div className="flex flex-wrap gap-1">
                          {kws.map((kw) => (
                            <span
                              key={kw}
                              className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
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
              <div className="rounded-xl border border-slate-700 bg-slate-800 p-12 text-center">
                <FileText className="mx-auto mb-3 h-10 w-10 text-slate-600" />
                <p className="text-sm text-slate-500">
                  Paste a job description and click Analyse JD to get started.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
