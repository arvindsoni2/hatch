"use client";

import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AnswerTimer } from "./AnswerTimer";

interface AudioBlobRecorderProps {
  onSubmit: (blob: Blob, durationMs: number) => void;
  disabled?: boolean;
}

export function AudioBlobRecorder({ onSubmit, disabled }: AudioBlobRecorderProps) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [durationMs, setDurationMs] = useState(0);

  const handleStart = async () => {
    setError(null);
    setBlob(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const recorded = new Blob(chunksRef.current, { type: mimeType });
        const elapsed = Date.now() - startTimeRef.current;
        setBlob(recorded);
        setDurationMs(elapsed);
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorderRef.current = mr;
      startTimeRef.current = Date.now();
      mr.start(200);
      setIsRecording(true);
    } catch (err) {
      setError("Could not access microphone. Please check your browser permissions.");
    }
  };

  const handleStop = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  const handleSubmit = () => {
    if (blob) onSubmit(blob, durationMs);
    setBlob(null);
    setDurationMs(0);
  };

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-amber-700 bg-amber-900/20 p-3 text-sm text-amber-300">
          {error}
        </div>
      )}

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
          <Button onClick={handleStop} className="gap-2 bg-red-600 hover:bg-red-500">
            <Square className="h-4 w-4" />
            Stop
          </Button>
        )}
        <AnswerTimer isRunning={isRecording} />
      </div>

      {blob && !isRecording && (
        <div className="space-y-2">
          <p className="text-xs text-slate-400">
            Recording ready ({(blob.size / 1024).toFixed(0)} KB, {(durationMs / 1000).toFixed(1)} s)
          </p>
          <Button
            onClick={handleSubmit}
            disabled={disabled}
            className="w-full bg-emerald-700 hover:bg-emerald-600"
          >
            Submit for Analysis
          </Button>
        </div>
      )}
    </div>
  );
}
