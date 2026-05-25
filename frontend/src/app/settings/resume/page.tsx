"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
import {
  ArrowLeft, Upload, CheckCircle2, AlertCircle, FileText,
  Loader2, RefreshCw, ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchResumeStatus, uploadResume, type ResumeStatus } from "@/lib/api";

function SectionRow({ label, present }: { label: string; present: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      {present ? (
        <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
      ) : (
        <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
      )}
      <span className="text-sm text-slate-700">{label}</span>
    </div>
  );
}

export default function ResumePage() {
  const [status, setStatus] = useState<ResumeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const s = await fetchResumeStatus();
      setStatus(s);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith(".docx") && !file.name.endsWith(".pdf")) {
      setUploadError("Only .docx and .pdf files are supported.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadResume(file);
      setStatus(result);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const SECTION_LABELS: Record<string, string> = {
    personal: "Contact information",
    summary: "Professional summary",
    experience: "Work experience",
    skills: "Skills",
    education: "Education",
    certifications: "Certifications",
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Nav */}
      <Link
        href="/settings"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-4 w-4" /> Settings
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Master CV</h1>
      <p className="text-sm text-slate-500">
        Upload your CV once. JobPilot uses it to generate tailored applications for each job.
        Supported formats: <strong>.docx</strong> and <strong>.pdf</strong>.
      </p>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors cursor-pointer ${
          dragOver
            ? "border-brand-400 bg-brand-50"
            : "border-slate-200 bg-white hover:border-brand-300 hover:bg-slate-50"
        }`}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".docx,.pdf"
          className="hidden"
          onChange={onInputChange}
        />
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50">
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
          ) : (
            <Upload className="h-6 w-6 text-brand-600" />
          )}
        </div>
        {uploading ? (
          <p className="text-sm font-medium text-slate-700">Uploading and parsing…</p>
        ) : (
          <>
            <p className="text-sm font-medium text-slate-700">
              Drag &amp; drop your CV here, or click to browse
            </p>
            <p className="mt-1 text-xs text-slate-400">.docx or .pdf · max 10MB</p>
          </>
        )}
      </div>

      {uploadError && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {uploadError}
        </div>
      )}

      {/* Current CV status */}
      {status && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-slate-400" />
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {status.filename ?? "master_cv.json"}
                </p>
                {status.uploaded_at && (
                  <p className="text-xs text-slate-400">
                    Last updated {new Date(status.uploaded_at).toLocaleDateString("en-GB", {
                      day: "numeric", month: "long", year: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>

          {status.parsed && (
            <div className="px-5 py-4 space-y-4">
              {/* Parsed sections */}
              <div>
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  Parsed sections
                </h3>
                <div className="grid grid-cols-2 gap-x-6">
                  {Object.entries(status.sections).map(([key, present]) => (
                    <SectionRow
                      key={key}
                      label={SECTION_LABELS[key] ?? key}
                      present={present}
                    />
                  ))}
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-4">
                <div className="text-center">
                  <p className="text-2xl font-bold text-slate-900">{status.skills_count}</p>
                  <p className="text-xs text-slate-500">skills extracted</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-slate-900">{status.experience_count}</p>
                  <p className="text-xs text-slate-500">experience items</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-slate-900">{status.proof_points_count}</p>
                  <p className="text-xs text-slate-500">proof points</p>
                  {status.proof_points_count === 0 && (
                    <p className="text-xs text-amber-600 mt-0.5">Configure in profile.yaml</p>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3 border-t border-slate-100 pt-4">
                <a href={`${API_BASE}/api/resume/json`} target="_blank" rel="noopener noreferrer">
                  <Button variant="outline" size="sm">
                    <ExternalLink className="h-3.5 w-3.5 mr-1" /> View parsed JSON
                  </Button>
                </a>
                <Link href="/settings">
                  <Button variant="outline" size="sm">
                    Edit proof points
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {!status.parsed && status.exists && (
            <div className="px-5 py-4 text-sm text-amber-700">
              CV file exists but could not be parsed. Try re-uploading.
            </div>
          )}
        </div>
      )}

      {!status?.exists && !loading && (
        <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50 p-6 text-center">
          <AlertCircle className="mx-auto mb-2 h-6 w-6 text-amber-500" />
          <p className="text-sm font-medium text-amber-800">No master CV found</p>
          <p className="mt-1 text-xs text-amber-600">
            Upload your CV above to enable automatic tailoring for shortlisted jobs.
          </p>
        </div>
      )}
    </div>
  );
}
