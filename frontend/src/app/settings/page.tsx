"use client"

import { useState, useEffect } from "react"
import { getDigestStatus, sendDigest, DigestStatus } from "../../lib/api"
import { DigestPreview } from "../../components/DigestPreview"

interface SectionCardProps {
  title: string
  children: React.ReactNode
}

function SectionCard({ title, children }: SectionCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-6 py-4">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  )
}

interface FieldRowProps {
  label: string
  value: React.ReactNode
}

function FieldRow({ label, value }: FieldRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-slate-100 last:border-0">
      <span className="text-sm font-medium text-slate-500 shrink-0 w-48">{label}</span>
      <span className="text-sm text-slate-800 text-right">{value}</span>
    </div>
  )
}

type DigestStatusData = DigestStatus

function toBoolean(val: unknown): boolean {
  if (typeof val === "boolean") return val
  if (typeof val === "string") return val.toLowerCase() === "true" || val === "1"
  if (typeof val === "number") return val === 1
  return false
}

type ToastVariant = "success" | "error"

export default function SettingsPage() {
  const [digestStatus, setDigestStatus] = useState<DigestStatusData | null>(null)
  const [digestLoading, setDigestLoading] = useState(true)
  const [digestError, setDigestError] = useState<string | null>(null)

  const [toast, setToast] = useState<{ message: string; variant: ToastVariant } | null>(null)
  const [sendingDigest, setSendingDigest] = useState(false)

  useEffect(() => {
    const load = async () => {
      setDigestLoading(true)
      setDigestError(null)
      try {
        const data = await getDigestStatus()
        setDigestStatus(data)
      } catch (err) {
        setDigestError(err instanceof Error ? err.message : "Failed to load digest status")
      } finally {
        setDigestLoading(false)
      }
    }
    void load()
  }, [])

  const showToast = (message: string, variant: ToastVariant) => {
    setToast({ message, variant })
    setTimeout(() => setToast(null), 4000)
  }

  const handleSendDigest = async () => {
    setSendingDigest(true)
    try {
      const result = await sendDigest()
      showToast(result.message || "Digest sent successfully", "success")
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to send digest", "error")
    } finally {
      setSendingDigest(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">
          View and manage JobPilot configuration.
        </p>
      </div>

      {/* Section 1: Auto-Apply */}
      <SectionCard title="Auto Apply">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Enabled boards" value="reed, cwjobs" />
          <FieldRow label="Max applications per hour" value="10" />
          <FieldRow label="Requires individual review" value="Yes" />
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Edit settings in the <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">.env</code> file to update auto-apply configuration.
        </p>
      </SectionCard>

      {/* Section 2: Daily Digest */}
      <SectionCard title="Daily Digest">
        {digestLoading ? (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Loading digest status…
          </div>
        ) : digestError ? (
          <p className="text-sm text-red-600">{digestError}</p>
        ) : (
          <div className="space-y-4">
            <div className="divide-y divide-slate-100">
              <FieldRow
                label="Enabled"
                value={
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      toBoolean(digestStatus?.enabled)
                        ? "bg-green-100 text-green-800"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {toBoolean(digestStatus?.enabled) ? "Yes" : "No"}
                  </span>
                }
              />
              <FieldRow
                label="Send time"
                value={
                  typeof digestStatus?.time === "string" && digestStatus.time
                    ? digestStatus.time
                    : "08:00"
                }
              />
              <FieldRow
                label="Timezone"
                value={
                  typeof digestStatus?.timezone === "string" && digestStatus.timezone
                    ? digestStatus.timezone
                    : "Europe/London"
                }
              />
              <FieldRow
                label="Frequency"
                value={
                  typeof digestStatus?.frequency === "string" && digestStatus.frequency
                    ? digestStatus.frequency
                    : "daily"
                }
              />
              <FieldRow
                label="SMTP configured"
                value={
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      toBoolean(digestStatus?.smtp_configured)
                        ? "bg-green-100 text-green-800"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {toBoolean(digestStatus?.smtp_configured) ? "Yes" : "No"}
                  </span>
                }
              />
            </div>
            <div className="flex items-center gap-3 pt-1">
              <DigestPreview />
              <button
                onClick={() => void handleSendDigest()}
                disabled={sendingDigest}
                className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >
                {sendingDigest ? (
                  <>
                    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Sending…
                  </>
                ) : (
                  "Send Now"
                )}
              </button>
            </div>
          </div>
        )}
      </SectionCard>

      {/* Section 3: Candidate Profile */}
      <SectionCard title="Candidate Profile">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Name" value="Solutions Architect" />
          <FieldRow label="Location" value="United Kingdom" />
          <FieldRow label="Primary target role" value="Solutions Architect" />
          <FieldRow label="Secondary target roles" value="Enterprise Architect, Cloud Architect" />
          <FieldRow label="Rate expectation" value="£700–£900/day" />
          <FieldRow label="Preferred working pattern" value="Hybrid / Remote" />
          <FieldRow label="IR35 preference" value="Outside IR35 only" />
          <FieldRow label="Years of experience" value="20+" />
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Edit{" "}
          <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">candidate_profile.json</code>{" "}
          to update these details.
        </p>
      </SectionCard>

      {/* Section 4: About */}
      <SectionCard title="About">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Application" value="JobPilot" />
          <FieldRow label="Version" value="2.0.0" />
          <FieldRow
            label="Modules"
            value="Scout · Tracker · Tailor · Coach"
          />
          <FieldRow
            label="AI model"
            value="claude-sonnet-4-20250514"
          />
          <FieldRow
            label="API documentation"
            value={
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-600 hover:underline"
              >
                localhost:8000/docs
              </a>
            }
          />
          <FieldRow
            label="OpenAPI spec"
            value={
              <a
                href="http://localhost:8000/openapi.json"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-600 hover:underline"
              >
                localhost:8000/openapi.json
              </a>
            }
          />
          <FieldRow
            label="Master CV"
            value={
              <a href="/settings/resume" className="text-brand-600 hover:underline">
                Upload &amp; manage master CV →
              </a>
            }
          />
          <FieldRow
            label="System event log"
            value={
              <a href="/settings/system" className="text-brand-600 hover:underline">
                View agent events &amp; LLM costs →
              </a>
            }
          />
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Personal tool built for UK outside-IR35 contract role hunting.
        </p>
      </SectionCard>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-lg px-4 py-3 shadow-lg text-sm font-medium text-white transition-all ${
            toast.variant === "success" ? "bg-green-600" : "bg-red-600"
          }`}
        >
          {toast.variant === "success" ? (
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
          {toast.message}
        </div>
      )}
    </div>
  )
}
