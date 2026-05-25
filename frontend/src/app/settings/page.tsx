"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { getDigestStatus, sendDigest, DigestStatus, API_BASE } from "../../lib/api"
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

interface ProfileData {
  candidate?: { name?: string; title?: string; years_experience?: number }
  search?: {
    target_roles?: string[]
    locations?: { city?: string; country?: string; remote_preference?: string }[]
    contract_type?: string
    scrape_interval_hours?: number
  }
  compensation?: { min_rate?: number; max_rate?: number; currency?: string; rate_type?: string; ir35_preference?: string }
  llm?: { provider?: string; primary_model?: string; triage_model?: string; api_key_env?: string; temperature?: number; monthly_budget?: number; currency?: string }
  job_boards?: { name: string; enabled: boolean; scraper: string }[]
}

export default function SettingsPage() {
  const [digestStatus, setDigestStatus] = useState<DigestStatusData | null>(null)
  const [digestLoading, setDigestLoading] = useState(true)
  const [digestError, setDigestError] = useState<string | null>(null)
  const [profileData, setProfileData] = useState<ProfileData | null>(null)

  const [toast, setToast] = useState<{ message: string; variant: ToastVariant } | null>(null)
  const [sendingDigest, setSendingDigest] = useState(false)

  useEffect(() => {
    const load = async () => {
      setDigestLoading(true)
      setDigestError(null)
      try {
        const [digestData, profileResp] = await Promise.all([
          getDigestStatus(),
          fetch(`${API_BASE}/api/v2/profile`).then((r) => r.json() as Promise<ProfileData>),
        ])
        setDigestStatus(digestData)
        setProfileData(profileResp)
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
        {profileData ? (() => {
          const roles = profileData.search?.target_roles ?? []
          const loc = profileData.search?.locations?.[0]
          const location = [loc?.city, loc?.country].filter(Boolean).join(", ") || "—"
          const primaryRole = roles[0] ?? "—"
          const secondaryRoles = roles.slice(1).join(", ") || "—"
          const comp = profileData.compensation
          const rateLabel = comp && (comp.min_rate ?? 0) > 0 && (comp.max_rate ?? 0) > 0
            ? `${comp.currency ?? "£"}${comp.min_rate}–${comp.max_rate}/${comp.rate_type === "daily" ? "day" : "hr"}`
            : comp && (comp.min_rate ?? 0) > 0
            ? `${comp.currency ?? "£"}${comp.min_rate}+/${comp.rate_type === "daily" ? "day" : "hr"}`
            : "Not set"
          const remoteLabel = loc?.remote_preference
            ? loc.remote_preference === "any" ? "Any (on-site / hybrid / remote)" : loc.remote_preference
            : "—"
          const ir35Label = comp?.ir35_preference
            ? comp.ir35_preference === "any" ? "Any" : comp.ir35_preference === "outside" ? "Outside IR35 only" : comp.ir35_preference
            : "—"
          const yearsExp = profileData.candidate?.years_experience != null
            ? `${profileData.candidate.years_experience}+`
            : "—"
          return (
            <div className="divide-y divide-slate-100">
              <FieldRow label="Name" value={profileData.candidate?.name ?? "—"} />
              <FieldRow label="Location" value={location} />
              <FieldRow label="Primary target role" value={primaryRole} />
              <FieldRow label="Secondary target roles" value={secondaryRoles} />
              <FieldRow label="Rate expectation" value={rateLabel} />
              <FieldRow label="Preferred working pattern" value={remoteLabel} />
              <FieldRow label="IR35 preference" value={ir35Label} />
              <FieldRow label="Years of experience" value={yearsExp} />
            </div>
          )
        })() : (
          <p className="text-sm text-slate-400 py-2">Loading profile…</p>
        )}
        <p className="mt-4 text-xs text-slate-400">
          <Link href="/settings/profile" className="text-brand-600 hover:underline">
            Edit profile settings →
          </Link>
        </p>
      </SectionCard>

      {/* Section 4: Job Boards */}
      <SectionCard title="Job Boards">
        {profileData?.job_boards && profileData.job_boards.length > 0 ? (
          <div className="divide-y divide-slate-100">
            {profileData.job_boards.map((board) => (
              <div key={board.name} className="flex items-center justify-between py-2.5">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`h-2 w-2 rounded-full shrink-0 ${board.enabled ? "bg-green-500" : "bg-slate-300"}`}
                  />
                  <span className="text-sm font-medium text-slate-700 capitalize">{board.name}</span>
                  {board.scraper && (
                    <span className="text-xs text-slate-400">({board.scraper})</span>
                  )}
                </div>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${board.enabled ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>
                  {board.enabled ? "Active" : "Disabled"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-400 py-2">
            No job boards configured. Add boards to <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">profile.yaml</code> under <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">search.job_boards</code>.
          </p>
        )}
        {profileData?.search?.scrape_interval_hours && (
          <p className="mt-3 text-xs text-slate-400">
            Scrape interval: every {profileData.search.scrape_interval_hours} hours · <Link href="/settings/profile" className="text-brand-600 hover:underline">Edit in profile →</Link>
          </p>
        )}
      </SectionCard>

      {/* Section 5: LLM Provider */}
      <SectionCard title="LLM Provider">
        {profileData?.llm ? (
          <div className="divide-y divide-slate-100">
            <FieldRow label="Provider" value={
              <span className="capitalize">{(profileData.llm.provider ?? "—").replace("_", " ")}</span>
            } />
            <FieldRow label="Primary model" value={profileData.llm.primary_model ?? "—"} />
            <FieldRow label="Triage model" value={profileData.llm.triage_model ?? "—"} />
            <FieldRow label="API key env var" value={
              <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                {profileData.llm.api_key_env ?? "—"}
              </code>
            } />
            <FieldRow label="Temperature" value={profileData.llm.temperature?.toString() ?? "0.1"} />
            {profileData.llm.monthly_budget && (
              <FieldRow
                label="Monthly budget"
                value={`${profileData.llm.currency ?? "£"}${profileData.llm.monthly_budget}`}
              />
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-400 py-2">Loading LLM configuration…</p>
        )}
        <p className="mt-4 text-xs text-slate-400">
          Switch providers by editing <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">profile.yaml</code> · <Link href="/settings/profile" className="text-brand-600 hover:underline">Open editor →</Link>
        </p>
      </SectionCard>

      {/* Section 6: About */}
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
            value={profileData?.llm?.primary_model ?? "—"}
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
