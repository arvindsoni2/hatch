"use client";

import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field, Choice, ToggleRow, Seg } from "./OnboardingPrimitives";
import type { LocaleBoard } from "@/lib/api";

// Model name constants shared with fetch_models.sh (single source of truth for display/traces).
export const LLAMACPP_PRIMARY_MODEL = "qwen3-8b-q5_k_m";
export const LLAMACPP_TRIAGE_MODEL  = "qwen3-0.6b-q8_0";

export const LLM_PROVIDERS = [
  { id: "llamacpp",     label: "Local AI (free)",    sub: "llama.cpp bundled in this stack — no API key, no cost, privacy-first", keyEnv: "", triageDefault: LLAMACPP_TRIAGE_MODEL, primaryDefault: LLAMACPP_PRIMARY_MODEL },
  { id: "google_genai", label: "Google Gemini",      sub: "Free tier available",                                                   keyEnv: "GOOGLE_API_KEY",    triageDefault: "gemini-2.5-flash-lite",     primaryDefault: "gemini-2.5-flash" },
  { id: "anthropic",    label: "Anthropic Claude",   sub: "Strongest tailoring quality",                                           keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001", primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai",       label: "OpenAI",             sub: "GPT-4o family",                                                         keyEnv: "OPENAI_API_KEY",    triageDefault: "gpt-4o-mini",               primaryDefault: "gpt-4o" },
];

export interface LLMData {
  provider: string;
  triage_model: string;
  primary_model: string;
  api_key_env: string;
  base_url: string | null;
  triage_base_url: string;
  temperature: number;
  max_retries: number;
  track_costs: boolean;
  monthly_budget: number;
  currency: string;
}

interface StepAIProviderProps {
  llm: LLMData;
  onLlmChange: (llm: LLMData) => void;
  testApiKey: string;
  onTestApiKeyChange: (key: string) => void;
  testingConnection: boolean;
  connectionResult: { ok: boolean; error?: string } | null;
  onTestConnection: () => void;
  boards: LocaleBoard[];
  enabledBoards: Set<string>;
  onEnabledBoardsChange: (boards: Set<string>) => void;
  scrapeIntervalHours: number;
  onScrapeIntervalChange: (hours: number) => void;
}

export function StepAIProvider({
  llm, onLlmChange,
  testApiKey, onTestApiKeyChange,
  testingConnection, connectionResult, onTestConnection,
  boards, enabledBoards, onEnabledBoardsChange,
  scrapeIntervalHours, onScrapeIntervalChange,
}: StepAIProviderProps) {
  const handleProviderChange = (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (!p) return;
    let baseUrl: string | null = null;
    let triageBaseUrl = "";

    if (providerId === "llamacpp") {
      baseUrl = "http://llm-primary:8080/v1";
      triageBaseUrl = "http://llm-triage:8081/v1";
    }
    onLlmChange({
      ...llm,
      provider: providerId,
      triage_model: p.triageDefault,
      primary_model: p.primaryDefault,
      api_key_env: p.keyEnv,
      base_url: baseUrl,
      triage_base_url: triageBaseUrl,
    });
    onTestApiKeyChange("");
  };

  const needsKey = llm.provider !== "llamacpp";

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 6 · AI &amp; launch
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Pick the engine.
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Hatch uses your own AI provider, so you control cost and privacy. Switch anytime in Settings.
      </p>

      <Field label="AI provider" req>
        <div className="grid grid-cols-1 gap-2">
          {LLM_PROVIDERS.map((p) => (
            <Choice
              key={p.id}
              on={llm.provider === p.id}
              onClick={() => handleProviderChange(p.id)}
              title={p.label}
              sub={p.sub}
            />
          ))}
        </div>
      </Field>

      {needsKey && (
        <Field
          label="API key"
          req
          hint="Validated live, then saved to your local machine only — never committed to the repo."
        >
          <div className="flex gap-2">
            <Input
              type="password"
              className="flex-1 font-mono text-[12.5px]"
              placeholder={llm.api_key_env}
              value={testApiKey}
              onChange={(e) => { onTestApiKeyChange(e.target.value); }}
            />
            <button
              type="button"
              onClick={onTestConnection}
              disabled={!testApiKey || testingConnection}
              className="flex-shrink-0 px-4 rounded-[var(--r-field,8px)] border border-[var(--border-strong)] text-[13px] font-[550] text-[var(--text)] disabled:opacity-40 transition-colors hover:bg-[var(--surface-3)]"
              style={{ background: "var(--surface-2)" }}
            >
              {testingConnection ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
            </button>
          </div>
          {connectionResult && (
            <div
              className={`flex items-center gap-2 mt-2 text-sm px-3 py-2 rounded-[var(--r-field,8px)] ${
                connectionResult.ok ? "text-[var(--success)]" : "text-[var(--danger)]"
              }`}
              style={{ background: connectionResult.ok ? "var(--success-soft)" : "var(--danger-soft)" }}
            >
              {connectionResult.ok
                ? <><CheckCircle className="h-4 w-4" /> Connected — key works.</>
                : <><XCircle className="h-4 w-4" /> {connectionResult.error ?? "Connection failed"}</>}
            </div>
          )}
        </Field>
      )}

      {llm.provider === "llamacpp" && (
        <div className="mt-3 rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-[550] text-[var(--text)]">Bundled AI services</span>
            <button
              type="button"
              onClick={onTestConnection}
              disabled={testingConnection}
              className="text-[12px] underline text-[var(--accent)] disabled:opacity-50"
            >
              {testingConnection ? "Checking…" : "Check reachability"}
            </button>
          </div>
          {connectionResult && !connectionResult.ok && (
            <div className="flex items-start gap-2 text-sm text-[var(--danger)]" style={{ background: "var(--danger-soft)", borderRadius: "var(--r-field,8px)", padding: "8px 12px" }}>
              <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>AI services unreachable. Start them with: <code className="font-mono text-[11.5px]">docker compose up -d</code></span>
            </div>
          )}
          {connectionResult && connectionResult.ok && (
            <div className="flex items-center gap-2 text-sm text-[var(--success)]" style={{ background: "var(--success-soft)", borderRadius: "var(--r-field,8px)", padding: "8px 12px" }}>
              <CheckCircle className="h-4 w-4" /> AI services are running.
            </div>
          )}
          <p className="text-[12px] text-[var(--text-dim)]">
            Primary: <code className="text-[var(--text)]">{llm.primary_model}</code> on port 8080 ·
            Triage: <code className="text-[var(--text)]">{llm.triage_model}</code> on port 8081
          </p>
        </div>
      )}

      {boards.length > 0 && (
        <Field label="Job boards" hint="Boards for your selected market, enabled by default. Toggle off any you don't want scraped.">
          {boards.map((b) => (
            <ToggleRow
              key={b.id}
              on={enabledBoards.has(b.id)}
              title={b.name}
              sub={enabledBoards.has(b.id) ? "Active" : "Disabled"}
              onToggle={() => {
                const next = new Set(enabledBoards);
                if (next.has(b.id)) next.delete(b.id); else next.add(b.id);
                onEnabledBoardsChange(next);
              }}
            />
          ))}
        </Field>
      )}

      <Field label="How often should Scout run?" hint="More frequent = fresher matches, slightly higher cost. You can change this later.">
        <Seg
          value={String(scrapeIntervalHours)}
          onChange={(v) => onScrapeIntervalChange(Number(v))}
          options={[
            { v: "2", l: "Every 2h" },
            { v: "4", l: "Every 4h" },
            { v: "8", l: "Every 8h" },
          ]}
        />
      </Field>
    </div>
  );
}
