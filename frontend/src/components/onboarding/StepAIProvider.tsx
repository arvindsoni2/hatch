"use client";

import { Cpu, Loader2, CheckCircle, XCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import type { LocaleBoard } from "@/lib/api";

export const LLM_PROVIDERS = [
  { id: "anthropic", label: "Anthropic (Claude)", keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001", primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai", label: "OpenAI (GPT)", keyEnv: "OPENAI_API_KEY", triageDefault: "gpt-4o-mini", primaryDefault: "gpt-4o" },
  { id: "google", label: "Google (Gemini) — free tier", keyEnv: "GOOGLE_API_KEY", triageDefault: "gemini-2.5-flash-lite", primaryDefault: "gemini-2.5-flash" },
  { id: "ollama", label: "Ollama (local — free)", keyEnv: "", triageDefault: "gemma3:4b", primaryDefault: "qwen3:14b" },
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
  const handleProviderChange = (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (p) {
      onLlmChange({ ...llm, provider: providerId, triage_model: p.triageDefault, primary_model: p.primaryDefault, api_key_env: p.keyEnv });
      onTestApiKeyChange("");
    }
  };

  return (
    <div className="space-y-5">
      <CardHeader className="px-0 pt-0">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-brand-600" />
          <CardTitle>AI provider</CardTitle>
        </div>
        <CardDescription>Choose your LLM provider and enable job boards.</CardDescription>
      </CardHeader>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {LLM_PROVIDERS.map((p) => (
          <button
            key={p.id}
            onClick={() => handleProviderChange(p.id)}
            className={`p-4 border-2 rounded-lg text-left transition-colors ${
              llm.provider === p.id ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="font-medium text-sm">{p.label}</div>
            {p.id === "google" && <div className="text-xs text-green-600 mt-1">Recommended — free tier available</div>}
            {p.id === "ollama" && <div className="text-xs text-green-600 mt-1">No API key needed</div>}
          </button>
        ))}
      </div>

      {llm.provider !== "ollama" && (
        <div className="space-y-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-sm font-medium text-amber-800">API key setup</p>
          <p className="text-xs text-amber-700">
            Set <code className="bg-amber-100 px-1 rounded">{llm.api_key_env}</code> in your{" "}
            <code className="bg-amber-100 px-1 rounded">.env</code> file. Your key is never stored in profile.yaml.
          </p>
          <div className="flex gap-2">
            <Input
              type="password"
              className="flex-1 text-sm"
              placeholder="Paste key to test (will be saved to .env)"
              value={testApiKey}
              onChange={(e) => { onTestApiKeyChange(e.target.value); }}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={onTestConnection}
              disabled={!testApiKey || testingConnection}
            >
              {testingConnection ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
            </Button>
          </div>
          {connectionResult && (
            <div className={`flex items-center gap-2 text-sm ${connectionResult.ok ? "text-green-700" : "text-red-700"}`}>
              {connectionResult.ok
                ? <><CheckCircle className="h-4 w-4" /> Connection successful</>
                : <><XCircle className="h-4 w-4" /> {connectionResult.error ?? "Connection failed"}</>}
            </div>
          )}
        </div>
      )}

      {llm.provider === "ollama" && (
        <div className="space-y-1">
          <Label>Ollama base URL</Label>
          <Input
            value={llm.base_url || ""}
            onChange={(e) => onLlmChange({ ...llm, base_url: e.target.value || null })}
            placeholder="http://localhost:11434"
          />
        </div>
      )}

      {boards.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">Job boards to scrape</p>
          <div className="grid grid-cols-2 gap-2">
            {boards.map((b) => (
              <label key={b.id} className="flex items-center gap-2 p-2 border rounded-md cursor-pointer hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={enabledBoards.has(b.id)}
                  onChange={() => {
                    const next = new Set(enabledBoards);
                    if (next.has(b.id)) next.delete(b.id); else next.add(b.id);
                    onEnabledBoardsChange(next);
                  }}
                />
                <span className="text-sm">{b.name}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-1 w-full sm:w-1/3">
        <Label>Scrape interval (hours)</Label>
        <Input
          type="number"
          min={1}
          max={24}
          value={scrapeIntervalHours}
          onChange={(e) => onScrapeIntervalChange(parseInt(e.target.value) || 4)}
        />
      </div>
    </div>
  );
}
