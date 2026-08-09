"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type {
  ConversationCommandType,
  ConversationLiveView,
  ConversationState,
} from "@/lib/api";
import { uploadCoachAttemptAudio } from "@/lib/api";
import { SilencePrompt } from "./SilencePrompt";

const ANALYSER_INTERVAL_MS = 100;
const CALIBRATION_MS = 500;
const SPEECH_MARGIN_DB = 8;
const MINIMUM_SPEECH_MS = 1500;
const FIVE_MINUTES_MS = 5 * 60 * 1000;
const TEN_MINUTES_MS = 10 * 60 * 1000;

type CaptureStatus = "idle" | "starting" | "recording" | "paused" | "stopped" | "submitting" | "error";
type SilenceState = "none" | "warning" | "prompt";

function elapsedLabel(elapsedMs: number): string {
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function sampleDecibels(analyser: AnalyserNode, buffer: Float32Array<ArrayBuffer>): number {
  analyser.getFloatTimeDomainData(buffer);
  let sumSquares = 0;
  for (const sample of buffer) sumSquares += sample * sample;
  const rms = Math.sqrt(sumSquares / buffer.length);
  return rms === 0 ? -100 : 20 * Math.log10(rms);
}

async function sha256(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function currentRecorderState(recorder: MediaRecorder): RecordingState {
  return recorder.state;
}

function microphoneFailureMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone was found. Connect a microphone or answer in writing.";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "The microphone is unavailable or in use by another application. Close it there or answer in writing.";
  }
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access was not granted. Check this site's browser permissions or answer in writing.";
  }
  return "This browser could not start audio capture. Check browser microphone support or answer in writing.";
}

export interface ConversationRecorderProps {
  sessionId: string;
  attemptId: string | null;
  serverState: ConversationState;
  authorityAvailable: boolean;
  authorityVersion: number;
  allowedCommands: ConversationCommandType[];
  silencePolicy: ConversationLiveView["silence_policy"];
  pending: boolean;
  onBeginAudio: () => Promise<{ attemptId: string; stateVersion: number } | null>;
  onPause: () => Promise<RecorderTransitionOutcome>;
  onResume: () => Promise<RecorderTransitionOutcome>;
  onKeepSpeaking: (attemptId: string) => Promise<boolean>;
  onCancel: (attemptId: string) => Promise<RecorderCancelOutcome>;
  onDiscardAndRetry: (attemptId: string) => Promise<boolean>;
  onFinishCommand: (attemptId: string, uploadId: string) => Promise<boolean>;
  onAnnouncement: (message: string) => void;
}

export type RecorderTransitionOutcome = "accepted" | "accepted_refresh_unavailable" | "rejected";
export type RecorderCancelOutcome =
  | "cancelled"
  | "remain_paused"
  | "resumed_pending"
  | "authority_mismatch"
  | "rejected";

export function ConversationRecorder({
  sessionId,
  attemptId,
  serverState,
  authorityAvailable,
  authorityVersion,
  allowedCommands,
  pending,
  silencePolicy,
  onBeginAudio,
  onPause,
  onResume,
  onKeepSpeaking,
  onCancel,
  onDiscardAndRetry,
  onFinishCommand,
  onAnnouncement,
}: ConversationRecorderProps) {
  const [microphoneError, setMicrophoneError] = useState<string | null>(null);
  const [captureStatus, setCaptureStatus] = useState<CaptureStatus>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [silenceState, setSilenceState] = useState<SilenceState>("none");
  const [durationWarning, setDurationWarning] = useState(false);
  const [captureMessage, setCaptureMessage] = useState<string | null>(null);
  const [hasLocalCapture, setHasLocalCapture] = useState(false);
  const [retryLabel, setRetryLabel] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const elapsedMsRef = useRef(0);
  const activeSegmentStartedAtRef = useRef<number | null>(null);
  const hardStopTimerRef = useRef<number | null>(null);
  const renderedElapsedSecondRef = useRef(0);
  const calibrationElapsedRef = useRef(0);
  const calibrationSamplesRef = useRef<number[]>([]);
  const calibratedNoiseDbRef = useRef<number | null>(null);
  const consecutiveSpeechMsRef = useRef(0);
  const speechSeenRef = useRef(false);
  const silenceMsRef = useRef(0);
  const silenceStateRef = useRef<SilenceState>("none");
  const durationWarningShownRef = useRef(false);
  const unsentBlobRef = useRef<Blob | null>(null);
  const captureAttemptIdRef = useRef<string | null>(null);
  const captureAuthorityVersionRef = useRef<number | null>(null);
  const analyserTimerRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const stopPromiseRef = useRef<Promise<Blob | null> | null>(null);
  const preserveBlobOnStopRef = useRef(false);
  const captureGenerationRef = useRef(0);
  const authorityAvailableRef = useRef(authorityAvailable);
  const authorityEpochRef = useRef(0);
  const authorityTupleRef = useRef<string | null>(null);
  const freshMatchingOwnershipRef = useRef(false);
  const uploadRef = useRef<{ uploadId: string; contentSha256: string; completed: boolean } | null>(null);
  const submitInFlightRef = useRef<number | null>(null);
  const hardStopStartedRef = useRef(false);
  const mountedRef = useRef(true);
  const finishButtonRef = useRef<HTMLButtonElement | null>(null);
  const pauseButtonRef = useRef<HTMLButtonElement | null>(null);
  const resumeButtonRef = useRef<HTMLButtonElement | null>(null);
  const focusTargetRef = useRef<"finish" | "pause" | "resume" | null>(null);

  const authorityTuple = `${authorityAvailable ? "available" : "unavailable"}:${attemptId ?? "none"}:${serverState}:${authorityVersion}`;
  if (authorityTupleRef.current === null) authorityTupleRef.current = authorityTuple;
  else if (authorityTupleRef.current !== authorityTuple) {
    authorityTupleRef.current = authorityTuple;
    authorityEpochRef.current += 1;
  }
  authorityAvailableRef.current = authorityAvailable;
  freshMatchingOwnershipRef.current = authorityAvailable
    && (serverState === "listening" || serverState === "paused")
    && (captureAttemptIdRef.current === null || captureAttemptIdRef.current === attemptId);

  const releaseBrowserResources = useCallback(() => {
    if (analyserTimerRef.current !== null) {
      window.clearInterval(analyserTimerRef.current);
      analyserTimerRef.current = null;
    }
    if (hardStopTimerRef.current !== null) {
      window.clearTimeout(hardStopTimerRef.current);
      hardStopTimerRef.current = null;
    }
    activeSegmentStartedAtRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    analyserRef.current?.disconnect();
    analyserRef.current = null;
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext !== null && audioContext.state !== "closed") void audioContext.close();
    for (const track of streamRef.current?.getTracks() ?? []) track.stop();
    streamRef.current = null;
  }, []);

  const clearLocalCapture = useCallback(() => {
    captureGenerationRef.current += 1;
    chunksRef.current = [];
    unsentBlobRef.current = null;
    captureAttemptIdRef.current = null;
    captureAuthorityVersionRef.current = null;
    uploadRef.current = null;
    stopPromiseRef.current = null;
    hardStopStartedRef.current = false;
    elapsedMsRef.current = 0;
    renderedElapsedSecondRef.current = 0;
    if (mountedRef.current) {
      setHasLocalCapture(false);
      setCaptureStatus("idle");
      setSilenceState("none");
      silenceStateRef.current = "none";
      setDurationWarning(false);
      durationWarningShownRef.current = false;
      setElapsedMs(0);
      setRetryLabel(false);
      setCaptureMessage(null);
    }
  }, []);

  const stopRecorder = useCallback((preserveBlob: boolean): Promise<Blob | null> => {
    if (stopPromiseRef.current !== null) {
      if (!preserveBlob) preserveBlobOnStopRef.current = false;
      return stopPromiseRef.current;
    }
    preserveBlobOnStopRef.current = preserveBlob;
    if (activeSegmentStartedAtRef.current !== null) {
      elapsedMsRef.current += Math.max(0, performance.now() - activeSegmentStartedAtRef.current);
      activeSegmentStartedAtRef.current = null;
    }
    if (hardStopTimerRef.current !== null) {
      window.clearTimeout(hardStopTimerRef.current);
      hardStopTimerRef.current = null;
    }
    const recorder = recorderRef.current;
    stopPromiseRef.current = new Promise<Blob | null>((resolve) => {
      const finish = () => {
        const type = recorder?.mimeType || chunksRef.current[0]?.type || "audio/webm";
        const blob = chunksRef.current.length > 0 ? new Blob(chunksRef.current, { type }) : null;
        recorderRef.current = null;
        releaseBrowserResources();
        if (preserveBlobOnStopRef.current && blob !== null) {
          unsentBlobRef.current = blob;
          if (mountedRef.current) {
            setHasLocalCapture(true);
            setCaptureStatus("stopped");
          }
        } else {
          clearLocalCapture();
        }
        resolve(blob);
      };
      if (recorder === null || recorder.state === "inactive") {
        finish();
        return;
      }
      recorder.onstop = finish;
      try {
        recorder.stop();
      } catch {
        finish();
      }
    });
    return stopPromiseRef.current;
  }, [clearLocalCapture, releaseBrowserResources]);

  const stopAtLimit = useCallback(async () => {
    if (hardStopStartedRef.current) return;
    hardStopStartedRef.current = true;
    await stopRecorder(true);
    if (!mountedRef.current) return;
    setCaptureMessage("Recording stopped at the ten-minute limit. Submit or discard the captured answer.");
    onAnnouncement("Recording stopped at the ten-minute limit. Submit or discard the captured answer.");
  }, [onAnnouncement, stopRecorder]);

  const currentActiveElapsed = useCallback(() => elapsedMsRef.current + (
    activeSegmentStartedAtRef.current === null
      ? 0
      : Math.max(0, performance.now() - activeSegmentStartedAtRef.current)
  ), []);

  const checkDurationBoundaries = useCallback(() => {
    const activeElapsed = currentActiveElapsed();
    const elapsedSecond = Math.floor(activeElapsed / 1000);
    if (elapsedSecond !== renderedElapsedSecondRef.current) {
      renderedElapsedSecondRef.current = elapsedSecond;
      setElapsedMs(activeElapsed);
    }
    if (activeElapsed >= FIVE_MINUTES_MS && !durationWarningShownRef.current) {
      durationWarningShownRef.current = true;
      setDurationWarning(true);
      onAnnouncement("This recording has reached five minutes. Take the time you need or finish when ready.");
    }
    if (activeElapsed >= TEN_MINUTES_MS) void stopAtLimit();
    return activeElapsed;
  }, [currentActiveElapsed, onAnnouncement, stopAtLimit]);

  const scheduleHardStop = useCallback(() => {
    if (hardStopTimerRef.current !== null) window.clearTimeout(hardStopTimerRef.current);
    const remaining = Math.max(0, TEN_MINUTES_MS - currentActiveElapsed());
    hardStopTimerRef.current = window.setTimeout(() => {
      hardStopTimerRef.current = null;
      checkDurationBoundaries();
    }, remaining);
  }, [checkDurationBoundaries, currentActiveElapsed]);

  const startAnalyser = useCallback((stream: MediaStream) => {
    const AudioContextConstructor = window.AudioContext;
    const audioContext = new AudioContextConstructor();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    audioContextRef.current = audioContext;
    sourceRef.current = source;
    analyserRef.current = analyser;
    const sampleBuffer = new Float32Array(analyser.fftSize);

    analyserTimerRef.current = window.setInterval(() => {
      const recorder = recorderRef.current;
      if (recorder?.state !== "recording") return;

      if (checkDurationBoundaries() >= TEN_MINUTES_MS) return;

      const db = sampleDecibels(analyser, sampleBuffer);
      if (calibratedNoiseDbRef.current === null) {
        calibrationSamplesRef.current.push(db);
        calibrationElapsedRef.current += ANALYSER_INTERVAL_MS;
        if (calibrationElapsedRef.current >= CALIBRATION_MS) {
          calibratedNoiseDbRef.current = calibrationSamplesRef.current.reduce((sum, value) => sum + value, 0)
            / calibrationSamplesRef.current.length;
        }
        return;
      }

      if (db >= calibratedNoiseDbRef.current + SPEECH_MARGIN_DB) {
        consecutiveSpeechMsRef.current += ANALYSER_INTERVAL_MS;
        silenceMsRef.current = 0;
        if (consecutiveSpeechMsRef.current >= MINIMUM_SPEECH_MS) speechSeenRef.current = true;
        if (silenceStateRef.current !== "none") {
          silenceStateRef.current = "none";
          setSilenceState("none");
        }
        return;
      }

      if (!speechSeenRef.current) {
        consecutiveSpeechMsRef.current = 0;
        return;
      }

      consecutiveSpeechMsRef.current = 0;
      silenceMsRef.current += ANALYSER_INTERVAL_MS;
      if (silenceMsRef.current >= silencePolicy.finish_prompt_ms) {
        if (silenceStateRef.current !== "prompt") {
          silenceStateRef.current = "prompt";
          setSilenceState("prompt");
          onAnnouncement("Are you finished? Choose Finish answer or Keep speaking.");
        }
      } else if (silenceMsRef.current >= silencePolicy.warning_ms) {
        if (silenceStateRef.current !== "warning") {
          silenceStateRef.current = "warning";
          setSilenceState("warning");
          onAnnouncement("You have been quiet for a few seconds. Recording continues.");
        }
      }
    }, ANALYSER_INTERVAL_MS);
  }, [checkDurationBoundaries, onAnnouncement, silencePolicy.finish_prompt_ms, silencePolicy.warning_ms]);

  const startAudio = async () => {
    if (captureStatus !== "idle") return;
    setCaptureStatus("starting");
    setMicrophoneError(null);
    setCaptureMessage(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const acceptedAttempt = await onBeginAudio();
      if (acceptedAttempt === null) {
        releaseBrowserResources();
        if (mountedRef.current) setCaptureStatus("idle");
        return;
      }
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      captureAttemptIdRef.current = acceptedAttempt.attemptId;
      captureAuthorityVersionRef.current = acceptedAttempt.stateVersion;
      captureGenerationRef.current += 1;
      chunksRef.current = [];
      elapsedMsRef.current = 0;
      renderedElapsedSecondRef.current = 0;
      calibrationElapsedRef.current = 0;
      calibrationSamplesRef.current = [];
      calibratedNoiseDbRef.current = null;
      consecutiveSpeechMsRef.current = 0;
      speechSeenRef.current = false;
      silenceMsRef.current = 0;
      silenceStateRef.current = "none";
      durationWarningShownRef.current = false;
      hardStopStartedRef.current = false;
      uploadRef.current = null;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        if (mountedRef.current) {
          setCaptureStatus("error");
          setCaptureMessage("Audio capture stopped because the browser reported an error. Discard and try again, or upload the captured audio if available.");
          onAnnouncement("Audio capture stopped because the browser reported an error.");
        }
        void stopRecorder(true);
      };
      recorder.start();
      activeSegmentStartedAtRef.current = performance.now();
      scheduleHardStop();
      startAnalyser(stream);
      setHasLocalCapture(true);
      setCaptureStatus("recording");
      onAnnouncement("Audio recording started");
    } catch (error) {
      if (recorderRef.current !== null) await stopRecorder(false);
      else releaseBrowserResources();
      if (mountedRef.current) {
        const message = microphoneFailureMessage(error);
        setMicrophoneError(message);
        setCaptureStatus("idle");
        onAnnouncement(message);
      }
    }
  };

  const submitCaptured = async () => {
    if (submitInFlightRef.current !== null) return;
    const captureGeneration = captureGenerationRef.current;
    const authorityEpoch = authorityEpochRef.current;
    submitInFlightRef.current = captureGeneration;
    setCaptureStatus("submitting");
    setCaptureMessage(null);
    const superseded = () => captureGeneration !== captureGenerationRef.current;
    const authorityChanged = () => authorityEpoch !== authorityEpochRef.current;
    const mismatched = () => authorityAvailableRef.current && !freshMatchingOwnershipRef.current;
    const pauseForUnavailableAuthority = () => {
      if (authorityAvailableRef.current) return false;
      if (mountedRef.current) setCaptureStatus("stopped");
      return true;
    };
    const pauseForChangedAuthority = () => {
      if (!authorityChanged()) return false;
      if (mountedRef.current) setCaptureStatus("stopped");
      return true;
    };
    try {
      const blob = unsentBlobRef.current ?? await stopRecorder(true);
      if (superseded() || mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
      const ownedAttemptId = captureAttemptIdRef.current ?? attemptId;
      if (blob === null || ownedAttemptId === null) {
        setCaptureStatus("error");
        setCaptureMessage("No captured audio is available to upload. Discard this draft and try again.");
        return;
      }
      let upload = uploadRef.current;
      if (upload === null) {
        upload = {
          uploadId: crypto.randomUUID(),
          contentSha256: await sha256(blob),
          completed: false,
        };
        if (superseded() || mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
        uploadRef.current = upload;
      }
      if (!upload.completed) {
        if (mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
        await uploadCoachAttemptAudio(sessionId, ownedAttemptId, {
          uploadId: upload.uploadId,
          contentSha256: upload.contentSha256,
          audio: blob,
        });
        if (superseded() || mismatched()) return;
        uploadRef.current = { ...upload, completed: true };
        upload = uploadRef.current;
        if (pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
      }
      if (mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
      const accepted = await onFinishCommand(ownedAttemptId, upload.uploadId);
      if (superseded() || mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
      if (accepted) {
        onAnnouncement("Audio answer submitted for processing");
        clearLocalCapture();
      } else {
        setCaptureStatus("stopped");
        setRetryLabel(true);
        setCaptureMessage("Your captured answer is still available. The server did not accept the finish command.");
      }
    } catch {
      if (superseded() || mismatched() || pauseForChangedAuthority() || pauseForUnavailableAuthority()) return;
      setCaptureStatus("stopped");
      setRetryLabel(true);
      setCaptureMessage("Your captured answer is still available. Upload it again when you are ready.");
      onAnnouncement("Your captured answer is still available after the upload error.");
    } finally {
      if (submitInFlightRef.current === captureGeneration) submitInFlightRef.current = null;
    }
  };

  const pauseRecording = async () => {
    const recorder = recorderRef.current;
    if (recorder?.state !== "recording") return;
    try {
      recorder.pause();
      if (activeSegmentStartedAtRef.current !== null) {
        elapsedMsRef.current += Math.max(0, performance.now() - activeSegmentStartedAtRef.current);
        activeSegmentStartedAtRef.current = null;
      }
      if (hardStopTimerRef.current !== null) {
        window.clearTimeout(hardStopTimerRef.current);
        hardStopTimerRef.current = null;
      }
      focusTargetRef.current = "resume";
      setCaptureStatus("paused");
      const outcome = await onPause();
      if (outcome === "rejected") {
        if (currentRecorderState(recorder) === "paused") recorder.resume();
        activeSegmentStartedAtRef.current = performance.now();
        scheduleHardStop();
        focusTargetRef.current = "pause";
        setCaptureStatus("recording");
        setCaptureMessage("The interview was not paused. Audio recording is continuing.");
      } else {
        onAnnouncement(outcome === "accepted_refresh_unavailable"
          ? "Audio recording paused. We could not refresh the interview state."
          : "Audio recording paused");
      }
    } catch {
      setCaptureMessage("The browser could not pause this recording.");
    }
  };

  const resumeRecording = async () => {
    const recorder = recorderRef.current;
    if (recorder?.state !== "paused") return;
    try {
      recorder.resume();
      activeSegmentStartedAtRef.current = performance.now();
      scheduleHardStop();
      focusTargetRef.current = "pause";
      setCaptureStatus("recording");
      const outcome = await onResume();
      if (outcome === "rejected") {
        if (currentRecorderState(recorder) === "recording") recorder.pause();
        if (activeSegmentStartedAtRef.current !== null) {
          elapsedMsRef.current += Math.max(0, performance.now() - activeSegmentStartedAtRef.current);
          activeSegmentStartedAtRef.current = null;
        }
        if (hardStopTimerRef.current !== null) {
          window.clearTimeout(hardStopTimerRef.current);
          hardStopTimerRef.current = null;
        }
        focusTargetRef.current = "resume";
        setCaptureStatus("paused");
        setCaptureMessage("The interview remains paused. The local recording was paused again.");
      } else {
        onAnnouncement(outcome === "accepted_refresh_unavailable"
          ? "Audio recording resumed. We could not refresh the interview state."
          : "Audio recording resumed");
      }
    } catch {
      setCaptureMessage("The browser could not resume this recording.");
    }
  };

  const keepSpeaking = async () => {
    const ownedAttemptId = captureAttemptIdRef.current ?? attemptId;
    if (ownedAttemptId === null || !await onKeepSpeaking(ownedAttemptId)) return;
    silenceMsRef.current = 0;
    consecutiveSpeechMsRef.current = 0;
    silenceStateRef.current = "none";
    focusTargetRef.current = "finish";
    setSilenceState("none");
    setCaptureMessage(null);
    onAnnouncement("Keep speaking. Audio recording continues.");
  };

  const stopWhileAuthorityUnavailable = async () => {
    const captureGeneration = captureGenerationRef.current;
    const blob = await stopRecorder(true);
    if (captureGeneration !== captureGenerationRef.current) return;
    if (blob === null) {
      setCaptureStatus("error");
      setCaptureMessage("No captured audio is available. Refresh the interview and try recording again.");
      return;
    }
    setCaptureMessage(null);
    onAnnouncement("Recording stopped. Your captured audio is preserved until interview status is available.");
  };

  const cancelRecording = async () => {
    const ownedAttemptId = captureAttemptIdRef.current ?? attemptId;
    if (ownedAttemptId === null) return;
    const captureGeneration = captureGenerationRef.current;
    const outcome = await onCancel(ownedAttemptId);
    if (captureGeneration !== captureGenerationRef.current) return;
    if (outcome === "remain_paused") {
      setCaptureStatus("paused");
      setCaptureMessage("The interview remains paused. Cancel was not completed.");
      onAnnouncement("The interview remains paused. Cancel was not completed.");
      return;
    }
    if (outcome === "resumed_pending") {
      let recorder = recorderRef.current;
      if (recorder !== null && currentRecorderState(recorder) === "paused") {
        recorder.resume();
        activeSegmentStartedAtRef.current = performance.now();
        scheduleHardStop();
      }
      if (recorder !== null && currentRecorderState(recorder) === "recording") {
        setCaptureStatus("recording");
        setCaptureMessage("The interview resumed, but cancel is pending. Stop locally to preserve this recording.");
        onAnnouncement("The interview resumed, but cancel is pending. Recording continues locally.");
        return;
      }
      if (stopPromiseRef.current !== null) await stopPromiseRef.current;
      if (captureGeneration !== captureGenerationRef.current) return;
      recorder = recorderRef.current;
      if (recorder !== null && currentRecorderState(recorder) === "recording") return;
      if (unsentBlobRef.current !== null) {
        setCaptureStatus("stopped");
        setCaptureMessage("The interview resumed, but cancel is pending. Your stopped audio is preserved locally.");
        onAnnouncement("Cancel is pending. Your stopped audio is preserved locally.");
        return;
      }
      setCaptureStatus("error");
      setCaptureMessage("The interview resumed, but cancel is pending. No local recording is available.");
      onAnnouncement("Cancel is pending, but no local recording is available.");
      return;
    }
    if (outcome === "authority_mismatch") {
      await stopRecorder(false);
      return;
    }
    if (outcome !== "cancelled") return;
    await stopRecorder(false);
  };

  const discardAndRetry = async () => {
    const ownedAttemptId = captureAttemptIdRef.current ?? attemptId;
    if (ownedAttemptId === null || !await onDiscardAndRetry(ownedAttemptId)) return;
    await stopRecorder(false);
    clearLocalCapture();
    setCaptureMessage(null);
    onAnnouncement("Audio draft discarded. You can start again.");
  };

  useEffect(() => {
    if (!authorityAvailable || !hasLocalCapture) return;
    const captureVersion = captureAuthorityVersionRef.current;
    if (captureVersion !== null && authorityVersion < captureVersion) return;
    const ownsCapture = captureAttemptIdRef.current !== null
      && captureAttemptIdRef.current === attemptId
      && (serverState === "listening" || serverState === "paused");
    if (ownsCapture) return;
    captureGenerationRef.current += 1;
    preserveBlobOnStopRef.current = false;
    if (recorderRef.current === null) clearLocalCapture();
    else void stopRecorder(false);
  }, [
    attemptId,
    authorityAvailable,
    authorityVersion,
    clearLocalCapture,
    hasLocalCapture,
    serverState,
    stopRecorder,
  ]);

  useEffect(() => {
    if (!hasLocalCapture) return;
    const recheckDuration = () => {
      if (recorderRef.current?.state === "recording") checkDurationBoundaries();
    };
    window.addEventListener("focus", recheckDuration);
    document.addEventListener("visibilitychange", recheckDuration);
    return () => {
      window.removeEventListener("focus", recheckDuration);
      document.removeEventListener("visibilitychange", recheckDuration);
    };
  }, [checkDurationBoundaries, hasLocalCapture]);

  useEffect(() => {
    const target = focusTargetRef.current;
    if (target === null) return;
    const element = target === "finish"
      ? finishButtonRef.current
      : target === "pause"
        ? pauseButtonRef.current
        : resumeButtonRef.current;
    if (element === null) return;
    element.focus();
    focusTargetRef.current = null;
  }, [allowedCommands, captureStatus, silenceState]);

  useEffect(() => {
    const shouldWarn = hasLocalCapture && ["asking", "listening", "paused"].includes(serverState);
    if (!shouldWarn) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [hasLocalCapture, serverState]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const recorder = recorderRef.current;
      if (recorder !== null && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          // Resource release below remains authoritative during teardown.
        }
      }
      recorderRef.current = null;
      releaseBrowserResources();
    };
  }, [releaseBrowserResources]);

  const hasLiveRecorder = recorderRef.current !== null;
  const freshMatchingOwnership = freshMatchingOwnershipRef.current;
  const isServerAudioDraft = attemptId !== null && (serverState === "listening" || serverState === "paused");
  const hasStoppedCapture = !hasLiveRecorder && unsentBlobRef.current !== null;
  const needsRecovery = (isServerAudioDraft || hasStoppedCapture) && !hasLiveRecorder;

  return (
    <div className="space-y-3">
      {authorityAvailable && allowedCommands.includes("begin_answer") && captureStatus === "idle" ? (
        <Button type="button" variant="outline" onClick={() => void startAudio()} disabled={pending}>
          Start audio answer
        </Button>
      ) : null}
      {microphoneError ? (
        <p className="text-sm text-[var(--text-muted)]">
          {microphoneError}
        </p>
      ) : null}

      {hasLiveRecorder ? (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3">
          <p className="text-sm font-semibold text-[var(--text)]">
            {captureStatus === "paused" ? "Microphone paused" : "Microphone recording"}
          </p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Elapsed recording time {elapsedLabel(elapsedMs)}</p>
          <p className="text-sm text-[var(--text-muted)]">
            Capture health: {captureStatus === "paused" ? "paused safely" : "audio is being captured"}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {freshMatchingOwnership && captureStatus === "recording" && silenceState !== "prompt" && allowedCommands.includes("finish_answer") ? (
              <Button ref={finishButtonRef} type="button" onClick={() => void submitCaptured()} disabled={pending}>
                Finish audio answer while recording
              </Button>
            ) : null}
            {freshMatchingOwnership && captureStatus === "recording" && allowedCommands.includes("pause") ? (
              <Button ref={pauseButtonRef} type="button" variant="outline" onClick={() => void pauseRecording()} disabled={pending}>
                Pause audio recording
              </Button>
            ) : null}
            {freshMatchingOwnership && captureStatus === "paused" && allowedCommands.includes("resume") ? (
              <Button ref={resumeButtonRef} type="button" variant="outline" onClick={() => void resumeRecording()} disabled={pending}>
                Resume paused audio recording
              </Button>
            ) : null}
            {freshMatchingOwnership && (serverState === "listening" || serverState === "paused") ? (
              <Button type="button" variant="outline" onClick={() => void cancelRecording()} disabled={pending}>
                Cancel audio answer and discard recording
              </Button>
            ) : null}
            {!authorityAvailable ? (
              <Button type="button" variant="outline" onClick={() => void stopWhileAuthorityUnavailable()}>
                Stop recording and preserve captured audio
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {silenceState === "warning" ? (
        <p className="text-sm text-[var(--text-muted)]">You have been quiet for a few seconds. Recording continues.</p>
      ) : null}
      {freshMatchingOwnership && silenceState === "prompt" ? (
        <SilencePrompt
          pending={pending || captureStatus === "submitting"}
          onFinish={() => void submitCaptured()}
          onKeepSpeaking={() => void keepSpeaking()}
        />
      ) : null}
      {durationWarning ? (
        <p className="text-sm text-[var(--text-muted)]">This recording has reached five minutes. Take the time you need or finish when ready.</p>
      ) : null}
      {captureMessage ? <p className="text-sm text-[var(--text-muted)]">{captureMessage}</p> : null}

      {needsRecovery ? (
        <section className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3">
          <p className="text-sm text-[var(--text)]">
            {authorityAvailable
              ? `This browser no longer has the live recording. The interview remains ${serverState} on the server.`
              : "Your captured audio is preserved locally while interview status is unavailable."}
          </p>
          {freshMatchingOwnership ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {unsentBlobRef.current !== null ? (
                <Button type="button" onClick={() => void submitCaptured()} disabled={pending || captureStatus === "submitting"}>
                  {retryLabel ? "Upload captured answer again" : "Upload captured answer"}
                </Button>
              ) : null}
              <Button type="button" variant="outline" onClick={() => void discardAndRetry()} disabled={pending}>
                Discard recording and try again
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
