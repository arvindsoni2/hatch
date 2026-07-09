"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getSession,
  submitAnswer,
  submitAudio,
  endSession,
  researchCompany,
  getAsyncJob,
  planFollowUpSession,
  getProgressTrend,
  getCoachCapabilities,
  getTTSQuestionUrl,
  saveQuestionBankFromInterviewAnswer,
  SessionResponse,
  SessionQuestion,
  AnswerEvaluation,
  SpeechMetrics,
  CompanyResearchResponse,
  ProgressTrendItem,
  PlanFollowUpResponse,
  CoachCapabilities,
} from "@/lib/api";
import { QuestionNav } from "@/components/coach/QuestionNav";
import { QuestionPanel } from "@/components/coach/QuestionPanel";
import { VoiceRecorder } from "@/components/coach/VoiceRecorder";
import { AudioBlobRecorder } from "@/components/coach/AudioBlobRecorder";
import { EvaluationCard } from "@/components/coach/EvaluationCard";
import { ModelAnswer } from "@/components/coach/ModelAnswer";
import { CompanyBrief } from "@/components/coach/CompanyBrief";
import { CoachModalitySelector, CoachMode } from "@/components/coach/CoachModalitySelector";
import { AnalysingBanner } from "@/components/coach/AnalysingBanner";
import { FaceCapture, FaceSummary } from "@/components/coach/FaceCapture";
import { Button } from "@/components/ui/button";
import { Loader2, FlagTriangleRight, Volume2, TrendingUp, ChevronRight } from "lucide-react";

type RecordingMode = CoachMode;
type SessionState = "idle" | "recording" | "submitted" | "evaluated";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentQuestion, setCurrentQuestion] = useState<SessionQuestion | null>(null);
  const [answeredIds, setAnsweredIds] = useState<Set<string>>(new Set());
  const [evaluation, setEvaluation] = useState<AnswerEvaluation | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>("idle");
  const [recordingMode, setRecordingMode] = useState<RecordingMode>("text");
  const [textAnswer, setTextAnswer] = useState("");
  const [research, setResearch] = useState<CompanyResearchResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savingToBank, setSavingToBank] = useState(false);
  const [bankMessage, setBankMessage] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Phase C — follow-up + progress trend
  const [planningFollowup, setPlanningFollowup] = useState(false);
  const [progressTrend, setProgressTrend] = useState<ProgressTrendItem[] | null>(null);
  const [showTrend, setShowTrend] = useState(false);
  // Phase D — face capture
  const [faceSummary, setFaceSummary] = useState<FaceSummary | null>(null);
  const [faceActive, setFaceActive] = useState(false);
  // Phase E — capabilities
  const [capabilities, setCapabilities] = useState<CoachCapabilities>({ face_analysis: false, tts: false });

  useEffect(() => {
    if (!id) return;
    getSession(id)
      .then((s) => {
        setSession(s);
        if (s.questions.length > 0) {
          setCurrentQuestion(s.questions[0]);
        }
        // Fetch company research in background
        researchCompany(s.company_name).then(setResearch).catch(() => {});
      })
      .catch(() => setError("Session not found"))
      .finally(() => setLoading(false));
    // Phase E: fetch capabilities on mount
    getCoachCapabilities().then(setCapabilities).catch(() => {});
  }, [id]);

  const handleAnswer = useCallback(
    async (transcript: string, metrics: SpeechMetrics, durationMs: number) => {
      if (!currentQuestion || !session) return;
      setSubmitting(true);
      setSessionState("submitted");
      try {
        const jobRef = await submitAnswer(
          session.id,
          currentQuestion.id,
          transcript,
          durationMs,
          metrics
        );
        // Poll until the evaluation job completes
        let eval_: AnswerEvaluation | null = null;
        while (!eval_) {
          const job = await getAsyncJob<AnswerEvaluation>(jobRef.job_id);
          if (job.status === "done" && job.result) { eval_ = job.result; break; }
          if (job.status === "failed") throw new Error(job.error ?? "Evaluation failed");
          await new Promise((r) => setTimeout(r, 2000));
        }
        setEvaluation(eval_);
        setAnsweredIds((prev) => { const next = new Set(prev); next.add(currentQuestion.id); return next; });
        setSessionState("evaluated");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Submission failed");
        setSessionState("idle");
      } finally {
        setSubmitting(false);
      }
    },
    [currentQuestion, session]
  );

  const handleTextSubmit = async () => {
    if (!textAnswer.trim()) return;
    await handleAnswer(textAnswer, { filler_count: 0, wpm: 0, hedging_count: 0, duration_ms: 0, pause_count: 0 }, 0);
    setTextAnswer("");
  };

  const handleSaveToQuestionBank = async () => {
    if (!session || !currentQuestion || !textAnswer.trim()) return;
    setSavingToBank(true);
    setBankMessage(null);
    try {
      await saveQuestionBankFromInterviewAnswer({
        session_id: session.id,
        question_id: currentQuestion.id,
        answer_draft: textAnswer.trim(),
        title: currentQuestion.text,
        confidence: "draft",
      });
      setBankMessage("Saved to Question Bank.");
    } catch {
      setBankMessage("Could not save to Question Bank.");
    } finally {
      setSavingToBank(false);
    }
  };

  const handleAudioSubmit = useCallback(
    async (blob: Blob, durationMs: number) => {
      if (!currentQuestion || !session) return;
      // Stop face capture and wait for summary if in video mode
      if (recordingMode === "video") {
        setFaceActive(false);
      }
      setSubmitting(true);
      setSessionState("submitted");
      try {
        const jobRef = await submitAudio(
          session.id,
          currentQuestion.id,
          blob,
          undefined,
          faceSummary ?? undefined
        );
        let eval_: AnswerEvaluation | null = null;
        while (!eval_) {
          const job = await getAsyncJob<AnswerEvaluation>(jobRef.job_id);
          if (job.status === "done" && job.result) { eval_ = job.result; break; }
          if (job.status === "failed") throw new Error(job.error ?? "Analysis failed");
          await new Promise((r) => setTimeout(r, 2000));
        }
        setEvaluation(eval_);
        setAnsweredIds((prev) => { const next = new Set(prev); next.add(currentQuestion.id); return next; });
        setSessionState("evaluated");
        setFaceSummary(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Audio submission failed");
        setSessionState("idle");
      } finally {
        setSubmitting(false);
      }
    },
    [currentQuestion, session, recordingMode, faceSummary]
  );

  const handleNext = () => {
    if (!session) return;
    const unanswered = session.questions.filter((q) => !answeredIds.has(q.id));
    if (unanswered.length > 0) {
      setCurrentQuestion(unanswered[0]);
      setEvaluation(null);
      setSessionState("idle");
    }
  };

  const handleEndSession = async () => {
    if (!session) return;
    setEnding(true);
    try {
      const jobRef = await endSession(session.id);
      // Poll until the report generation job completes
      while (true) {
        const job = await getAsyncJob(jobRef.job_id);
        if (job.status === "done") break;
        if (job.status === "failed") throw new Error(job.error ?? "Failed to generate report");
        await new Promise((r) => setTimeout(r, 2000));
      }
      router.push(`/coach/report/${session.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to end session");
      setEnding(false);
    }
  };

  // Phase C: Plan a follow-up session
  const handlePlanFollowup = async () => {
    if (!session) return;
    setPlanningFollowup(true);
    try {
      const resp: PlanFollowUpResponse = await planFollowUpSession(session.id);
      router.push(`/coach/session/${resp.followup_session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to plan follow-up session");
    } finally {
      setPlanningFollowup(false);
    }
  };

  // Phase C: Load and toggle progress trend
  const handleToggleTrend = async () => {
    if (showTrend) {
      setShowTrend(false);
      return;
    }
    if (!session) return;
    try {
      const trend = await getProgressTrend(session.id);
      setProgressTrend(trend);
      setShowTrend(true);
    } catch {
      // Silently ignore
    }
  };

  // Phase E: Play TTS audio for a question
  const handlePlayTTS = (questionId: string) => {
    if (!session) return;
    const url = getTTSQuestionUrl(session.id, questionId);
    const audio = new Audio(url);
    audio.play().catch(() => {});
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  if (!session || error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-slate-400">{error ?? "Session not found"}</p>
      </div>
    );
  }

  const unansweredCount = session.questions.filter((q) => !answeredIds.has(q.id)).length;
  const allAnswered = unansweredCount === 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="font-semibold text-slate-100">
            {session.role_title} · {session.company_name}
          </h1>
          <p className="text-xs text-slate-500">
            {answeredIds.size}/{session.questions.length} answered
          </p>
        </div>
        <Button
          onClick={handleEndSession}
          disabled={ending}
          className="gap-2 bg-red-900/50 text-red-300 hover:bg-red-800"
        >
          <FlagTriangleRight className="h-4 w-4" />
          {ending ? "Generating report…" : allAnswered ? "Get Report" : "End Session"}
        </Button>
      </div>

      {/* 3-column layout */}
      <div className="grid grid-cols-[200px_1fr_240px] gap-4">
        {/* Left: Question nav */}
        <aside className="rounded-xl border border-slate-700 bg-slate-800 p-3">
          <QuestionNav
            questions={session.questions}
            answeredIds={answeredIds}
            currentId={currentQuestion?.id ?? null}
            onSelect={(q) => {
              setCurrentQuestion(q);
              setEvaluation(null);
              setSessionState("idle");
            }}
          />
        </aside>

        {/* Centre: Question + Recorder */}
        <div className="space-y-4">
          {currentQuestion ? (
            <>
              {/* Question panel with optional TTS button (Phase E) */}
              <div className="relative">
                <QuestionPanel question={{ ...currentQuestion, num: currentQuestion.order_in_session, total: session.questions.length }} />
                {capabilities.tts && (
                  <button
                    type="button"
                    aria-label="Play question aloud"
                    title="Play question aloud"
                    onClick={() => handlePlayTTS(currentQuestion.id)}
                    className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full border border-slate-600 bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-200"
                  >
                    <Volume2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {sessionState !== "evaluated" && (
                <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-slate-400">Your Answer</p>
                    <CoachModalitySelector
                      mode={recordingMode}
                      onModeChange={(m) => {
                        setRecordingMode(m);
                        setFaceActive(m === "video");
                      }}
                      disabled={submitting}
                    />
                  </div>

                  {recordingMode === "text" ? (
                    <div className="space-y-2">
                      <textarea
                        value={textAnswer}
                        onChange={(e) => setTextAnswer(e.target.value)}
                        rows={6}
                        placeholder="Type your answer using the STAR framework (Situation, Task, Action, Result)…"
                        className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
                        disabled={submitting}
                      />
                      <Button
                        onClick={handleTextSubmit}
                        disabled={!textAnswer.trim() || submitting}
                        className="w-full bg-emerald-700 hover:bg-emerald-600"
                      >
                        {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit Answer"}
                      </Button>
                      <Button
                        onClick={handleSaveToQuestionBank}
                        disabled={!textAnswer.trim() || submitting || savingToBank}
                        className="w-full border-slate-600 text-slate-200 hover:bg-slate-700"
                        variant="outline"
                      >
                        {savingToBank ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        {savingToBank ? "Saving…" : "Save to Question Bank"}
                      </Button>
                      {bankMessage ? (
                        <p className="text-xs text-slate-400" role="status">{bankMessage}</p>
                      ) : null}
                    </div>
                  ) : recordingMode === "voice" ? (
                    <AudioBlobRecorder onSubmit={handleAudioSubmit} disabled={submitting} />
                  ) : recordingMode === "video" ? (
                    <div className="space-y-3">
                      {/* Phase D: FaceCapture alongside AudioBlobRecorder */}
                      <FaceCapture
                        active={faceActive && !submitting}
                        onSummaryReady={(summary) => setFaceSummary(summary)}
                      />
                      <AudioBlobRecorder onSubmit={handleAudioSubmit} disabled={submitting} />
                    </div>
                  ) : (
                    <VoiceRecorder onSubmit={handleAnswer} disabled={submitting} />
                  )}
                </div>
              )}

              <AnalysingBanner visible={sessionState === "submitted" && submitting} />

              {evaluation && sessionState === "evaluated" && (
                <div className="space-y-3">
                  <EvaluationCard evaluation={evaluation} />
                  <ModelAnswer modelAnswer={currentQuestion.model_answer} />
                  {!allAnswered && (
                    <Button
                      onClick={handleNext}
                      className="w-full bg-indigo-600 hover:bg-indigo-500"
                    >
                      Next Question →
                    </Button>
                  )}
                  {allAnswered && (
                    <>
                      <Button
                        onClick={handleEndSession}
                        disabled={ending}
                        className="w-full bg-emerald-700 hover:bg-emerald-600"
                      >
                        {ending ? "Generating report…" : "View Feedback Report →"}
                      </Button>
                      {/* Phase C: Plan follow-up session */}
                      <Button
                        onClick={handlePlanFollowup}
                        disabled={planningFollowup}
                        variant="outline"
                        className="w-full border-indigo-700 text-indigo-300 hover:bg-indigo-900/40"
                      >
                        {planningFollowup ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : (
                          <ChevronRight className="h-4 w-4 mr-2" />
                        )}
                        Plan follow-up session
                      </Button>
                      {/* Phase C: Progress trend toggle */}
                      <Button
                        onClick={handleToggleTrend}
                        variant="outline"
                        className="w-full border-slate-600 text-slate-400 hover:bg-slate-700"
                      >
                        <TrendingUp className="h-4 w-4 mr-2" />
                        {showTrend ? "Hide progress trend" : "Show progress trend"}
                      </Button>
                      {showTrend && progressTrend && (
                        <div className="rounded-xl border border-slate-700 bg-slate-800 p-4">
                          <h3 className="mb-3 text-sm font-medium text-slate-300">Progress Trend</h3>
                          {progressTrend.length === 0 ? (
                            <p className="text-xs text-slate-500">No trend data yet.</p>
                          ) : (
                            <div className="space-y-2">
                              {progressTrend.map((item, i) => (
                                <div key={item.session_id} className="flex items-center justify-between text-xs">
                                  <span className="text-slate-400">Session {i + 1}</span>
                                  <span className="text-slate-300">
                                    {item.overall_score !== null
                                      ? `${item.overall_score.toFixed(1)}/10`
                                      : "—"}
                                  </span>
                                  {item.focus_areas.length > 0 && (
                                    <span className="text-indigo-400">
                                      Focus: {item.focus_areas.join(", ")}
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-xl border border-slate-700 bg-slate-800">
              <p className="text-slate-500">Select a question to begin</p>
            </div>
          )}
        </div>

        {/* Right: Company brief */}
        <aside>
          {research ? (
            <CompanyBrief research={research} />
          ) : (
            <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 text-xs text-slate-500">
              Loading company intelligence…
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
