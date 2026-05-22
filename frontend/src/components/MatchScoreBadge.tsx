"use client"
import { useState } from "react"

interface Props {
  score: number | null | undefined
  reasons?: string[] | null
}

export function MatchScoreBadge({ score, reasons }: Props) {
  const [showTooltip, setShowTooltip] = useState(false)

  if (score == null) return null

  const scoreInt = Math.round(score)
  const colorClass =
    scoreInt >= 85
      ? "bg-green-100 text-green-800 border-green-200"
      : scoreInt >= 70
      ? "bg-amber-100 text-amber-800 border-amber-200"
      : "bg-red-100 text-red-800 border-red-200"

  return (
    <div className="relative inline-block">
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border cursor-pointer ${colorClass}`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {scoreInt}% match
      </span>
      {showTooltip && reasons && reasons.length > 0 && (
        <div className="absolute z-50 bottom-full left-0 mb-1 w-64 bg-gray-900 text-white text-xs rounded p-2 shadow-lg">
          <div className="font-semibold mb-1">Match reasons:</div>
          <ul className="space-y-0.5">
            {reasons.map((r, i) => (
              <li key={i} className="text-gray-200">• {r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
