"use client";

interface LiveFeedbackProps {
  fillerCount: number;
  wpm: number;
  hedgingCount: number;
  isRecording: boolean;
}

function WpmGauge({ wpm }: { wpm: number }) {
  const good = wpm >= 120 && wpm <= 180;
  const ok = (wpm >= 100 && wpm < 120) || (wpm > 180 && wpm <= 200);
  const color = good ? "text-emerald-400" : ok ? "text-amber-400" : "text-red-400";
  return (
    <div className="text-center">
      <p className={`text-xl font-bold tabular-nums ${color}`}>{Math.round(wpm)}</p>
      <p className="text-xs text-slate-500">WPM</p>
    </div>
  );
}

function CountBadge({ value, label, warn }: { value: number; label: string; warn: number }) {
  const color = value >= warn ? "text-red-400" : value > 0 ? "text-amber-400" : "text-emerald-400";
  return (
    <div className="text-center">
      <p className={`text-xl font-bold tabular-nums ${color}`}>{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

export function LiveFeedback({ fillerCount, wpm, hedgingCount, isRecording }: LiveFeedbackProps) {
  if (!isRecording) return null;

  return (
    <div className="flex items-center justify-around rounded-xl border border-slate-700 bg-slate-800 p-4">
      <WpmGauge wpm={wpm} />
      <div className="h-8 w-px bg-slate-700" />
      <CountBadge value={fillerCount} label="Fillers" warn={5} />
      <div className="h-8 w-px bg-slate-700" />
      <CountBadge value={hedgingCount} label="Hedging" warn={3} />
    </div>
  );
}
