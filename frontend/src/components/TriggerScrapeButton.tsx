"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Zap, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

interface ScrapeResult {
  agent: string;
  result: {
    sources_run: number;
    jobs_found: number;
    jobs_new: number;
    errors: string[];
  };
}

export function TriggerScrapeButton({ variant = "primary" }: { variant?: "primary" | "link" }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<ScrapeResult["result"] | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const handleClick = async () => {
    setState("running");
    setResult(null);
    setErrorMsg("");
    try {
      const res = await fetch("/api/agents/scout/trigger", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ScrapeResult = await res.json();
      setResult(data.result);
      setState("done");
      router.refresh();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setState("error");
    }
  };

  if (variant === "link") {
    return (
      <span className="flex items-center gap-2">
        <button
          onClick={handleClick}
          disabled={state === "running"}
          className="text-xs font-medium underline underline-offset-2 disabled:opacity-50"
        >
          {state === "running" ? "Scraping…" : "Trigger scrape now"}
        </button>
        {state === "done" && result && (
          <span className="text-xs text-green-600 font-medium">
            ✓ {result.jobs_new} new / {result.jobs_found} found
          </span>
        )}
        {state === "error" && (
          <span className="text-xs text-red-500">Failed — {errorMsg}</span>
        )}
      </span>
    );
  }

  return (
    <div className="space-y-3">
      <button
        onClick={handleClick}
        disabled={state === "running"}
        className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {state === "running" ? (
          <><Loader2 className="h-4 w-4 animate-spin" /> Scraping…</>
        ) : (
          <><Zap className="h-4 w-4" /> Trigger scrape now</>
        )}
      </button>

      {state === "done" && result && (
        <div className="flex items-start gap-2 rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800">
          <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-green-600" />
          <div>
            <span className="font-medium">{result.jobs_new} new jobs found</span>
            <span className="text-green-600 ml-1">
              ({result.jobs_found} total across {result.sources_run} sources)
            </span>
            {result.errors.length > 0 && (
              <p className="mt-1 text-xs text-amber-700">
                {result.errors.length} source(s) had errors.
              </p>
            )}
          </div>
        </div>
      )}

      {state === "error" && (
        <div className="flex items-center gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Scrape failed: {errorMsg}
        </div>
      )}
    </div>
  );
}
