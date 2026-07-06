"use client";

import { Button } from "@/components/ui/button";
import { Camera, EyeOff, Shield } from "lucide-react";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ConsentGateProps {
  onAccept: () => void;
  onDecline: () => void;
}

/**
 * ConsentGate explains face analysis and asks for explicit user consent.
 *
 * What it collects: facial blendshapes + head pose angles (numeric summaries only).
 * What is NOT sent to the server: raw video frames, JPEG/PNG images, video stream.
 */
export function ConsentGate({ onAccept, onDecline }: ConsentGateProps) {
  return (
    <Dialog open>
      <DialogContent className="max-w-md" hideClose preventClose>
        {/* Header */}
        <DialogHeader className="flex items-center gap-3 pr-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-900">
            <Camera aria-hidden="true" className="h-5 w-5 text-indigo-300" />
          </div>
          <div>
            <DialogTitle>Enable Face Analysis?</DialogTitle>
            <DialogDescription>
              Choose whether Hatch may analyse webcam landmarks locally during practice.
            </DialogDescription>
          </div>
        </DialogHeader>

        {/* What it does */}
        <DialogBody>
          <p className="mb-4 text-sm text-slate-300">
            When enabled, your webcam feed is analysed locally in your browser using{" "}
            <span className="font-medium text-slate-100">MediaPipe Face Landmarker</span>. The
            analysis measures:
          </p>
          <ul className="mb-4 list-disc space-y-1 pl-5 text-sm text-slate-300">
          <li className="flex items-center gap-2">
            Eye contact percentage, showing how often you look at the camera
          </li>
          <li className="flex items-center gap-2">
            Head stability during your answer
          </li>
          <li className="flex items-center gap-2">
            Engagement trend across your answer
          </li>
          </ul>

          {/* What is NOT sent */}
          <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/30 p-3">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-emerald-400">
              <Shield aria-hidden="true" className="h-3.5 w-3.5" />
              Privacy guarantee
            </div>
            <div className="flex items-start gap-2 text-sm text-emerald-200">
              <EyeOff aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <span>
                Raw video, individual frames, and images are{" "}
                <span className="font-semibold">never sent to the server</span>. Only numeric
                summaries, such as eye contact percentage, are uploaded.
              </span>
            </div>
          </div>
        </DialogBody>

        {/* Actions */}
        <DialogFooter className="grid grid-cols-2">
          <Button
            onClick={onDecline}
            variant="outline"
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            Cancel
          </Button>
          <Button
            onClick={onAccept}
            className="bg-indigo-600 text-white hover:bg-indigo-500"
          >
            Enable Face Analysis
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
