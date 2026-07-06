"use client"

import { useState } from "react"
import { Eye } from "lucide-react"
import { Button } from "@/components/ui/button"
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
      <Button
        onClick={() => void handlePreview()}
        loading={loading}
        variant="outline"
        className="w-fit"
      >
        {loading ? null : <Eye aria-hidden="true" className="h-4 w-4" />}
        {loading ? "Loading…" : "Preview Today’s Digest"}
      </Button>
      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}
    </div>
  )
}
