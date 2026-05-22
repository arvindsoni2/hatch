"use client"

import { useState, useEffect } from "react"
import { getAutoApplyHistory, getAutoApplyPreview, type ApplicationAttempt } from "../../lib/api"
import { AutoApplyReview } from "../../components/AutoApplyReview"

type StatusColor = "green" | "red" | "amber" | "blue" | "gray"

const STATUS_CONFIG: Record<string, { label: string; color: StatusColor }> = {
  submitted: { label: "Submitted", color: "green" },
  failed: { label: "Failed", color: "red" },
  captcha_blocked: { label: "CAPTCHA Blocked", color: "amber" },
  ready_for_review: { label: "Ready for Review", color: "blue" },
  pending: { label: "Pending", color: "gray" },
}

const BADGE_CLASSES: Record<StatusColor, string> = {
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
  blue: "bg-blue-100 text-blue-800",
  gray: "bg-slate-100 text-slate-600",
}

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? { label: status, color: "gray" as StatusColor }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_CLASSES[config.color]}`}
    >
      {config.label}
    </span>
  )
}

function truncateUrl(url: string, max = 50): string {
  if (url.length <= max) return url
  try {
    const parsed = new URL(url)
    const host = parsed.hostname
    const path = parsed.pathname
    if (host.length + 3 >= max) return `${host.slice(0, max - 3)}…`
    return `${host}${path.slice(0, max - host.length - 3)}…`
  } catch {
    return `${url.slice(0, max - 1)}…`
  }
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return "—"
  try {
    return new Date(dateStr).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return dateStr
  }
}

export default function AutoApplyPage() {
  const [attempts, setAttempts] = useState<ApplicationAttempt[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Modal state
  const [modalAppId, setModalAppId] = useState<string | null>(null)
  const [previewAttempt, setPreviewAttempt] = useState<ApplicationAttempt | null>(null)

  const loadHistory = async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const data = await getAutoApplyHistory()
      setAttempts(data)
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Failed to load history")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadHistory()
  }, [])

  const handleViewPreview = async (attempt: ApplicationAttempt) => {
    try {
      const preview = await getAutoApplyPreview(attempt.id)
      setPreviewAttempt(preview)
      setModalAppId(attempt.application_id)
    } catch {
      // Fall back to opening the modal with the attempt's application_id directly
      setModalAppId(attempt.application_id)
    }
  }

  const handleRetry = (attempt: ApplicationAttempt) => {
    setModalAppId(attempt.application_id)
  }

  const handleModalClose = () => {
    setModalAppId(null)
    setPreviewAttempt(null)
  }

  const handleModalSuccess = () => {
    setModalAppId(null)
    setPreviewAttempt(null)
    void loadHistory()
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Auto Apply</h1>
          <p className="mt-1 text-sm text-slate-500">
            Use the <span className="font-medium">Auto Apply</span> button on individual applications to prepare and submit applications.
          </p>
        </div>
        <button
          onClick={() => void loadHistory()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
        >
          <svg className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {loading && (
          <div className="flex items-center justify-center py-16">
            <svg className="h-6 w-6 animate-spin text-brand-600" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            <span className="ml-3 text-sm text-slate-500">Loading attempts…</span>
          </div>
        )}

        {fetchError && !loading && (
          <div className="flex items-center gap-3 px-6 py-8 text-sm text-red-600">
            <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {fetchError}
          </div>
        )}

        {!loading && !fetchError && attempts.length === 0 && (
          <div className="py-16 text-center">
            <svg className="mx-auto h-10 w-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="mt-3 text-sm text-slate-500">No auto-apply attempts yet.</p>
          </div>
        )}

        {!loading && !fetchError && attempts.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Job URL
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Platform
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Submitted At
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {attempts.map((attempt) => (
                <tr key={attempt.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <a
                      href={attempt.job_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={attempt.job_url}
                      className="text-brand-600 hover:underline"
                    >
                      {truncateUrl(attempt.job_url)}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {attempt.platform ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={attempt.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {formatDate(attempt.submitted_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => void handleViewPreview(attempt)}
                        className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                      >
                        View Preview
                      </button>
                      {(attempt.status === "failed" || attempt.status === "captcha_blocked") && (
                        <button
                          onClick={() => handleRetry(attempt)}
                          className="rounded border border-brand-300 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-100 transition-colors"
                        >
                          Retry
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal */}
      {modalAppId && (
        <AutoApplyReview
          applicationId={modalAppId}
          jobUrl={previewAttempt?.job_url}
          onClose={handleModalClose}
          onSuccess={handleModalSuccess}
        />
      )}
    </div>
  )
}
