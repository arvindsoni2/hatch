"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Cpu, ShieldCheck, TriangleAlert } from "lucide-react";
import { API_BASE } from "@/lib/api";

type ModelItem = {
  id: string;
  display_name: string;
  role: "triage" | "combined_capable_primary";
  download_size_gb: number;
  min_ram_gb: number;
  recommended_ram_gb: number;
};

type SetupStatus = {
  runtime: {
    ai_mode: "not_configured" | "cloud" | "local" | "custom";
    quality_mode: string;
    provider?: string | null;
    warnings?: string[];
  };
  next_command?: string | null;
};

type HardwareResponse = {
  detected: boolean;
  message?: string;
  next_command?: string;
  snapshot?: {
    platform: { os_family: string; arch: string };
    memory: { total_gb: number };
    storage: { models_dir_free_gb: number };
  };
};

type RecommendationResponse = {
  recommended: Array<{ model_id: string; already_downloaded: boolean }>;
  compatible: Array<{ model_id: string; already_downloaded: boolean }>;
  not_recommended: Array<{ model_id: string; reasons: string[] }>;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

const PROVIDERS = [
  { id: "google_genai", label: "Google Gemini" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic Claude" },
] as const;

export default function AiSettingsPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [hardware, setHardware] = useState<HardwareResponse | null>(null);
  const [catalog, setCatalog] = useState<ModelItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null);
  const [selectedModels, setSelectedModels] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const load = useCallback(async () => {
    const [nextStatus, nextHardware, nextCatalog] = await Promise.all([
      request<SetupStatus>("/api/setup/status"),
      request<HardwareResponse>("/api/setup/hardware"),
      request<{ models: ModelItem[] }>("/api/setup/models/catalog"),
    ]);
    setStatus(nextStatus);
    setHardware(nextHardware);
    setCatalog(nextCatalog.models);
    if (nextHardware.detected) {
      setRecommendations(await request<RecommendationResponse>("/api/setup/models/recommendations"));
    }
  }, []);

  useEffect(() => {
    void load().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "Could not load AI setup.");
    });
  }, [load]);

  const saveMode = (path: string, payload?: object) => {
    startTransition(async () => {
      try {
        const result = await request<{ next_command?: string }>(path, {
          method: "POST",
          body: payload ? JSON.stringify(payload) : undefined,
        });
        setMessage(`Saved. Next: ${result.next_command ?? "hatch apply-ai-config"}`);
        await load();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not save AI setup.");
      }
    });
  };

  const toggleModel = (modelId: string) => {
    setSelectedModels((current) => {
      const next = new Set(current);
      if (next.has(modelId)) next.delete(modelId);
      else next.add(modelId);
      return next;
    });
  };

  const bucketFor = (modelId: string) => {
    if (recommendations?.recommended.some((item) => item.model_id === modelId)) return "Recommended";
    if (recommendations?.compatible.some((item) => item.model_id === modelId)) return "Compatible";
    return "Advanced override";
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link href="/settings" className="inline-flex items-center gap-2 text-sm text-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" /> Settings
      </Link>

      <header>
        <h1 className="text-2xl font-semibold text-fg">AI setup</h1>
        <p className="mt-1 text-sm text-muted">
          Choose when and where Hatch runs AI. No model downloads start without your confirmation.
        </p>
      </header>

      <section className="rounded-xl border border-border bg-surface p-5">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-accent" />
          <div>
            <h2 className="font-semibold text-fg">Current status</h2>
            <p className="text-sm text-muted">
              {status ? `${status.runtime.ai_mode} · ${status.runtime.quality_mode}` : "Loading…"}
            </p>
          </div>
        </div>
        {message ? <p className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-fg">{message}</p> : null}
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => saveMode("/api/setup/skip-ai")}
          className="rounded-xl border border-border bg-surface p-5 text-left hover:border-accent disabled:opacity-50"
        >
          <h2 className="font-semibold text-fg">Use Hatch now, set up AI later</h2>
          <p className="mt-2 text-sm text-muted">Profile, tracker, and manual application tools remain available.</p>
        </button>

        {PROVIDERS.map((provider) => (
          <button
            key={provider.id}
            type="button"
            disabled={isPending}
            onClick={() => saveMode("/api/setup/cloud-provider", { provider: provider.id })}
            className="rounded-xl border border-border bg-surface p-5 text-left hover:border-accent disabled:opacity-50"
          >
            <h2 className="font-semibold text-fg">Use {provider.label}</h2>
            <p className="mt-2 text-sm text-muted">
              Prompts may be sent to this provider. Add the key afterward with{" "}
              <code>hatch secrets set {provider.id}</code>.
            </p>
          </button>
        ))}
      </section>

      <section className="rounded-xl border border-border bg-surface p-5">
        <div className="flex items-center gap-3">
          <Cpu className="h-5 w-5 text-accent" />
          <div>
            <h2 className="font-semibold text-fg">Run AI locally</h2>
            <p className="text-sm text-muted">
              {hardware?.detected
                ? `${hardware.snapshot?.memory.total_gb} GB RAM · ${hardware.snapshot?.storage.models_dir_free_gb} GB model storage free`
                : "Hardware not detected yet. Run hatch probe."}
            </p>
          </div>
        </div>

        {hardware?.detected ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {catalog.map((model) => (
              <label key={model.id} className="rounded-lg border border-border p-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selectedModels.has(model.id)}
                    onChange={() => toggleModel(model.id)}
                    className="mt-1"
                  />
                  <span>
                    <span className="block font-medium text-fg">{model.display_name}</span>
                    <span className="mt-1 block text-xs text-muted">{bucketFor(model.id)}</span>
                    <span className="block text-xs text-muted">
                      {model.download_size_gb} GB · {model.recommended_ram_gb} GB RAM recommended
                    </span>
                  </span>
                </div>
              </label>
            ))}
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            <TriangleAlert className="h-4 w-4" /> Run <code>hatch probe</code>, then refresh this page.
          </div>
        )}

        <button
          type="button"
          disabled={isPending || selectedModels.size === 0}
          onClick={() =>
            saveMode("/api/setup/local-model-selection", {
              selected_model_ids: Array.from(selectedModels),
            })
          }
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          <CheckCircle2 className="h-4 w-4" /> Save local selection
        </button>
        <p className="mt-2 text-xs text-muted">
          Saving records your choice only. Run <code>hatch models install</code> to confirm downloads.
        </p>
      </section>
    </div>
  );
}
