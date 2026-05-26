"use client";

const FILLER_PATTERN = /\b(um|uh|er|ah|hmm|basically|literally|actually|honestly|right|like|so)\b/gi;

interface TranscriptDisplayProps {
  transcript: string;
  isFinal: boolean;
}

function FillerHighlight({ text }: { text: string }) {
  const parts = text.split(FILLER_PATTERN);
  const fillers = new Set(["um","uh","er","ah","hmm","basically","literally","actually","honestly","right","like","so"]);
  return (
    <>
      {parts.map((part, i) =>
        fillers.has(part.toLowerCase()) ? (
          <mark key={i} className="bg-amber-500/30 text-amber-300 rounded px-0.5">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export function TranscriptDisplay({ transcript, isFinal }: TranscriptDisplayProps) {
  if (!transcript) {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-slate-600 bg-slate-800/50">
        <p className="text-sm text-slate-500">Your transcript will appear here as you speak…</p>
      </div>
    );
  }

  return (
    <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-700 bg-slate-800 p-4">
      <p className={`text-sm leading-relaxed ${isFinal ? "text-slate-200" : "text-slate-400"}`}>
        <FillerHighlight text={transcript} />
      </p>
      {!isFinal && (
        <span className="inline-block h-4 w-0.5 animate-pulse bg-indigo-400 align-middle ml-0.5" />
      )}
    </div>
  );
}
