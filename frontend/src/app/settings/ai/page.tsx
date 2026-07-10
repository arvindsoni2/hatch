"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import {
  CheckCircle2,
  Clipboard,
  Cloud,
  Cpu,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SettingsShell } from "@/components/settings/SettingsShell";
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
  schema_version?: number;
  experience?: "essential" | "full_ai" | "custom" | string;
  ai?: {
    mode: "not_configured" | "cloud" | "local" | "custom" | string;
    configured: boolean;
    healthy: boolean;
    provider?: string | null;
    model?: string | null;
    action_required?: string | null;
  };
  capabilities?: {
    profile: "core" | "browser" | "local-embeddings" | "full" | string;
    enabled: string[];
    available_profiles: string[];
    operation?: ProfileOperation | null;
  };
  operation?: ProfileOperation | null;
  runtime: {
    ai_mode: "not_configured" | "cloud" | "local" | "custom";
    quality_mode: string;
    provider?: string | null;
    warnings?: string[];
  };
  next_command?: string | null;
};

type ProfileOperation = {
  id: string;
  label?: string;
  command: string;
  host_action_required: boolean;
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
  { id: "openrouter", label: "OpenRouter", defaultModel: "openai/gpt-4o-mini" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic Claude" },
] as const;

function formatMode(value?: string | null) {
  if (!value || value === "not_configured") return "Basic / use Hatch now, set up AI later";
  return value.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatExperience(value?: string | null) {
  if (value === "full_ai") return "Full AI";
  if (value === "custom") return "Custom";
  return "Essential";
}

function formatProfile(value?: string | null) {
  if (value === "local-embeddings") return "Local embeddings";
  if (value === "full") return "Full";
  if (value === "browser") return "Browser";
  return "Core";
}

function setupSummary(status: SetupStatus | null) {
  const mode = status?.ai?.mode ?? status?.runtime.ai_mode;
  if (!status) {
    return {
      title: "Loading setup status...",
      description: "Checking the local Hatch backend for the current AI setup.",
    };
  }
  if (mode === "not_configured") {
    return {
      title: "Use Hatch now, set up AI later.",
      description: "Manual tracking, profile editing, and settings are available. Tailoring and Coach unlock after AI setup.",
    };
  }
  if (mode === "local") {
    return {
      title: "Local AI is configured.",
      description: "Hatch will use models running on this machine, keeping prompts inside your local workspace.",
    };
  }
  if (mode === "cloud") {
    return {
      title: "Cloud AI is configured.",
      description: "Hatch will use your host-owned provider secrets for AI-assisted tailoring and coaching.",
    };
  }
  return {
    title: "Custom AI runtime is configured.",
    description: "Hatch will use the configured runtime for AI-assisted workflows.",
  };
}

function recommendedTier(recommendations: RecommendationResponse | null) {
  const recommendedIds = recommendations?.recommended.map((item) => item.model_id) ?? [];
  if (recommendedIds.some((id) => /medium|8b|4b|primary/i.test(id))) return "medium";
  if (recommendedIds.length > 0) return "small";
  return "not available yet";
}

function friendlyError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  if (/failed to fetch|network/i.test(error.message)) return "Could not reach the local Hatch backend.";
  if (/probe/i.test(error.message)) return "Run hatch probe, then refresh this page.";
  return fallback;
}

export default function AiSettingsPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [hardware, setHardware] = useState<HardwareResponse | null>(null);
  const [catalog, setCatalog] = useState<ModelItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null);
  const [selectedModels, setSelectedModels] = useState<Set<string>>(() => new Set());
  const [openRouterModel, setOpenRouterModel] = useState("openai/gpt-4o-mini");
  const [message, setMessage] = useState<string | null>(null);
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
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
      setMessage(friendlyError(error, "Could not load AI setup."));
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
        setMessage(friendlyError(error, "Could not save AI setup."));
      }
    });
  };

  const saveExperience = (payload: {
    experience: "essential" | "full_ai" | "custom";
    ai_mode: "not_configured" | "cloud" | "local" | "custom";
    backend_profile: "core" | "browser" | "local-embeddings" | "full";
    acknowledgement: boolean;
  }) => {
    startTransition(async () => {
      try {
        const result = await request<{ next_command?: string }>("/api/setup/experience", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setMessage(`Saved. Next: ${result.next_command ?? "hatch apply-ai-config"}`);
        await load();
      } catch (error) {
        setMessage(friendlyError(error, "Could not save Hatch experience."));
      }
    });
  };

  const refreshHardware = () => {
    startTransition(async () => {
      try {
        const result = await request<HardwareResponse & { started?: boolean }>("/api/setup/hardware", {
          method: "POST",
        });
        setHardware(result);
        setMessage(result.detected ? "Hardware probe status refreshed." : `Run ${result.next_command ?? "hatch probe"} from the host, then refresh.`);
      } catch (error) {
        setMessage(friendlyError(error, "Could not refresh hardware probe status."));
      }
    });
  };

  const testProvider = (providerId: string) => {
    startTransition(async () => {
      try {
        const result = await request<{ ok: boolean; status: string; error?: string }>("/api/setup/provider/test", {
          method: "POST",
          body: JSON.stringify({
            provider: providerId,
            model: providerId === "openrouter" ? openRouterModel.trim() : undefined,
          }),
        });
        setMessage(result.ok ? `Provider test: ${result.status}` : `Provider test: ${result.status}. ${result.error ?? ""}`.trim());
      } catch (error) {
        setMessage(friendlyError(error, "Could not test provider."));
      }
    });
  };

  const copyCommand = async (command: string) => {
    await navigator.clipboard.writeText(command);
    setCopiedCommand(command);
    window.setTimeout(() => setCopiedCommand(null), 1800);
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
  const currentSetup = setupSummary(status);

  return (
    <SettingsShell
      activeHref="/settings/ai"
      title="AI & Capabilities"
      description="Choose the Hatch experience, backend capabilities, and AI provider without putting host-owned secrets in the browser."
    >
      <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
            <div>
              <h2 className="font-semibold text-[var(--text)]">Current setup</h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {currentSetup.title}
              </p>
              <p className="mt-2 text-sm text-[var(--text-dim)]">
                {currentSetup.description}
              </p>
              {status ? (
                <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                  <div className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                    <p className="text-[var(--text-muted)]">Experience: {formatExperience(status.experience)}</p>
                  </div>
                  <div className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                    <p className="text-[var(--text-muted)]">Backend profile: {formatProfile(status.capabilities?.profile)}</p>
                  </div>
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  disabled={isPending}
                  onClick={() => saveExperience({
                    experience: "full_ai",
                    ai_mode: "not_configured",
                    backend_profile: "full",
                    acknowledgement: true,
                  })}
                  type="button"
                >
                  Upgrade to Full AI
                </Button>
                <Button
                  disabled={isPending}
                  onClick={() => saveExperience({
                    experience: "essential",
                    ai_mode: "not_configured",
                    backend_profile: "core",
                    acknowledgement: true,
                  })}
                  type="button"
                  variant="outline"
                >
                  Switch to Essential
                </Button>
              </div>
              {status ? (
                <details className="mt-3 text-sm text-[var(--text-muted)]">
                  <summary className="cursor-pointer font-semibold text-[var(--text-dim)]" role="button" tabIndex={0}>
                    View technical setup details
                  </summary>
                  <dl className="mt-2 grid gap-2 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3">
                    <div className="flex items-center justify-between gap-4">
                      <dt>Mode</dt>
                      <dd className="font-semibold text-[var(--text)]">{formatMode(status.runtime.ai_mode)}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <dt>Quality</dt>
                      <dd className="font-semibold text-[var(--text)]">{formatMode(status.runtime.quality_mode)}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <dt>Provider</dt>
                      <dd className="font-semibold text-[var(--text)]">{status.runtime.provider ?? "local/custom runtime"}</dd>
                    </div>
                  </dl>
                </details>
              ) : null}
            </div>
          </div>
          <div className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-dim)]">
            Test provider: <span className="font-semibold text-[var(--text)]">Not tested yet</span>
          </div>
        </div>
        {message ? <p className="mt-4 rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]" role="status">{message}</p> : null}
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <article className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="flex items-center gap-3">
            <PlayCircle className="h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
            <h2 className="font-semibold text-[var(--text)]">Use Hatch now, set up AI later</h2>
          </div>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="font-semibold text-[var(--text)]">Best for</dt>
              <dd className="text-[var(--text-muted)]">Trying the app and using manual job-search workflows.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Privacy impact</dt>
              <dd className="text-[var(--text-muted)]">No prompts are sent to an AI provider.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Status</dt>
              <dd className="text-[var(--text-muted)]">Ready with limited AI features.</dd>
            </div>
          </dl>
          <Button className="mt-4 w-full" disabled={isPending} onClick={() => saveMode("/api/setup/skip-ai")} type="button" variant="secondary">
            Choose set up later
          </Button>
        </article>

        <article className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="flex items-center gap-3">
            <Cpu className="h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
            <h2 className="font-semibold text-[var(--text)]">Run AI locally</h2>
          </div>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="font-semibold text-[var(--text)]">Best for</dt>
              <dd className="text-[var(--text-muted)]">Privacy and cost control on your own machine.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Setup required</dt>
              <dd className="text-[var(--text-muted)]">Run the hardware probe, select models, then install them from the host CLI.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Status</dt>
              <dd className="text-[var(--text-muted)]">{hardware?.detected ? "Hardware detected" : "Not installed"}</dd>
            </div>
          </dl>
          <div className="mt-4 rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text-dim)]">
            {hardware?.detected ? (
              <div className="grid gap-1">
                <p>Detected RAM: {hardware.snapshot?.memory.total_gb ?? 0} GB</p>
                <p>Model storage free: {hardware.snapshot?.storage.models_dir_free_gb ?? 0} GB</p>
                <p>Recommended local model tier: {recommendedTier(recommendations)}</p>
                <p>Selected models: {selectedModels.size}</p>
              </div>
            ) : (
              <p>Hardware not detected yet. Run hatch probe.</p>
            )}
          </div>
          <Button className="mt-4 w-full" disabled={isPending} onClick={refreshHardware} type="button" variant="outline">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh hardware probe
          </Button>
        </article>

        <article className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="flex items-center gap-3">
            <Cloud className="h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
            <h2 className="font-semibold text-[var(--text)]">Use cloud AI provider</h2>
          </div>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="font-semibold text-[var(--text)]">Best for</dt>
              <dd className="text-[var(--text-muted)]">Quality and convenience when you already use a provider.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Privacy impact</dt>
              <dd className="text-[var(--text-muted)]">Prompts may leave this machine and be processed by the provider.</dd>
            </div>
            <div>
              <dt className="font-semibold text-[var(--text)]">Status</dt>
              <dd className="text-[var(--text-muted)]">Missing secret until added from the host CLI. Not tested yet.</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="flex items-center gap-3">
          <Cloud className="h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
          <div>
            <h2 className="font-semibold text-[var(--text)]">Cloud provider commands</h2>
            <p className="text-sm text-[var(--text-muted)]">Choose a provider here, then add its secret from your terminal. Hatch never asks for API keys in the browser.</p>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {PROVIDERS.map((provider) => {
            const command = `hatch secrets set ${provider.id}`;
            const metadata = provider.id === "openrouter" ? { model: openRouterModel.trim() } : undefined;
            return (
              <article className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-4" key={provider.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-[var(--text)]">{provider.label}</h3>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">Status: missing secret · Not tested yet</p>
                  </div>
                  <Sparkles className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
                </div>
                <code className="mt-3 block overflow-x-auto rounded-[var(--radius-control)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text)]">{command}</code>
                {provider.id === "openrouter" ? (
                  <label className="mt-3 block text-xs font-medium text-[var(--text-muted)]">
                    Model slug
                    <input
                      className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text)]"
                      value={openRouterModel}
                      onChange={(event) => setOpenRouterModel(event.target.value)}
                    />
                  </label>
                ) : null}
                <div className="mt-3 grid gap-2">
                  <Button
                    className="w-full"
                    disabled={isPending}
                    onClick={() => saveMode("/api/setup/cloud-provider", { provider: provider.id, provider_metadata: metadata })}
                    type="button"
                    variant="outline"
                  >
                    Use {provider.label}
                  </Button>
                  <Button
                    aria-label={`Copy ${provider.label} secret command`}
                    className="w-full"
                    onClick={() => void copyCommand(command)}
                    type="button"
                    variant="ghost"
                  >
                    <Clipboard className="h-4 w-4" aria-hidden="true" />
                    Copy command
                  </Button>
                  {provider.id === "openrouter" ? (
                    <Button
                      className="w-full"
                      disabled={isPending}
                      onClick={() => testProvider(provider.id)}
                      type="button"
                      variant="secondary"
                    >
                      Test OpenRouter
                    </Button>
                  ) : null}
                  {copiedCommand === command ? <p className="text-xs font-medium text-[var(--success)]" role="status">Command copied.</p> : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="flex items-center gap-3">
          <Cpu className="h-5 w-5 text-[var(--accent)]" aria-hidden="true" />
          <div>
            <h2 className="font-semibold text-[var(--text)]">Local model selection</h2>
            <p className="text-sm text-[var(--text-muted)]">
              {hardware?.detected
                ? "Select the models Hatch should install and run locally."
                : "Hardware not detected yet. Run hatch probe, then refresh this page."}
            </p>
          </div>
        </div>
        {hardware?.detected ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {catalog.map((model) => (
              <label key={model.id} className="rounded-[var(--radius-control)] border border-[var(--border)] p-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selectedModels.has(model.id)}
                    onChange={() => toggleModel(model.id)}
                    className="mt-1"
                  />
                  <span>
                    <span className="block font-medium text-[var(--text)]">{model.display_name}</span>
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">{bucketFor(model.id)}</span>
                    <span className="block text-xs text-[var(--text-muted)]">
                      {model.download_size_gb} GB · {model.recommended_ram_gb} GB RAM recommended
                    </span>
                  </span>
                </div>
              </label>
            ))}
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-2 rounded-[var(--radius-control)] bg-[var(--warning-soft)] p-3 text-sm text-[var(--warning)]">
            <TriangleAlert className="h-4 w-4" /> Run <code>hatch probe</code>, then refresh this page.
          </div>
        )}

        <Button
          type="button"
          disabled={isPending || selectedModels.size === 0}
          onClick={() =>
            saveMode("/api/setup/local-model-selection", {
              selected_model_ids: Array.from(selectedModels),
            })
          }
          className="mt-4"
        >
          <CheckCircle2 className="h-4 w-4" /> Save local selection
        </Button>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          Saving records your choice only. Run <code>hatch models install</code> to confirm downloads.
        </p>
      </section>
    </SettingsShell>
  );
}
