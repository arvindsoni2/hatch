"use client";

import { useEffect, useState } from "react";

interface AnswerTimerProps {
  isRunning: boolean;
  onElapsed?: (ms: number) => void;
}

const AMBER_THRESHOLD = 90; // seconds
const RED_THRESHOLD = 150; // seconds

export function AnswerTimer({ isRunning, onElapsed }: AnswerTimerProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!isRunning) {
      onElapsed?.(elapsed * 1000);
      return;
    }
    setElapsed(0);
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const formatted = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;

  const colorClass =
    elapsed >= RED_THRESHOLD
      ? "text-red-400"
      : elapsed >= AMBER_THRESHOLD
        ? "text-amber-400"
        : "text-emerald-400";

  return (
    <div className={`font-mono text-2xl font-bold tabular-nums ${colorClass}`}>
      {formatted}
    </div>
  );
}
