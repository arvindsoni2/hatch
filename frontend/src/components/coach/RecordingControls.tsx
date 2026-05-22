"use client";

import { Mic, Video, Type } from "lucide-react";

type RecordingMode = "audio" | "video" | "text";

interface RecordingControlsProps {
  mode: RecordingMode;
  onChange: (mode: RecordingMode) => void;
  disabled?: boolean;
}

const MODES: { value: RecordingMode; label: string; Icon: React.ElementType }[] = [
  { value: "text", label: "Text", Icon: Type },
  { value: "audio", label: "Audio", Icon: Mic },
  { value: "video", label: "Video", Icon: Video },
];

export function RecordingControls({ mode, onChange, disabled }: RecordingControlsProps) {
  return (
    <div className="inline-flex rounded-lg border border-slate-700 bg-slate-800 p-0.5">
      {MODES.map(({ value, label, Icon }) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          disabled={disabled}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            mode === value
              ? "bg-indigo-600 text-white"
              : "text-slate-400 hover:text-slate-200 disabled:opacity-50"
          }`}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
