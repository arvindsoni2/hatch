"use client"

import { useState } from "react"
import { getDigestPreview } from "../lib/api"

export function DigestPreview() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handlePreview = async () => {
    setLoading(true)
    setError(null)
    try {
      const html = await getDigestPreview()
      const blob = new Blob([html], { type: "text/html" })
      const url = URL.createObjectURL(blob)
      window.open(url, "_blank", "noopener,noreferrer")
      // Revoke after a short delay to allow the new tab to load
      setTimeout(() => URL.revokeObjectURL(url), 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load digest preview")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={() => void handlePreview()}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors w-fit"
      >
        {loading ? (
          <>
            <svg className="h-4 w-4 animate-spin text-slate-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Loading…
          </>
        ) : (
          <>
            <svg className="h-4 w-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            Preview Today&#39;s Digest
          </>
        )}
      </button>
      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}
    </div>
  )
}
