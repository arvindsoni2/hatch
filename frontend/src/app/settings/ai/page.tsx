"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import {
  API_BASE,
  fetchEnvStatus,
  saveApiKey,
  fetchOllamaModels,
  saveOllamaModel,
  type EnvStatus,
} from "@/lib/api"

// ── Shared primitives ──────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl shadow-sm" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
      <div className="px-6 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>{title}</h2>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  )
}

function Badge({ variant, children }: { variant: "green" | "amber" | "slate"; children: React.ReactNode }) {
  const cls = {
    green: "bg-green-100 text-green-800",
    amber: "bg-amber-100 text-amber-700",
    slate: "bg-surface-2 text-dim",
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

// ── Constants ──────────────────────────────────────────────────────

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

const FREE_PROVIDERS = new Set(["ollama"])

// ── Spend readout ─────────────────────────────────────────────────

interface MonthlyCost {
  total: number;
  by_agent: Record<string, number>;
  month: string;
}

function SpendReadout({ provider }: { provider?: string }) {
  const [cost, setCost] = useState<MonthlyCost | null>(null)
  useEffect(() => {
    fetch(`${API_BASE}/api/analytics/costs/monthly`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: MonthlyCost | null) => { if (d) setCost(d) })
      .catch(() => {})
  }, [])

  const isFree = provider ? FREE_PROVIDERS.has(provider) : false

  return (
    <SectionCard title="LLM Spend">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[22px] font-[600] text-[var(--text)] tabular-nums">
              {cost?.total != null ? `$${cost.total.toFixed(4)}` : "—"}
            </span>
            <span className="text-sm text-[var(--text-dim)]">this month</span>
            {isFree && (
              <span className="inline-flex items-center rounded-full bg-green-100 text-green-800 px-2 py-0.5 text-xs font-medium">
                FREE
              </span>
            )}
            {provider && !isFree && (
              <span className="inline-flex items-center rounded-full bg-amber-100 text-amber-700 px-2 py-0.5 text-xs font-medium">
                PAID
              </span>
            )}
          </div>
          {cost && cost.total > 0 && Object.keys(cost.by_agent).length > 0 && (
            <div className="mt-3 space-y-1">
              {Object.entries(cost.by_agent)
                .sort(([, a], [, b]) => b - a)
                .map(([agent, spend]) => (
                  <div key={agent} className="flex items-center gap-2 text-[12px]">
                    <span className="w-28 text-[var(--text-dim)] truncate capitalize">{agent.replace(/_/g, " ")}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
                      <div
                        className="h-full bg-[var(--accent)] rounded-full"
                        style={{ width: `${Math.min(100, (spend / cost.total) * 100).toFixed(1)}%` }}
                      />
                    </div>
                    <span className="w-14 text-right text-[var(--text-dim)] tabular-nums">${spend.toFixed(4)}</span>
                  </div>
                ))}
            </div>
          )}
          {isFree && (
            <p className="text-[12px] text-[var(--text-dim)] mt-2">
              Ollama runs locally — no API charges. Set <code className="bg-[var(--surface-2)] rounded px-1">track_costs: false</code> in profile.yaml to hide this panel.
            </p>
          )}
        </div>
      </div>
    </SectionCard>
  )
}

// ── Page ───────────────────────────────────────────────────────────

export default function AiSettingsPage() {
  // Profile data (for Ollama model picker)
  const [currentProvider, setCurrentProvider] = useState<string | undefined>()
  const [currentPrimaryModel, setCurrentPrimaryModel] = useState<string | undefined>()
  const [currentTriageModel, setCurrentTriageModel] = useState<string | undefined>()

  useEffect(() => {
    fetch(`${API_BASE}/api/v2/profile`)
      .then((r) => r.json())
      .then((d) => {
        setCurrentProvider(d?.llm?.provider)
        setCurrentPrimaryModel(d?.llm?.primary_model)
        setCurrentTriageModel(d?.llm?.triage_model)
      })
      .catch(() => {})
  }, [])

  // Provider status
  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)

  // API key form
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
      // silent
    } finally {
      setLoadingStatus(false)
    }
  }

  useEffect(() => { void loadStatus() }, [])

  useEffect(() => {
    if (currentProvider !== "ollama") return
    setOllamaLoading(true)
    setOllamaError(null)
    fetchOllamaModels()
      .then((r) => {
        setOllamaModels(r.models)
        if (r.error) setOllamaError("Ollama unreachable — is it running?")
        if (r.models.length > 0) {
          setSelectedPrimary(currentPrimaryModel && r.models.includes(currentPrimaryModel) ? currentPrimaryModel : r.models[0])
          setSelectedTriage(currentTriageModel && r.models.includes(currentTriageModel) ? currentTriageModel : (r.models.length > 1 ? r.models[1] : r.models[0]))
        }
      })
      .catch(() => setOllamaError("Could not fetch Ollama models"))
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
    <div className="space-y-6 max-w-3xl">
      {/* Back nav */}
      <Link
        href="/settings"
        className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"
      >
        <ArrowLeft className="h-4 w-4" /> Settings
      </Link>

      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text)" }}>AI Provider</h1>
        <p className="mt-1 text-sm text-muted">Configure your AI provider, API keys, and model preferences.</p>
      </div>

      {/* Configured Providers */}
      <SectionCard title="Configured Providers">
        {loadingStatus ? (
          <div className="flex items-center gap-2 text-sm text-muted py-2"><Spinner /> Loading…</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {Object.entries(PROVIDER_LABELS).map(([provider, label]) => {
              const info = configured[provider]
              const isActive = envStatus?.current_provider === provider
              return (
                <div key={provider} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className={`h-2 w-2 rounded-full shrink-0 ${info?.set || FREE_PROVIDERS.has(provider) ? "bg-green-500" : "bg-[var(--border-strong)]"}`} />
                    <span className="text-sm font-medium text-fg">{label}</span>
                    {isActive && <Badge variant="green">active</Badge>}
                    {FREE_PROVIDERS.has(provider)
                      ? <Badge variant="green">free</Badge>
                      : <Badge variant="amber">paid</Badge>}
                  </div>
                  <div className="flex items-center gap-2 text-right">
                    {info?.masked && (
                      <code className="text-xs px-1.5 py-0.5 rounded" style={{ color: "var(--text-muted)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                        {info.masked}
                      </code>
                    )}
                    {provider === "ollama" && (
                      <span className="text-xs text-muted">no key needed</span>
                    )}
                    {!info?.set && provider !== "ollama" && (
                      <span className="text-xs text-muted">not set</span>
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
              <label className="block text-xs font-medium text-dim mb-1">Provider</label>
              <select
                value={selectedKeyName}
                onChange={(e) => setSelectedKeyName(e.target.value)}
                className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
              >
                {Object.entries(KEY_PROVIDER_MAP).map(([envVar, provider]) => (
                  <option key={envVar} value={envVar}>
                    {PROVIDER_LABELS[provider] ?? provider} ({envVar})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-dim mb-1">API Key</label>
              <input
                ref={inputRef}
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="Paste key here…"
                className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
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
          <p className="text-xs text-muted">
            The key is validated via a test call before being saved to{" "}
            <code className="bg-surface-2 rounded px-1">data/api_keys.env</code>. The actual key value is never returned by the API.
          </p>
        </div>
      </SectionCard>

      {/* Ollama model picker — only shown when provider is ollama */}
      {currentProvider === "ollama" && (
        <SectionCard title="Ollama Models">
          {ollamaLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted py-2"><Spinner /> Fetching installed models…</div>
          ) : ollamaError ? (
            <p className="text-sm text-red-600 py-2">{ollamaError}</p>
          ) : ollamaModels.length === 0 ? (
            <p className="text-sm text-muted py-2">No models found — pull a model with <code className="bg-surface-2 rounded px-1">ollama pull &lt;model&gt;</code> first.</p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-dim mb-1">
                    Primary model <span className="text-muted font-normal">(tailoring, coach, analysis)</span>
                  </label>
                  <select
                    value={selectedPrimary}
                    onChange={(e) => setSelectedPrimary(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                  >
                    {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-dim mb-1">
                    Triage model <span className="text-muted font-normal">(fast pre-filtering)</span>
                  </label>
                  <select
                    value={selectedTriage}
                    onChange={(e) => setSelectedTriage(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
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

      {/* LLM spend readout */}
      <SpendReadout provider={currentProvider} />

      {/* Scoring strategy */}
      <SectionCard title="Scoring Strategy">
        <p className="text-sm text-dim mb-3">
          Set <code className="bg-surface-2 rounded px-1">scoring.method</code> in{" "}
          <code className="bg-surface-2 rounded px-1">data/profile.yaml</code> to control LLM usage:
        </p>
        <div className="space-y-2">
          {[
            { val: "auto",   desc: "Hybrid for free-tier providers, full LLM for paid (default)" },
            { val: "hybrid", desc: "Local keyword scoring first; only top 20% sent to LLM" },
            { val: "local",  desc: "Keyword-only — zero LLM cost, faster but less accurate" },
            { val: "llm",    desc: "Full LLM scoring for every job (highest accuracy, most tokens)" },
          ].map(({ val, desc }) => (
            <div key={val} className="flex items-start gap-2 text-sm">
              <code className="mt-0.5 shrink-0 rounded bg-indigo-50 text-indigo-700 px-1.5 py-0.5 text-xs font-mono">{val}</code>
              <span className="text-dim">{desc}</span>
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
