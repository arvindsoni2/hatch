"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import {
  getDigestStatus,
  updateDigestSettings,
  sendDigest,
  DigestStatus,
  API_BASE,
  fetchEnvStatus,
  saveApiKey,
  EnvStatus,
  fetchOllamaModels,
  saveOllamaModel,
} from "../../lib/api"
import { DigestPreview } from "../../components/DigestPreview"

// ── Shared primitives ──────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-6 py-4">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  )
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-start sm:justify-between sm:gap-4 py-2.5 border-b border-slate-100 last:border-0">
      <span className="text-sm font-medium text-slate-500 sm:shrink-0 sm:w-48">{label}</span>
      <span className="text-sm text-slate-800 sm:text-right">{value}</span>
    </div>
  )
}

function Badge({ variant, children }: { variant: "green" | "amber" | "slate"; children: React.ReactNode }) {
  const cls = {
    green: "bg-green-100 text-green-800",
    amber: "bg-amber-100 text-amber-700",
    slate: "bg-slate-100 text-slate-600",
  }[variant]
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {children}
    </span>
  )
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

// ── Profile data types ─────────────────────────────────────────────

interface ProfileData {
  locale?: string
  candidate?: { name?: string; title?: string; years_experience?: number; summary?: string }
  search?: {
    target_roles?: string[]
    locations?: { city?: string; country?: string; remote_preference?: string }[]
    contract_type?: string
    scrape_interval_hours?: number
  }
  compensation?: {
    min_rate?: number
    max_rate?: number
    currency?: string
    rate_type?: string
    ir35_preference?: string
    legal_preferences?: Record<string, string>
  }
  skills?: { primary?: string[]; secondary?: string[]; certifications?: string[] }
  scoring?: { method?: string; shortlist_threshold?: number }
  llm?: {
    provider?: string
    primary_model?: string
    triage_model?: string
    api_key_env?: string
    temperature?: number
    monthly_budget?: number
    currency?: string
  }
  job_boards?: { name: string; enabled: boolean; scraper: string }[]
  preferences?: { scrape_interval_hours?: number; archive_after_days?: number; follow_up_days?: number[] }
}

// ── Tab: Profile ───────────────────────────────────────────────────

function ProfileTab({ data }: { data: ProfileData | null }) {
  if (!data) return <p className="text-sm text-slate-400 py-4">Loading profile…</p>

  const roles = data.search?.target_roles ?? []
  const loc = data.search?.locations?.[0]
  const location = [loc?.city, loc?.country].filter(Boolean).join(", ") || "—"
  const comp = data.compensation
  const rateLabel =
    comp && (comp.min_rate ?? 0) > 0 && (comp.max_rate ?? 0) > 0
      ? `${comp.currency ?? "£"}${comp.min_rate}–${comp.max_rate}/${comp.rate_type === "daily" ? "day" : "hr"}`
      : comp && (comp.min_rate ?? 0) > 0
      ? `${comp.currency ?? "£"}${comp.min_rate}+/${comp.rate_type === "daily" ? "day" : "hr"}`
      : "Not set"

  const allLocations = (data.search?.locations ?? [])
    .map((l) => [l.city, l.country].filter(Boolean).join(", "))
    .join(" · ") || "—"

  return (
    <div className="space-y-6">
      <SectionCard title="Candidate">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Name" value={data.candidate?.name ?? "—"} />
          <FieldRow label="Title" value={data.candidate?.title ?? "—"} />
          <FieldRow label="Years of experience" value={data.candidate?.years_experience != null ? `${data.candidate.years_experience}+` : "—"} />
          <FieldRow label="Locale" value={data.locale ?? "—"} />
        </div>
        {data.candidate?.summary && (
          <p className="mt-3 text-xs text-slate-500 leading-relaxed line-clamp-3">{data.candidate.summary}</p>
        )}
      </SectionCard>

      <SectionCard title="Job Search">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Target roles" value={roles.join(", ") || "—"} />
          <FieldRow label="Locations" value={allLocations} />
          <FieldRow label="Remote preference" value={loc?.remote_preference ?? "—"} />
          <FieldRow label="Job type" value={data.search?.contract_type ?? "—"} />
          <FieldRow label="Rate expectation" value={rateLabel} />
          <FieldRow label="Legal preference" value={comp?.legal_preferences ? Object.values(comp.legal_preferences)[0] ?? "—" : "—"} />
        </div>
      </SectionCard>

      <SectionCard title="Skills">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-medium text-slate-500 mb-1.5">Primary</p>
            <div className="flex flex-wrap gap-1.5">
              {(data.skills?.primary ?? []).map((s) => (
                <span key={s} className="rounded-full bg-indigo-100 text-indigo-700 px-2.5 py-0.5 text-xs font-medium">{s}</span>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-1.5">Secondary / Certifications</p>
            <div className="flex flex-wrap gap-1.5">
              {(data.skills?.secondary ?? []).concat(data.skills?.certifications ?? []).map((s) => (
                <span key={s} className="rounded-full bg-slate-100 text-slate-600 px-2.5 py-0.5 text-xs font-medium">{s}</span>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      <p className="text-xs text-slate-400">
        Edit full profile in{" "}
        <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">data/profile.yaml</code>
        {" "}·{" "}
        <Link href="/settings/profile" className="text-brand-600 hover:underline">Open YAML editor →</Link>
      </p>
    </div>
  )
}

// ── Tab: Resume ────────────────────────────────────────────────────

function ResumeTab() {
  return (
    <div className="space-y-6">
      <SectionCard title="Master CV">
        <p className="text-sm text-slate-600 mb-4">
          Upload and manage your master CV. Hatch parses it to extract work experience,
          skills, and proof points used when tailoring applications.
        </p>
        <Link
          href="/settings/resume"
          className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
        >
          Open Resume Manager →
        </Link>
      </SectionCard>

      <SectionCard title="Proof Points">
        <p className="text-sm text-slate-500 mb-3">
          Proof points are quantified achievements injected into every tailored CV.
          Edit them in your profile YAML.
        </p>
        <Link href="/settings/profile" className="text-sm text-brand-600 hover:underline">
          Edit proof points in profile.yaml →
        </Link>
      </SectionCard>
    </div>
  )
}

// ── Tab: AI Provider ───────────────────────────────────────────────

const KEY_PROVIDER_MAP: Record<string, string> = {
  ANTHROPIC_API_KEY: "anthropic",
  OPENAI_API_KEY: "openai",
  GOOGLE_API_KEY: "google_genai",
  GOOGLE_GENAI_API_KEY: "google_genai",
  AZURE_OPENAI_API_KEY: "azure_openai",
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI (GPT)",
  google_genai: "Google Gemini",
  azure_openai: "Azure OpenAI",
  ollama: "Ollama (local, free)",
}

function AiProviderTab({ currentProvider, currentPrimaryModel, currentTriageModel }: { currentProvider?: string; currentPrimaryModel?: string; currentTriageModel?: string }) {
  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [selectedKeyName, setSelectedKeyName] = useState("GOOGLE_API_KEY")
  const [keyValue, setKeyValue] = useState("")
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Ollama model state
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [ollamaError, setOllamaError] = useState<string | null>(null)
  const [selectedPrimary, setSelectedPrimary] = useState("")
  const [selectedTriage, setSelectedTriage] = useState("")
  const [savingModel, setSavingModel] = useState(false)
  const [modelResult, setModelResult] = useState<{ ok: boolean; message: string } | null>(null)

  const loadStatus = async () => {
    setLoadingStatus(true)
    try {
      const s = await fetchEnvStatus()
      setEnvStatus(s)
    } catch {
      // silent — show stale data
    } finally {
      setLoadingStatus(false)
    }
  }

  useEffect(() => { void loadStatus() }, [])

  useEffect(() => {
    if (currentProvider !== "ollama") return
    setOllamaLoading(true)
    setOllamaError(null)
    fetchOllamaModels().then((r) => {
      setOllamaModels(r.models)
      if (r.error) setOllamaError("Ollama unreachable — is it running?")
      if (r.models.length > 0) {
        // Pre-populate from current profile values if they exist in the model list,
        // otherwise default to first available model
        setSelectedPrimary(currentPrimaryModel && r.models.includes(currentPrimaryModel) ? currentPrimaryModel : r.models[0])
        setSelectedTriage(currentTriageModel && r.models.includes(currentTriageModel) ? currentTriageModel : (r.models.length > 1 ? r.models[1] : r.models[0]))
      }
    }).catch(() => setOllamaError("Could not fetch Ollama models"))
      .finally(() => setOllamaLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProvider])

  const handleSaveModel = async () => {
    if (!selectedPrimary) return
    setSavingModel(true)
    setModelResult(null)
    try {
      await saveOllamaModel(selectedPrimary, selectedTriage)
      setModelResult({ ok: true, message: `Saved — primary: ${selectedPrimary}, triage: ${selectedTriage}` })
    } catch (err) {
      setModelResult({ ok: false, message: err instanceof Error ? err.message : "Save failed" })
    } finally {
      setSavingModel(false)
    }
  }

  const handleSave = async () => {
    if (!keyValue.trim()) return
    setSaving(true)
    setResult(null)
    try {
      const r = await saveApiKey(selectedKeyName, keyValue.trim())
      if (r.valid) {
        setResult({
          ok: true,
          message: `Saved! Provider set to ${PROVIDER_LABELS[r.provider ?? ""] ?? r.provider}. Models available: ${(r.models_available ?? []).join(", ")}.`,
        })
        setKeyValue("")
        await loadStatus()
      } else {
        setResult({ ok: false, message: r.error ?? "Key validation failed." })
      }
    } catch (err) {
      setResult({ ok: false, message: err instanceof Error ? err.message : "Request failed" })
    } finally {
      setSaving(false)
    }
  }

  const configured = envStatus?.configured_providers ?? {}

  return (
    <div className="space-y-6">
      {/* Current status */}
      <SectionCard title="Configured Providers">
        {loadingStatus ? (
          <div className="flex items-center gap-2 text-sm text-slate-500 py-2"><Spinner /> Loading…</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {Object.entries(PROVIDER_LABELS).map(([provider, label]) => {
              const info = configured[provider]
              const isActive = envStatus?.current_provider === provider
              return (
                <div key={provider} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className={`h-2 w-2 rounded-full shrink-0 ${info?.set ? "bg-green-500" : "bg-slate-300"}`} />
                    <span className="text-sm font-medium text-slate-700">{label}</span>
                    {isActive && <Badge variant="green">active</Badge>}
                  </div>
                  <div className="flex items-center gap-2 text-right">
                    {info?.masked && (
                      <code className="text-xs text-slate-400 bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded">
                        {info.masked}
                      </code>
                    )}
                    {provider === "ollama" && (
                      <span className="text-xs text-slate-400">no key needed</span>
                    )}
                    {!info?.set && provider !== "ollama" && (
                      <span className="text-xs text-slate-400">not set</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </SectionCard>

      {/* Add / update key */}
      <SectionCard title="Add or Update API Key">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Provider</label>
              <select
                value={selectedKeyName}
                onChange={(e) => setSelectedKeyName(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {Object.entries(KEY_PROVIDER_MAP).map(([envVar, provider]) => (
                  <option key={envVar} value={envVar}>
                    {PROVIDER_LABELS[provider] ?? provider} ({envVar})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">API Key</label>
              <input
                ref={inputRef}
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="Paste key here…"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500"
                onKeyDown={(e) => { if (e.key === "Enter") void handleSave() }}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => void handleSave()}
              disabled={saving || !keyValue.trim()}
              className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {saving ? <><Spinner /> Validating…</> : "Save & Validate"}
            </button>
            {result && (
              <p className={`text-sm font-medium ${result.ok ? "text-green-700" : "text-red-600"}`}>
                {result.ok ? "✓ " : "✗ "}{result.message}
              </p>
            )}
          </div>

          <p className="text-xs text-slate-400">
            The key is validated via a test call before being saved to{" "}
            <code className="bg-slate-100 rounded px-1">data/api_keys.env</code>. The actual key value is never returned by the API.
          </p>
        </div>
      </SectionCard>

      {/* Ollama model picker — only shown when provider is ollama */}
      {currentProvider === "ollama" && (
        <SectionCard title="Ollama Models">
          {ollamaLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-2"><Spinner /> Fetching installed models…</div>
          ) : ollamaError ? (
            <p className="text-sm text-red-600 py-2">{ollamaError}</p>
          ) : ollamaModels.length === 0 ? (
            <p className="text-sm text-slate-400 py-2">No models found — pull a model with <code className="bg-slate-100 rounded px-1">ollama pull &lt;model&gt;</code> first.</p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Primary model <span className="text-slate-400 font-normal">(tailoring, coach, analysis)</span></label>
                  <select
                    value={selectedPrimary}
                    onChange={(e) => setSelectedPrimary(e.target.value)}
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Triage model <span className="text-slate-400 font-normal">(fast pre-filtering)</span></label>
                  <select
                    value={selectedTriage}
                    onChange={(e) => setSelectedTriage(e.target.value)}
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => void handleSaveModel()}
                  disabled={savingModel || !selectedPrimary}
                  className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
                >
                  {savingModel ? <><Spinner /> Saving…</> : "Save Models"}
                </button>
                {modelResult && (
                  <p className={`text-sm font-medium ${modelResult.ok ? "text-green-700" : "text-red-600"}`}>
                    {modelResult.ok ? "✓ " : "✗ "}{modelResult.message}
                  </p>
                )}
              </div>
            </div>
          )}
        </SectionCard>
      )}

      {/* Scoring strategy */}
      <SectionCard title="Scoring Strategy">
        <p className="text-sm text-slate-600 mb-3">
          Set <code className="bg-slate-100 rounded px-1">scoring.method</code> in{" "}
          <code className="bg-slate-100 rounded px-1">data/profile.yaml</code> to control LLM usage:
        </p>
        <div className="space-y-2">
          {[
            { val: "auto", desc: "Hybrid for free-tier providers, full LLM for paid (default)" },
            { val: "hybrid", desc: "Local keyword scoring first; only top 20% sent to LLM" },
            { val: "local", desc: "Keyword-only — zero LLM cost, faster but less accurate" },
            { val: "llm", desc: "Full LLM scoring for every job (highest accuracy, most tokens)" },
          ].map(({ val, desc }) => (
            <div key={val} className="flex items-start gap-2 text-sm">
              <code className="mt-0.5 shrink-0 rounded bg-indigo-50 text-indigo-700 px-1.5 py-0.5 text-xs font-mono">{val}</code>
              <span className="text-slate-600">{desc}</span>
            </div>
          ))}
        </div>
        <Link href="/settings/profile" className="mt-3 block text-xs text-brand-600 hover:underline">
          Edit scoring.method in profile.yaml →
        </Link>
      </SectionCard>
    </div>
  )
}

// ── Tab: Job Boards ────────────────────────────────────────────────

function JobBoardsTab({ data }: { data: ProfileData | null }) {
  const boards = data?.job_boards ?? []
  const scrapeInterval = data?.preferences?.scrape_interval_hours ?? data?.search?.scrape_interval_hours ?? 4
  const locale = data?.locale ?? "uk"

  return (
    <div className="space-y-6">
      <SectionCard title="Active Boards">
        <p className="text-sm text-slate-500 mb-4">
          Boards are automatically determined by your locale <Badge variant="slate">{locale}</Badge>.
          Change the <code className="bg-slate-100 rounded px-1">locale</code> key in profile.yaml to switch regions.
        </p>
        {boards.length > 0 ? (
          <div className="divide-y divide-slate-100">
            {boards.map((board) => (
              <div key={board.name} className="flex items-center justify-between py-2.5">
                <div className="flex items-center gap-2.5">
                  <span className={`h-2 w-2 rounded-full shrink-0 ${board.enabled ? "bg-green-500" : "bg-slate-300"}`} />
                  <span className="text-sm font-medium text-slate-700">{board.name}</span>
                  {board.scraper && (
                    <span className="text-xs text-slate-400">({board.scraper})</span>
                  )}
                </div>
                <Badge variant={board.enabled ? "green" : "slate"}>
                  {board.enabled ? "Active" : "Disabled"}
                </Badge>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-400 py-2">
            No job boards configured. Add boards under <code className="bg-slate-100 rounded px-1">job_boards</code> in profile.yaml.
          </p>
        )}
        <p className="mt-3 text-xs text-slate-400">
          Scrape interval: every {scrapeInterval} hours ·{" "}
          <Link href="/settings/profile" className="text-brand-600 hover:underline">Edit →</Link>
        </p>
      </SectionCard>

      <SectionCard title="Locale">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Current locale" value={<Badge variant="slate">{locale}</Badge>} />
          <FieldRow
            label="Available locales"
            value={
              <div className="flex gap-1.5">
                {["uk", "in"].map((l) => (
                  <Badge key={l} variant={l === locale ? "green" : "slate"}>{l}</Badge>
                ))}
              </div>
            }
          />
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Change locale in <code className="bg-slate-100 rounded px-1">profile.yaml</code> under the <code className="bg-slate-100 rounded px-1">locale</code> key.
          Board availability and scoring rules adapt automatically.
        </p>
      </SectionCard>
    </div>
  )
}

// ── Tab: System ────────────────────────────────────────────────────

function toBoolean(val: unknown): boolean {
  if (typeof val === "boolean") return val
  if (typeof val === "string") return val.toLowerCase() === "true" || val === "1"
  if (typeof val === "number") return val === 1
  return false
}

function SystemTab({ profileData }: { profileData: ProfileData | null }) {
  const [digestStatus, setDigestStatus] = useState<DigestStatus | null>(null)
  const [digestLoading, setDigestLoading] = useState(true)
  const [digestError, setDigestError] = useState<string | null>(null)
  const [sendingDigest, setSendingDigest] = useState(false)
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null)
  const [editingTimezone, setEditingTimezone] = useState(false)
  const [timezoneInput, setTimezoneInput] = useState("")
  const [savingTimezone, setSavingTimezone] = useState(false)

  useEffect(() => {
    const load = async () => {
      setDigestLoading(true)
      try {
        const status = await getDigestStatus()
        setDigestStatus(status)
        setTimezoneInput(status.timezone || "UTC")
      } catch (err) {
        setDigestError(err instanceof Error ? err.message : "Failed to load digest status")
      } finally {
        setDigestLoading(false)
      }
    }
    void load()
  }, [])

  const handleSaveTimezone = async () => {
    if (!timezoneInput.trim()) return
    setSavingTimezone(true)
    try {
      const updated = await updateDigestSettings({ timezone: timezoneInput.trim() })
      setDigestStatus(updated)
      setEditingTimezone(false)
      setToast({ ok: true, message: "Timezone updated" })
      setTimeout(() => setToast(null), 3000)
    } catch (err) {
      setToast({ ok: false, message: err instanceof Error ? err.message : "Failed to update timezone" })
      setTimeout(() => setToast(null), 4000)
    } finally {
      setSavingTimezone(false)
    }
  }

  const handleSendDigest = async () => {
    setSendingDigest(true)
    try {
      const result = await sendDigest()
      setToast({ ok: true, message: result.message || "Digest sent successfully" })
    } catch (err) {
      setToast({ ok: false, message: err instanceof Error ? err.message : "Failed to send digest" })
    } finally {
      setSendingDigest(false)
      setTimeout(() => setToast(null), 4000)
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard title="Daily Digest">
        {digestLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500 py-2"><Spinner /> Loading…</div>
        ) : digestError ? (
          <p className="text-sm text-red-600">{digestError}</p>
        ) : (
          <div className="space-y-4">
            <div className="divide-y divide-slate-100">
              <FieldRow label="Enabled" value={<Badge variant={toBoolean(digestStatus?.enabled) ? "green" : "slate"}>{toBoolean(digestStatus?.enabled) ? "Yes" : "No"}</Badge>} />
              <FieldRow label="Send time" value={typeof digestStatus?.time === "string" && digestStatus.time ? digestStatus.time : "08:00"} />
              <div className="flex items-center justify-between py-3 gap-4">
                <span className="text-sm text-slate-500 shrink-0">Timezone</span>
                {editingTimezone ? (
                  <div className="flex items-center gap-2">
                    <input
                      value={timezoneInput}
                      onChange={(e) => setTimezoneInput(e.target.value)}
                      placeholder="e.g. Asia/Kolkata"
                      className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500 w-44"
                      onKeyDown={(e) => { if (e.key === "Enter") void handleSaveTimezone(); if (e.key === "Escape") setEditingTimezone(false); }}
                      autoFocus
                    />
                    <button
                      onClick={() => void handleSaveTimezone()}
                      disabled={savingTimezone}
                      className="rounded bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      {savingTimezone ? "Saving…" : "Save"}
                    </button>
                    <button onClick={() => setEditingTimezone(false)} className="text-xs text-slate-400 hover:text-slate-600">Cancel</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-900">
                      {digestStatus?.timezone || "UTC"}
                    </span>
                    <button
                      onClick={() => { setTimezoneInput(digestStatus?.timezone || "UTC"); setEditingTimezone(true); }}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      Edit
                    </button>
                  </div>
                )}
              </div>
              <FieldRow label="Frequency" value={typeof digestStatus?.frequency === "string" && digestStatus.frequency ? digestStatus.frequency : "daily"} />
              <FieldRow label="SMTP configured" value={<Badge variant={toBoolean(digestStatus?.smtp_configured) ? "green" : "amber"}>{toBoolean(digestStatus?.smtp_configured) ? "Yes" : "No"}</Badge>} />
            </div>
            <div className="flex items-center gap-3 pt-1">
              <DigestPreview />
              <button
                onClick={() => void handleSendDigest()}
                disabled={sendingDigest}
                className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >
                {sendingDigest ? <><Spinner /> Sending…</> : "Send Now"}
              </button>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Scheduler">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Scrape interval" value={`${profileData?.preferences?.scrape_interval_hours ?? 4} hours`} />
          <FieldRow label="Auto-archive after" value={`${profileData?.preferences?.archive_after_days ?? 30} days`} />
          <FieldRow label="Follow-up days" value={(profileData?.preferences?.follow_up_days ?? [5, 10, 15]).join(", ")} />
        </div>
      </SectionCard>

      <SectionCard title="About">
        <div className="divide-y divide-slate-100">
          <FieldRow label="Application" value="Hatch" />
          <FieldRow label="AI model" value={profileData?.llm?.primary_model ?? "—"} />
          <FieldRow
            label="API documentation"
            value={<a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline">localhost:8000/docs</a>}
          />
          <FieldRow
            label="OpenAPI spec"
            value={<a href="http://localhost:8000/openapi.json" target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline">localhost:8000/openapi.json</a>}
          />
          <FieldRow
            label="Agent events &amp; costs"
            value={<Link href="/analytics" className="text-brand-600 hover:underline">Analytics →</Link>}
          />
        </div>
      </SectionCard>

      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-lg px-4 py-3 shadow-lg text-sm font-medium text-white ${toast.ok ? "bg-green-600" : "bg-red-600"}`}>
          {toast.ok
            ? <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            : <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          }
          {toast.message}
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────

const TABS = ["Profile", "Resume", "AI Provider", "Job Boards", "System"] as const
type Tab = typeof TABS[number]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Profile")
  const [profileData, setProfileData] = useState<ProfileData | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetch(`${API_BASE}/api/v2/profile`).then((r) => r.json() as Promise<ProfileData>)
        setProfileData(data)
      } catch {
        // silent
      }
    }
    void load()
  }, [])

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Configure Hatch — profile, resume, AI provider, job boards, and system.</p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-slate-200">
        <nav className="flex gap-1 -mb-px" aria-label="Settings tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === "Profile" && <ProfileTab data={profileData} />}
      {activeTab === "Resume" && <ResumeTab />}
      {activeTab === "AI Provider" && <AiProviderTab currentProvider={profileData?.llm?.provider} currentPrimaryModel={profileData?.llm?.primary_model} currentTriageModel={profileData?.llm?.triage_model} />}
      {activeTab === "Job Boards" && <JobBoardsTab data={profileData} />}
      {activeTab === "System" && <SystemTab profileData={profileData} />}
    </div>
  )
}
