/**
 * Web Speech API wrapper for real-time transcription with filler tracking.
 * The Web Speech API has no official @types package, so we use
 * safe window-key lookups and unknown → structured casts.
 */
import { SpeechMetrics } from "./api";

type SpeechRecognitionInstance = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: SpeechResultEvent) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechResultEvent = {
  resultIndex: number;
  results: { isFinal: boolean; 0: { transcript: string } }[];
};

const FILLERS = [
  "um", "uh", "er", "ah", "hmm",
  "basically", "literally", "actually", "honestly",
  "you know", "right", "like", "so",
  "kind of", "sort of",
];

const HEDGING = [
  "i think", "i believe", "i guess", "i suppose",
  "maybe", "perhaps", "probably", "possibly",
  "sort of", "kind of",
];

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionInstance) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  const ctor = w["SpeechRecognition"] ?? w["webkitSpeechRecognition"];
  return (ctor as (new () => SpeechRecognitionInstance) | undefined) ?? null;
}

export class SpeechRecogniser {
  private recognition: SpeechRecognitionInstance | null = null;
  private fullTranscript = "";
  private startTime = 0;
  private fillerCount = 0;
  private hedgingCount = 0;

  constructor() {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return;
    this.recognition = new Ctor();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = "en-GB";
  }

  get isSupported(): boolean {
    return this.recognition !== null;
  }

  start(onTranscript: (text: string, isFinal: boolean) => void): void {
    if (!this.recognition) return;
    this.fullTranscript = "";
    this.startTime = Date.now();
    this.fillerCount = 0;
    this.hedgingCount = 0;

    this.recognition.onresult = (event: SpeechResultEvent) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal) {
          this.fullTranscript += text + " ";
          this.fillerCount += this._countFillers(text);
          this.hedgingCount += this._countHedging(text);
          onTranscript(this.fullTranscript.trim(), true);
        } else {
          interim = text;
          onTranscript(this.fullTranscript + interim, false);
        }
      }
    };

    this.recognition.start();
  }

  stop(): SpeechMetrics {
    const durationMs = Date.now() - this.startTime;
    this.recognition?.stop();
    const words = this.fullTranscript.trim().split(/\s+/).filter(Boolean);
    const minutes = durationMs / 60_000 || 1;
    const wpm = words.length / minutes;
    return {
      filler_count: this.fillerCount,
      wpm: Math.round(wpm * 10) / 10,
      hedging_count: this.hedgingCount,
      duration_ms: durationMs,
      pause_count: 0,
    };
  }

  getTranscript(): string {
    return this.fullTranscript.trim();
  }

  private _countFillers(text: string): number {
    const lower = text.toLowerCase();
    return FILLERS.reduce((count, filler) => {
      const regex = new RegExp(`\\b${filler}\\b`, "gi");
      return count + (lower.match(regex)?.length ?? 0);
    }, 0);
  }

  private _countHedging(text: string): number {
    const lower = text.toLowerCase();
    return HEDGING.reduce((count, phrase) => {
      return count + (lower.includes(phrase) ? 1 : 0);
    }, 0);
  }
}
