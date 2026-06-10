"use client";

import { useEffect, useRef, useCallback } from "react";

export interface FaceSummary {
  eye_contact_pct: number;       // fraction 0.0-1.0 of frames where both eyes are roughly forward
  avg_arousal: number;           // proxy from brow/eye blendshapes
  head_stability: number;        // stddev of head euler angles (lower = more stable)
  engagement_trend: "rising" | "steady" | "falling";  // first vs last half comparison
}

interface FaceCaptureProps {
  active: boolean;
  onSummaryReady: (summary: FaceSummary) => void;
}

interface BlendshapeFrame {
  eyeContactScore: number;      // 0-1 per frame
  browRaise: number;            // brow_inner_up blendshape
  headYaw: number;              // head euler angle Y
  headPitch: number;            // head euler angle X
}

const MEDIAPIPE_CDN =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0";
const WASM_BASE = `${MEDIAPIPE_CDN}/wasm/`;
const FRAME_INTERVAL_MS = 500;  // ~2fps

function stddev(values: number[]): number {
  if (values.length === 0) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function computeSummary(frames: BlendshapeFrame[]): FaceSummary {
  if (frames.length === 0) {
    return {
      eye_contact_pct: 0,
      avg_arousal: 0,
      head_stability: 1,
      engagement_trend: "steady",
    };
  }

  const eye_contact_pct =
    frames.reduce((sum, f) => sum + f.eyeContactScore, 0) / frames.length;

  const avg_arousal =
    frames.reduce((sum, f) => sum + f.browRaise, 0) / frames.length;

  const yawStd = stddev(frames.map((f) => f.headYaw));
  const pitchStd = stddev(frames.map((f) => f.headPitch));
  const head_stability = (yawStd + pitchStd) / 2;

  // Compare first and last halves for engagement trend
  const mid = Math.floor(frames.length / 2);
  const firstHalf = frames.slice(0, mid);
  const secondHalf = frames.slice(mid);

  const firstAvg = firstHalf.length
    ? firstHalf.reduce((s, f) => s + f.eyeContactScore + f.browRaise, 0) / (2 * firstHalf.length)
    : 0;
  const secondAvg = secondHalf.length
    ? secondHalf.reduce((s, f) => s + f.eyeContactScore + f.browRaise, 0) / (2 * secondHalf.length)
    : 0;

  let engagement_trend: "rising" | "steady" | "falling" = "steady";
  if (secondAvg - firstAvg > 0.05) engagement_trend = "rising";
  else if (firstAvg - secondAvg > 0.05) engagement_trend = "falling";

  return { eye_contact_pct, avg_arousal, head_stability, engagement_trend };
}

/**
 * FaceCapture — runs MediaPipe Face Landmarker at ~2fps during recording.
 *
 * Renders a 160×90 webcam preview with a LIVE indicator.
 * When `active` transitions from true → false, calls onSummaryReady with aggregated data.
 * MediaPipe is loaded from CDN to keep the bundle size lean.
 */
export function FaceCapture({ active, onSummaryReady }: FaceCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const framesRef = useRef<BlendshapeFrame[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const landmarkerRef = useRef<unknown>(null);
  const activeRef = useRef(active);
  activeRef.current = active;

  const stopStream = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  // Initialise MediaPipe + webcam
  useEffect(() => {
    if (!active) return;

    let cancelled = false;

    async function init() {
      try {
        // Dynamic import of @mediapipe/tasks-vision from CDN.
        // Uses a script-tag approach to avoid bundler interception.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let mpModule: any;
        // Check if already loaded (e.g. via script tag)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if ((window as any).__mediapipe_tasks_vision) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          mpModule = (window as any).__mediapipe_tasks_vision;
        } else {
          // Dynamic import from CDN — ignored by bundler at build time
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          mpModule = await (Function('url', 'return import(url)') as any)(`${MEDIAPIPE_CDN}/vision_bundle.mjs`);
        }

        if (cancelled) return;

        const { FaceLandmarker, FilesetResolver } = mpModule;

        const filesetResolver = await FilesetResolver.forVisionTasks(WASM_BASE);
        const faceLandmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
          baseOptions: {
            modelAssetPath: `${MEDIAPIPE_CDN}/models/face_landmarker.task`,
          },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: true,
          outputFacialTransformationMatrixes: true,
        });

        if (cancelled) {
          faceLandmarker.close();
          return;
        }

        landmarkerRef.current = faceLandmarker;
        framesRef.current = [];

        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }

        // Capture frames at ~2fps
        intervalRef.current = setInterval(() => {
          if (!activeRef.current) return;
          const video = videoRef.current;
          if (!video || video.readyState < 2) return;

          try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const result = (faceLandmarker as any).detectForVideo(video, performance.now());
            if (result?.faceBlendshapes?.length) {
              const blendshapes: Array<{ categoryName: string; score: number }> =
                result.faceBlendshapes[0].categories ?? [];
              const get = (name: string) =>
                blendshapes.find((b) => b.categoryName === name)?.score ?? 0;

              // Eye contact: both eyes visible (high "eyeBlinkLeft/Right" means eyes open)
              const leftOpen = 1 - get("eyeBlinkLeft");
              const rightOpen = 1 - get("eyeBlinkRight");
              const eyeContactScore = (leftOpen + rightOpen) / 2;

              // Brow raise as arousal proxy
              const browRaise = (get("browInnerUp") + get("browOuterUpLeft") + get("browOuterUpRight")) / 3;

              // Head euler angles from transformation matrix
              let headYaw = 0;
              let headPitch = 0;
              if (result?.facialTransformationMatrixes?.length) {
                const mat = result.facialTransformationMatrixes[0].data;
                // Extract Y and X euler from rotation matrix (approximate)
                headYaw = Math.atan2(mat[8], mat[0]) * (180 / Math.PI);
                headPitch = Math.atan2(-mat[9], Math.sqrt(mat[1] ** 2 + mat[5] ** 2)) * (180 / Math.PI);
              }

              framesRef.current.push({ eyeContactScore, browRaise, headYaw, headPitch });
            }
          } catch {
            // Silently skip frame on error
          }
        }, FRAME_INTERVAL_MS);
      } catch (err) {
        if (!cancelled) {
          console.warn("FaceCapture: failed to initialise MediaPipe", err);
        }
      }
    }

    void init();

    return () => {
      cancelled = true;
    };
  }, [active]);

  // When active transitions false → true, fire the summary
  useEffect(() => {
    if (!active) {
      const frames = framesRef.current;
      if (frames.length > 0) {
        const summary = computeSummary(frames);
        onSummaryReady(summary);
        framesRef.current = [];
      }
      stopStream();
    }
  }, [active, onSummaryReady, stopStream]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  if (!active) return null;

  return (
    <div className="relative inline-block overflow-hidden rounded-lg border border-slate-600">
      {/* Webcam preview */}
      <video
        ref={videoRef}
        muted
        playsInline
        className="h-[90px] w-[160px] object-cover"
        aria-label="Webcam preview for face analysis"
      />
      {/* LIVE indicator */}
      <div className="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 text-xs font-semibold text-red-400">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
        LIVE
      </div>
    </div>
  );
}
