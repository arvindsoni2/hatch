"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SpeechRecogniser } from "@/lib/speech";
import { SpeechMetrics } from "@/lib/api";
import { AnswerTimer } from "./AnswerTimer";
import { LiveFeedback } from "./LiveFeedback";
import { TranscriptDisplay } from "./TranscriptDisplay";

interface VoiceRecorderProps {
  onSubmit: (transcript: string, metrics: SpeechMetrics, durationMs: number) => void;
  disabled?: boolean;
}

export function VoiceRecorder({ onSubmit, disabled }: VoiceRecorderProps) {
  const recogniserRef = useRef<SpeechRecogniser | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [isFinal, setIsFinal] = useState(false);
  const [metrics, setMetrics] = useState<SpeechMetrics>({
    filler_count: 0, wpm: 0, hedging_count: 0, duration_ms: 0, pause_count: 0,
  });
  const [durationMs, setDurationMs] = useState(0);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    recogniserRef.current = new SpeechRecogniser();
    if (!recogniserRef.current.isSupported) setSupported(false);
  }, []);

  const handleStart = () => {
    if (!recogniserRef.current) return;
    setTranscript("");
    setIsFinal(false);
    setIsRecording(true);
    recogniserRef.current.start((text, final) => {
      setTranscript(text);
      setIsFinal(final);
    });
  };

  const handleStop = () => {
    if (!recogniserRef.current) return;
    const finalMetrics = recogniserRef.current.stop();
    setMetrics(finalMetrics);
    setIsRecording(false);
    setDurationMs(finalMetrics.duration_ms);
  };

  const handleSubmit = () => {
    if (!transcript.trim()) return;
    onSubmit(transcript.trim(), metrics, durationMs);
    setTranscript("");
    setMetrics({ filler_count: 0, wpm: 0, hedging_count: 0, duration_ms: 0, pause_count: 0 });
  };

  if (!supported) {
    return (
      <div className="rounded-xl border border-amber-700 bg-amber-900/20 p-4 text-sm text-amber-300">
        Speech recognition is not supported in this browser. Please type your answer below.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        {!isRecording ? (
          <Button
            onClick={handleStart}
            disabled={disabled}
            className="gap-2 bg-indigo-600 hover:bg-indigo-500"
          >
            <Mic className="h-4 w-4" />
            Start Recording
          </Button>
        ) : (
          <Button
            onClick={handleStop}
            className="gap-2 bg-red-600 hover:bg-red-500"
          >
            <Square className="h-4 w-4" />
            Stop
          </Button>
        )}
        <AnswerTimer isRunning={isRecording} />
      </div>

      <LiveFeedback
        fillerCount={metrics.filler_count}
        wpm={metrics.wpm}
        hedgingCount={metrics.hedging_count}
        isRecording={isRecording}
      />

      <TranscriptDisplay transcript={transcript} isFinal={isFinal} />

      {!isRecording && transcript.trim() && (
        <Button
          onClick={handleSubmit}
          disabled={disabled}
          className="w-full bg-emerald-700 hover:bg-emerald-600"
        >
          Submit Answer
        </Button>
      )}
    </div>
  );
}
