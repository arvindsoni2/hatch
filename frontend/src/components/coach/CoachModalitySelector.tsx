"use client";

import { useEffect, useState } from "react";
import { Mic, Type, Video } from "lucide-react";
import { ConsentGate } from "./ConsentGate";

export type CoachMode = "text" | "voice" | "video";

interface ModeConfig {
  value: CoachMode;
  label: string;
  Icon: React.ElementType;
  requires: "microphone" | "camera" | null;
  phaseGate?: "D";  // modes gated behind a future phase are hidden unless explicitly enabled
}

// Ordered mode list — Phase D adds "video" without restructuring this table.
const ALL_MODES: ModeConfig[] = [
  { value: "text",  label: "Text",  Icon: Type,  requires: null },
  { value: "voice", label: "Voice", Icon: Mic,   requires: "microphone" },
  { value: "video", label: "Video", Icon: Video, requires: "camera", phaseGate: "D" },
];

interface CoachModalitySelectorProps {
  mode: CoachMode;
  onModeChange: (mode: CoachMode) => void;
  disabled?: boolean;
  /** Set to true to show the video option (Phase D). Default false. */
  showVideo?: boolean;
}

interface CapabilityState {
  microphone: boolean | null;  // null = checking
  camera: boolean | null;
}

interface ServerCapabilities {
  face_analysis: boolean;
  tts: boolean;
}

const FACE_CONSENT_KEY = "face_consent_given";

async function detectCapabilities(): Promise<{ microphone: boolean; camera: boolean }> {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return { microphone: false, camera: false };
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return {
      microphone: devices.some((d) => d.kind === "audioinput"),
      camera: devices.some((d) => d.kind === "videoinput"),
    };
  } catch {
    return { microphone: false, camera: false };
  }
}

async function fetchServerCapabilities(): Promise<ServerCapabilities> {
  try {
    const res = await fetch("/api/coach/capabilities");
    if (!res.ok) return { face_analysis: false, tts: false };
    return res.json() as Promise<ServerCapabilities>;
  } catch {
    return { face_analysis: false, tts: false };
  }
}

export function CoachModalitySelector({
  mode,
  onModeChange,
  disabled = false,
  showVideo: showVideoProp = false,
}: CoachModalitySelectorProps) {
  const [caps, setCaps] = useState<CapabilityState>({ microphone: null, camera: null });
  const [serverCaps, setServerCaps] = useState<ServerCapabilities>({ face_analysis: false, tts: false });
  const [showConsent, setShowConsent] = useState(false);
  const [pendingMode, setPendingMode] = useState<CoachMode | null>(null);

  useEffect(() => {
    detectCapabilities().then(({ microphone, camera }) => {
      setCaps({ microphone, camera });
    });
    fetchServerCapabilities().then(setServerCaps);
  }, []);

  // Video is shown if: either showVideo prop OR server says face_analysis is available
  const showVideo = showVideoProp || serverCaps.face_analysis;

  const visibleModes = ALL_MODES.filter(
    (m) => m.phaseGate !== "D" || showVideo
  );

  function isModeDisabled(m: ModeConfig): boolean {
    if (disabled) return true;
    if (m.requires === "microphone") return caps.microphone === false;
    if (m.requires === "camera") return caps.camera === false;
    return false;
  }

  function disabledReason(m: ModeConfig): string | null {
    if (m.requires === "microphone" && caps.microphone === false) {
      return "Microphone not available in this browser";
    }
    if (m.requires === "camera" && caps.camera === false) {
      return "Camera not available";
    }
    return null;
  }

  function handleModeClick(m: ModeConfig) {
    if (isModeDisabled(m)) return;
    if (m.value === "video") {
      // Check if consent has already been given
      const alreadyConsented =
        typeof localStorage !== "undefined" &&
        localStorage.getItem(FACE_CONSENT_KEY) === "true";
      if (!alreadyConsented) {
        setPendingMode("video");
        setShowConsent(true);
        return;
      }
    }
    onModeChange(m.value);
  }

  function handleConsentAccept() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(FACE_CONSENT_KEY, "true");
    }
    setShowConsent(false);
    if (pendingMode) {
      onModeChange(pendingMode);
      setPendingMode(null);
    }
  }

  function handleConsentDecline() {
    setShowConsent(false);
    setPendingMode(null);
  }

  // Aggregate reason text shown below the selector (only when a mode is disabled)
  const anyReason = visibleModes.map(disabledReason).find(Boolean) ?? null;

  return (
    <>
      {showConsent && (
        <ConsentGate onAccept={handleConsentAccept} onDecline={handleConsentDecline} />
      )}

      <div className="space-y-1">
        <div className="inline-flex rounded-lg border border-slate-700 bg-slate-800 p-0.5">
          {visibleModes.map((m) => {
            const off = isModeDisabled(m);
            const active = mode === m.value;
            const reason = disabledReason(m);
            return (
              <button
                key={m.value}
                type="button"
                role="button"
                onClick={() => handleModeClick(m)}
                disabled={off}
                aria-disabled={off}
                title={reason ?? m.label}
                className={[
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  active && !off
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200",
                  off ? "cursor-not-allowed opacity-40" : "cursor-pointer",
                ].join(" ")}
              >
                <m.Icon className="h-3.5 w-3.5" />
                {m.label}
              </button>
            );
          })}
        </div>

        {anyReason && (
          <p className="text-xs text-amber-400" role="status">
            {anyReason}
          </p>
        )}
      </div>
    </>
  );
}
