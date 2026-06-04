"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field, Choice, ToggleRow, Seg } from "./OnboardingPrimitives";
import type { LocaleBoard } from "@/lib/api";
import { fetchOllamaModels } from "@/lib/api";

export const LLM_PROVIDERS = [
  { id: "google_genai", label: "Google Gemini",   sub: "Free tier available — great default",  keyEnv: "GOOGLE_API_KEY",    triageDefault: "gemini-2.5-flash-lite",     primaryDefault: "gemini-2.5-flash" },
  { id: "anthropic",    label: "Anthropic Claude", sub: "Strongest tailoring quality",          keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001", primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai",       label: "OpenAI",           sub: "GPT-4o family",                        keyEnv: "OPENAI_API_KEY",    triageDefault: "gpt-4o-mini",               primaryDefault: "gpt-4o" },
  { id: "ollama",       label: "Ollama (local)",   sub: "Runs on your machine — $0, no key",    keyEnv: "",                  triageDefault: "",                          primaryDefault: "" },
];

export interface LLMData {
  provider: string;
  triage_model: string;
  primary_model: string;
  api_key_env: string;
  base_url: string | null;
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
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaError, setOllamaError] = useState<string | null>(null);

  const loadOllamaModels = async () => {
    setOllamaLoading(true);
    setOllamaError(null);
    try {
      const result = await fetchOllamaModels();
      setOllamaModels(result.models);
      if (result.error) setOllamaError("Ollama unreachable — is it running?");
      return result.models;
    } catch {
      setOllamaError("Could not fetch Ollama models");
      return [];
    } finally {
      setOllamaLoading(false);
    }
  };

  const handleProviderChange = async (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (!p) return;
    let primary = p.primaryDefault;
    let triage = p.triageDefault;
    if (providerId === "ollama") {
      const models = await loadOllamaModels();
      primary = models[0] ?? "";
      triage = models.length > 1 ? models[1] : (models[0] ?? "");
    }
    onLlmChange({
      ...llm,
      provider: providerId,
      triage_model: triage,
      primary_model: primary,
      api_key_env: p.keyEnv,
      base_url: providerId === "ollama" ? "http://host.containers.internal:11434" : null,
    });
    onTestApiKeyChange("");
  };

  useEffect(() => {
    if (llm.provider === "ollama" && ollamaModels.length === 0) {
      void loadOllamaModels();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const needsKey = llm.provider !== "ollama";

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
              onClick={() => void handleProviderChange(p.id)}
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

      {llm.provider === "ollama" && (
        <>
          <Field label="Ollama base URL" hint="Container deployment: use http://host.containers.internal:11434. Direct host install: http://localhost:11434.">
            <Input
              value={llm.base_url || ""}
              onChange={(e) => onLlmChange({ ...llm, base_url: e.target.value || "http://host.containers.internal:11434" })}
              placeholder="http://host.containers.internal:11434"
            />
          </Field>

          <Field label="Primary model" hint="Used for tailoring, coaching, and detailed analysis.">
            {ollamaLoading ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-dim)]">
                <Loader2 className="h-4 w-4 animate-spin" /> Fetching installed models…
              </div>
            ) : ollamaError ? (
              <p className="text-sm text-[var(--danger)]">{ollamaError}</p>
            ) : ollamaModels.length === 0 ? (
              <p className="text-sm text-[var(--text-dim)]">No models found — pull a model with <code>ollama pull &lt;model&gt;</code> first.</p>
            ) : (
              <select
                value={llm.primary_model}
                onChange={(e) => onLlmChange({ ...llm, primary_model: e.target.value })}
                className="w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              >
                {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </Field>

          <Field label="Triage model" hint="Fast model for quick relevance filtering (can be the same as primary).">
            {!ollamaLoading && ollamaModels.length > 0 && (
              <select
                value={llm.triage_model}
                onChange={(e) => onLlmChange({ ...llm, triage_model: e.target.value })}
                className="w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              >
                {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </Field>
        </>
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
