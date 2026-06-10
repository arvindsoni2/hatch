"use client";

import { Button } from "@/components/ui/button";
import { Camera, EyeOff, Shield } from "lucide-react";

interface ConsentGateProps {
  onAccept: () => void;
  onDecline: () => void;
}

/**
 * ConsentGate — explains face analysis and asks for explicit user consent.
 *
 * What it collects: facial blendshapes + head pose angles (numeric summaries only).
 * What is NOT sent to the server: raw video frames, JPEG/PNG images, video stream.
 */
export function ConsentGate({ onAccept, onDecline }: ConsentGateProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-600 bg-slate-800 p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-900">
            <Camera className="h-5 w-5 text-indigo-300" />
          </div>
          <h2 id="consent-title" className="text-lg font-semibold text-slate-100">
            Enable Face Analysis?
          </h2>
        </div>

        {/* What it does */}
        <p className="mb-4 text-sm text-slate-300">
          When enabled, your webcam feed is analysed locally in your browser using{" "}
          <span className="font-medium text-slate-100">MediaPipe Face Landmarker</span>. The
          analysis measures:
        </p>
        <ul className="mb-4 space-y-1 text-sm text-slate-300">
          <li className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Eye contact percentage — how often you look at the camera
          </li>
          <li className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Head stability — movement during your answer
          </li>
          <li className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Engagement trend — rising or falling across your answer
          </li>
        </ul>

        {/* What is NOT sent */}
        <div className="mb-5 rounded-lg border border-emerald-800/60 bg-emerald-950/30 p-3">
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-emerald-400">
            <Shield className="h-3.5 w-3.5" />
            Privacy guarantee
          </div>
          <div className="flex items-start gap-2 text-sm text-emerald-200">
            <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            <span>
              Raw video, individual frames, and images are{" "}
              <span className="font-semibold">never sent to the server</span>. Only numeric
              summaries (e.g. eye_contact_pct = 0.82) are uploaded.
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Button
            onClick={onDecline}
            variant="outline"
            className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            Cancel
          </Button>
          <Button
            onClick={onAccept}
            className="flex-1 bg-indigo-600 text-white hover:bg-indigo-500"
          >
            Enable face analysis
          </Button>
        </div>
      </div>
    </div>
  );
}
