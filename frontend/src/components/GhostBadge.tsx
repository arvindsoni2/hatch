"use client"
import { useState } from "react"
import { overrideGhostVerdict } from "@/lib/api"

interface Props {
  score?: number | null
  verdict?: string | null
  signals?: unknown[] | null
  jobId?: string
  onOverride?: (newVerdict: string) => void
}

const VERDICT_CONFIG: Record<string, { label: string; icon: string; className: string }> = {
  likely_ghost: {
    label: "Likely ghost",
    icon: "⛔",
    className: "bg-red-100 text-red-800 border-red-200",
  },
  suspicious: {
    label: "Suspicious",
    icon: "⚠",
    className: "bg-orange-100 text-orange-800 border-orange-200",
  },
  uncertain: {
    label: "Unverified",
    icon: "⚠",
    className: "bg-yellow-100 text-yellow-800 border-yellow-200",
  },
}

function formatSignal(sig: unknown): string {
  if (Array.isArray(sig) && sig.length >= 1) {
    const name = String(sig[0]).replace(/_/g, " ")
    const detail = sig[1] != null ? ` (${sig[1]})` : ""
    return name + detail
  }
  return String(sig)
}

export function GhostBadge({ score, verdict, signals, jobId, onOverride }: Props) {
  const [showTooltip, setShowTooltip] = useState(false)
  const [overriding, setOverriding] = useState(false)

  if (!verdict || verdict === "likely_real" || score == null || score < 25) return null

  const config = VERDICT_CONFIG[verdict]
  if (!config) return null

  async function handleOverride() {
    if (!jobId) return
    const newVerdict = verdict === "likely_ghost" ? "likely_real" : "likely_ghost"
    setOverriding(true)
    try {
      await overrideGhostVerdict(jobId, newVerdict)
      onOverride?.(newVerdict)
    } catch {
      // silently ignore
    } finally {
      setOverriding(false)
      setShowTooltip(false)
    }
  }

  const signalList = Array.isArray(signals) ? signals : []

  return (
    <div className="relative inline-block">
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border cursor-pointer ${config.className}`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <span>{config.icon}</span>
        {config.label}
      </span>

      {showTooltip && (
        <div
          className="absolute z-50 bottom-full left-0 mb-1 w-72 bg-gray-900 text-white text-xs rounded p-3 shadow-lg"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
        >
          <div className="font-semibold mb-1">
            Ghost score: {score}/100
          </div>
          {signalList.length > 0 && (
            <ul className="space-y-0.5 mb-2">
              {signalList.map((sig, i) => (
                <li key={i} className="text-gray-300">• {formatSignal(sig)}</li>
              ))}
            </ul>
          )}
          {jobId && (
            <button
              onClick={handleOverride}
              disabled={overriding}
              className="mt-1 text-blue-300 hover:text-blue-100 underline disabled:opacity-50"
            >
              {overriding
                ? "Saving..."
                : verdict === "likely_ghost"
                ? "Mark as Real"
                : "Mark as Ghost"}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
