"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { AiEngineSelector } from "@/components/setup/AiEngineSelector";
import { CapabilitySelector } from "@/components/setup/CapabilitySelector";
import { ModelRoutingSelector } from "@/components/setup/ModelRoutingSelector";
import { SetupStatusPanel } from "@/components/setup/SetupStatusPanel";
import {
  getModelDiscovery,
  getProviders,
  setupRequest,
  useSetupStatus,
  type AiMode,
  type BackendProfile,
  type DiscoveryResult,
  type Provider,
  type SetupIntent,
} from "@/lib/setup";

export function AiCapabilitiesForm({ context, onSaved }: {
  context: "onboarding" | "settings";
  onSaved?: (intent: SetupIntent) => void;
}) {
  const { status, loading, error: statusError, checkAgain } = useSetupStatus();
  const hydrated = useRef(false);
  const [mode, setMode] = useState<AiMode>("none");
  const [profile, setProfile] = useState<BackendProfile>("core");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [primaryModel, setPrimaryModel] = useState("");
  const [triageModel, setTriageModel] = useState("");
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    void getProviders().then((result) => {
      if (!cancelled) setProviders(result.providers);
    }).catch(() => {
      if (!cancelled) setMessage("Cloud provider catalog is unavailable.");
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!status || hydrated.current) return;
    hydrated.current = true;
    const intent = status.intent;
    setMode(intent.ai_mode === "not_configured" ? "none" : intent.ai_mode);
    setProfile(intent.backend_profile);
    setProviderId(intent.cloud_provider ?? "");
    setPrimaryModel(intent.cloud_primary_model ?? intent.local_primary_model ?? "");
    setTriageModel(intent.cloud_triage_model ?? intent.local_triage_model ?? "");
    onSaved?.(intent);
  }, [onSaved, status]);

  useEffect(() => {
    if (mode !== "cloud" || providerId || providers.length === 0) return;
    const provider = providers[0];
    setProviderId(provider.id);
    setPrimaryModel(provider.primary_model);
    setTriageModel(provider.triage_model);
  }, [mode, providerId, providers]);

  useEffect(() => {
    if (mode !== "local") {
      setDiscovery(null);
      setDiscoveryError(null);
      return;
    }
    let cancelled = false;
    void getModelDiscovery().then((result) => {
      if (cancelled) return;
      setDiscovery(result);
      setDiscoveryError(result.error ?? null);
      setPrimaryModel((current) => current || result.recommended_primary?.catalog_id || "");
      setTriageModel((current) => current || result.recommended_triage?.catalog_id || "");
    }).catch((caught) => {
      if (!cancelled) setDiscoveryError(caught instanceof Error ? caught.message : "Model discovery failed.");
    });
    return () => { cancelled = true; };
  }, [mode]);

  const changeMode = (next: AiMode) => {
    setMode(next);
    setMessage(null);
    if (next === "none") {
      setProviderId("");
      setPrimaryModel("");
      setTriageModel("");
    } else if (next === "cloud") {
      const provider = providers[0];
      if (provider) {
        setProviderId(provider.id);
        setPrimaryModel(provider.primary_model);
        setTriageModel(provider.triage_model);
      }
    } else if (next === "local") {
      setProviderId("");
      setPrimaryModel("");
      setTriageModel("");
    }
  };

  const changeProvider = (provider: Provider) => {
    setProviderId(provider.id);
    setPrimaryModel(provider.primary_model);
    setTriageModel(provider.triage_model);
  };

  const save = (defer = false) => {
    const nextMode = defer ? "none" : mode;
    if (!defer && nextMode !== "none" && (!primaryModel || !triageModel)) {
      setMessage(`Select both ${nextMode} model routes before saving.`);
      return;
    }
    startTransition(async () => {
      try {
        const payload = {
          ai_mode: nextMode,
          backend_profile: profile,
          experience: profile === "core" ? "essential" : "custom",
          local_primary_model: nextMode === "local" ? primaryModel : null,
          local_triage_model: nextMode === "local" ? triageModel : null,
          cloud_provider: nextMode === "cloud" ? providerId : null,
          cloud_primary_model: nextMode === "cloud" ? primaryModel : null,
          cloud_triage_model: nextMode === "cloud" ? triageModel : null,
          restart_required: nextMode !== "none" || profile !== status?.capabilities.profile,
        };
        const result = await setupRequest<{ intent: SetupIntent }>("/api/setup/intent", {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        setMode(nextMode);
        setMessage(defer ? "AI setup deferred. You can finish it later in Settings." : "Selection saved. Complete any host actions shown below.");
        onSaved?.(result.intent);
        checkAgain();
      } catch (caught) {
        setMessage(caught instanceof Error ? caught.message : "Setup choices could not be saved.");
      }
    });
  };

  const testProvider = () => {
    if (mode !== "cloud" || !providerId || !primaryModel || !triageModel) return;
    startTransition(async () => {
      try {
        const result = await setupRequest<{ ok: boolean; status: string; error?: string }>("/api/setup/provider/test", {
          method: "POST",
          body: JSON.stringify({ provider: providerId, primary_model: primaryModel, triage_model: triageModel }),
        });
        setMessage(result.ok ? "Provider connection is ready." : `Provider test: ${result.status}. ${result.error ?? ""}`.trim());
        checkAgain();
      } catch (caught) {
        setMessage(caught instanceof Error ? caught.message : "Provider test failed.");
      }
    });
  };

  return (
    <div className="grid gap-5">
      {context === "settings" ? <SetupStatusPanel error={statusError} loading={loading} onCheckAgain={checkAgain} status={status} /> : null}
      <section className="grid gap-6 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <AiEngineSelector onChange={changeMode} value={mode} />
        <ModelRoutingSelector
          discovery={discovery}
          discoveryError={discoveryError}
          mode={mode}
          onPrimaryChange={setPrimaryModel}
          onProviderChange={changeProvider}
          onTriageChange={setTriageModel}
          primaryModel={primaryModel}
          providerId={providerId}
          providers={providers}
          triageModel={triageModel}
        />
        <CapabilitySelector onChange={setProfile} value={profile} />
        {mode === "cloud" ? (
          <div>
            <Button disabled={isPending || !providerId} onClick={testProvider} type="button" variant="outline">Test provider connection</Button>
            <p className="mt-1 text-xs text-[var(--text-muted)]">This explicit test makes a small billable provider request. Status polling never calls the provider.</p>
          </div>
        ) : null}
        {message ? <p className="text-sm text-[var(--text-muted)]" role="status">{message}</p> : null}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button disabled={isPending || loading} onClick={() => save(false)} type="button">Save AI & capabilities</Button>
          {context === "onboarding" ? <Button disabled={isPending} onClick={() => save(true)} type="button" variant="outline">Finish setup later</Button> : null}
        </div>
      </section>
    </div>
  );
}
