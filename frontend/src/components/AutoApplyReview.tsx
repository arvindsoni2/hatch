"use client"

import { useState, useEffect, useCallback } from "react"
import {
  createAutoApplyAttempt,
  getAutoApplyPreview,
  updateAutoApplyPreview,
  approveAutoApply,
  submitAutoApply,
  type ApplicationAttempt,
} from "../lib/api"

interface AutoApplyReviewProps {
  applicationId: string
  jobUrl?: string
  onClose: () => void
  onSuccess: () => void
}

type Stage = "preparing" | "review" | "result"

const PREP_STEPS = [
  "Opening job page",
  "Detecting form",
  "Filling fields",
  "Generating answers",
]

interface EditableField {
  key: string
  value: string
}

interface EditableQuestion {
  question: string
  answer: string
}

function parseJsonSafe<T>(raw: string | undefined): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function AutoApplyReview({
  applicationId,
  onClose,
  onSuccess,
}: AutoApplyReviewProps) {
  const [stage, setStage] = useState<Stage>("preparing")
  const [attempt, setAttempt] = useState<ApplicationAttempt | null>(null)
  const [prepStepIndex, setPrepStepIndex] = useState(0)
  const [prepProgress, setPrepProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const [formFields, setFormFields] = useState<EditableField[]>([])
  const [customQuestions, setCustomQuestions] = useState<EditableQuestion[]>([])
  const [reviewed, setReviewed] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const prepareApplication = useCallback(async () => {
    setError(null)
    setStage("preparing")
    setPrepStepIndex(0)
    setPrepProgress(0)

    // Animate through steps while waiting for the API
    const stepInterval = setInterval(() => {
      setPrepStepIndex((i) => {
        const next = Math.min(i + 1, PREP_STEPS.length - 1)
        setPrepProgress(Math.round(((next + 1) / PREP_STEPS.length) * 85))
        return next
      })
    }, 1200)

    try {
      const result = await createAutoApplyAttempt(applicationId)
      clearInterval(stepInterval)
      setPrepStepIndex(PREP_STEPS.length - 1)
      setPrepProgress(100)
      setAttempt(result)

      // Parse editable fields
      const parsedForm = parseJsonSafe<Record<string, string>>(result.form_data)
      if (parsedForm) {
        setFormFields(
          Object.entries(parsedForm).map(([key, value]) => ({ key, value }))
        )
      }

      const parsedQuestions = parseJsonSafe<EditableQuestion[]>(
        result.custom_questions
      )
      if (parsedQuestions) {
        setCustomQuestions(parsedQuestions)
      }

      setStage("review")
    } catch (err) {
      clearInterval(stepInterval)
      setError(err instanceof Error ? err.message : "Preparation failed")
      setStage("result")
    }
  }, [applicationId])

  useEffect(() => {
    void prepareApplication()
  }, [prepareApplication])

  const handleFieldChange = (index: number, value: string) => {
    setFormFields((prev) =>
      prev.map((f, i) => (i === index ? { ...f, value } : f))
    )
  }

  const handleQuestionChange = (index: number, answer: string) => {
    setCustomQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, answer } : q))
    )
  }

  const handleApproveAndSubmit = async () => {
    if (!attempt) return
    setSubmitting(true)
    setError(null)
    try {
      // Build updated payload from edited fields
      const updatedFormData = formFields.reduce<Record<string, string>>(
        (acc, f) => {
          acc[f.key] = f.value
          return acc
        },
        {}
      )
      await updateAutoApplyPreview(attempt.id, {
        form_data: JSON.stringify(updatedFormData),
        custom_questions: JSON.stringify(customQuestions),
      })
      await approveAutoApply(attempt.id)
      const submitted = await submitAutoApply(attempt.id)
      setAttempt(submitted)
      setStage("result")
      if (submitted.status === "submitted") {
        onSuccess()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed")
      setStage("result")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative w-full max-w-2xl rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Auto Apply</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          {/* Stage 1: Preparing */}
          {stage === "preparing" && (
            <div className="space-y-6">
              <p className="text-sm text-slate-500">
                Preparing your application — this may take a few seconds.
              </p>
              {/* Progress bar */}
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-brand-600 transition-all duration-700"
                  style={{ width: `${prepProgress}%` }}
                />
              </div>
              {/* Steps */}
              <ol className="space-y-3">
                {PREP_STEPS.map((step, i) => (
                  <li key={step} className="flex items-center gap-3">
                    {i < prepStepIndex ? (
                      <svg className="h-5 w-5 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : i === prepStepIndex ? (
                      <svg className="h-5 w-5 text-brand-600 shrink-0 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                      </svg>
                    ) : (
                      <div className="h-5 w-5 rounded-full border-2 border-slate-300 shrink-0" />
                    )}
                    <span
                      className={`text-sm ${
                        i <= prepStepIndex ? "text-slate-900 font-medium" : "text-slate-400"
                      }`}
                    >
                      {step}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Stage 2: Review */}
          {stage === "review" && attempt && (
            <div className="space-y-5">
              {/* Warning */}
              <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <svg className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
                <p className="text-sm text-amber-800">
                  Review all fields carefully before submitting. Incorrect information may disqualify your application.
                </p>
              </div>

              {/* Platform info */}
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 space-y-1">
                {attempt.platform && (
                  <p className="text-sm text-slate-600">
                    <span className="font-medium">Platform:</span> {attempt.platform}
                  </p>
                )}
                {attempt.apply_url && (
                  <p className="text-sm text-slate-600 break-all">
                    <span className="font-medium">Apply URL:</span>{" "}
                    <a
                      href={attempt.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-brand-600 hover:underline"
                    >
                      {attempt.apply_url}
                    </a>
                  </p>
                )}
              </div>

              {/* Form fields */}
              {formFields.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-slate-700 uppercase tracking-wide">
                    Form Fields
                  </h3>
                  <div className="space-y-3">
                    {formFields.map((field, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-slate-500">
                          {field.key}
                        </label>
                        <input
                          type="text"
                          value={field.value}
                          onChange={(e) => handleFieldChange(i, e.target.value)}
                          className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Custom questions */}
              {customQuestions.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-slate-700 uppercase tracking-wide">
                    Custom Questions
                  </h3>
                  <div className="space-y-4">
                    {customQuestions.map((qa, i) => (
                      <div key={i} className="space-y-1">
                        <p className="text-sm font-medium text-slate-800">{qa.question}</p>
                        <textarea
                          value={qa.answer}
                          onChange={(e) => handleQuestionChange(i, e.target.value)}
                          rows={3}
                          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Confirmation checkbox */}
              <label className="flex items-start gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={reviewed}
                  onChange={(e) => setReviewed(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <span className="text-sm text-slate-700">
                  I have reviewed all fields and confirm they are accurate.
                </span>
              </label>
            </div>
          )}

          {/* Stage 3: Result */}
          {stage === "result" && (
            <div className="space-y-4 py-2">
              {attempt?.status === "submitted" && (
                <div className="flex flex-col items-center gap-3 py-4 text-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-green-100">
                    <svg className="h-7 w-7 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-lg font-semibold text-slate-900">Application submitted successfully</p>
                </div>
              )}

              {attempt?.status === "captcha_blocked" && (
                <div className="flex flex-col items-center gap-3 py-4 text-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-amber-100">
                    <svg className="h-7 w-7 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                    </svg>
                  </div>
                  <p className="text-lg font-semibold text-slate-900">CAPTCHA detected</p>
                  <p className="text-sm text-slate-500">
                    Automated submission was blocked. Please apply manually.
                  </p>
                  {attempt.apply_url && (
                    <a
                      href={attempt.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 transition-colors"
                    >
                      Apply Manually
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  )}
                </div>
              )}

              {(attempt?.status === "failed" || (!attempt && error)) && (
                <div className="flex flex-col items-center gap-3 py-4 text-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-100">
                    <svg className="h-7 w-7 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                  <p className="text-lg font-semibold text-slate-900">Submission failed</p>
                  {(attempt?.error_message ?? error) && (
                    <p className="text-sm text-red-600">
                      {attempt?.error_message ?? error}
                    </p>
                  )}
                  <div className="flex gap-3">
                    <button
                      onClick={() => void prepareApplication()}
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      Retry
                    </button>
                    {attempt?.apply_url && (
                      <a
                        href={attempt.apply_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
                      >
                        Apply Manually
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        {stage === "review" && (
          <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-6 py-4">
            <button
              onClick={onClose}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => void prepareApplication()}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Re-prepare
            </button>
            <button
              onClick={() => void handleApproveAndSubmit()}
              disabled={!reviewed || submitting}
              className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? (
                <>
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Submitting…
                </>
              ) : (
                "Approve & Submit"
              )}
            </button>
          </div>
        )}

        {stage === "result" && attempt?.status === "submitted" && (
          <div className="flex items-center justify-end border-t border-slate-200 px-6 py-4">
            <button
              onClick={onClose}
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
            >
              Close
            </button>
          </div>
        )}

        {stage === "result" && (attempt?.status === "captcha_blocked" || (!attempt && error)) && (
          <div className="flex items-center justify-end border-t border-slate-200 px-6 py-4">
            <button
              onClick={onClose}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
