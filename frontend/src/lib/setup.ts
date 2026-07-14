"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

export type AiMode = "not_configured" | "none" | "local" | "cloud" | "custom";
export type BackendProfile = "core" | "browser" | "local-embeddings" | "full";

export type SetupIntent = {
  schema_version: 2;
  ai_mode: AiMode;
  backend_profile: BackendProfile;
  experience: "essential" | "full_ai" | "custom";
  local_primary_model?: string | null;
  local_triage_model?: string | null;
  cloud_provider?: string | null;
  cloud_primary_model?: string | null;
  cloud_triage_model?: string | null;
  restart_required?: boolean;
};

export type HostAction = {
  id: string;
  label: string;
  command?: string | null;
  executable?: string | null;
  args: string[];
};

export type SetupStatus = {
  overall_status: "ready" | "needs_user_input" | "pending_host_action" | "error";
  onboarding: { status: string; last_completed_step: string | null };
  intent: SetupIntent;
  ai: { mode: AiMode; status: string; healthy: boolean };
  capabilities: {
    profile: BackendProfile;
    selected_profile: BackendProfile;
    enabled: string[];
    operation: unknown;
  };
  next_actions: HostAction[];
};

export type Provider = {
  id: string;
  label: string;
  primary_model: string;
  triage_model: string;
  models: string[];
  privacy: string;
  cost: string;
  configured: boolean;
};

export type DiscoveredModel = {
  catalog_id: string;
  filename: string;
  family: string;
  quantization: string;
  download_size_gb: number;
  min_ram_gb: number;
};

export type DiscoveryResult = {
  source: "live" | "cache" | "fallback";
  models: DiscoveredModel[];
  compatible: DiscoveredModel[];
  recommended_primary?: DiscoveredModel | null;
  recommended_triage?: DiscoveredModel | null;
  error?: string | null;
};

export async function setupRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Setup request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const getSetupStatus = () => setupRequest<SetupStatus>("/api/setup/status");
export const getProviders = () => setupRequest<{ providers: Provider[] }>("/api/setup/providers");
export const getModelDiscovery = () => setupRequest<DiscoveryResult>("/api/setup/models/discovery");

export function nextSetupPollInterval(status: SetupStatus | null, visible: boolean, elapsedMs: number) {
  if (!visible || !status || status.overall_status === "ready" || status.overall_status === "error") {
    return null;
  }
  return elapsedMs >= 120_000 ? 15_000 : 5_000;
}

export function useSetupStatus({ visible = true }: { visible?: boolean } = {}) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [pageVisible, setPageVisible] = useState(() =>
    typeof document === "undefined" || document.visibilityState === "visible"
  );
  const startedAt = useRef(Date.now());
  const checkAgain = useCallback(() => {
    setError(null);
    setLoading(true);
    setRefresh((value) => value + 1);
  }, []);

  useEffect(() => {
    const update = () => setPageVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await getSetupStatus();
        if (cancelled) return;
        setStatus(next);
        setError(null);
        setLoading(false);
        const interval = nextSetupPollInterval(next, visible && pageVisible, Date.now() - startedAt.current);
        if (interval !== null) timer = setTimeout(poll, interval);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Could not check setup status.");
        setLoading(false);
      }
    };
    if (visible && pageVisible) void poll();
    else setLoading(false);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [pageVisible, refresh, visible]);

  return { status, loading, error, checkAgain };
}

export function modeLabel(mode: AiMode) {
  if (mode === "cloud") return "Cloud AI";
  if (mode === "local") return "Local AI";
  if (mode === "none") return "No AI";
  return "Not configured";
}

export function profileLabel(profile: BackendProfile) {
  return {
    core: "Standard Hatch",
    browser: "Core + browser",
    "local-embeddings": "Core + local embeddings",
    full: "Full capabilities",
  }[profile];
}
