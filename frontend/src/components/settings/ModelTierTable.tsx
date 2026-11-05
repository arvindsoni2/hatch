"use client";

import { useEffect, useState } from "react";

import { SectionCard } from "@/components/ui/section-card";
import { setupRequest } from "@/lib/setup";

type TierRow = {
  tier: string;
  route: string;
  model_id: string | null;
  display_name: string;
  status: string;
  thinking: boolean;
  max_output_tokens: number;
  deadline_s: number;
};

type TierPayload = {
  tiers: TierRow[];
  tier_l: { available: boolean; enabled: boolean; min_ram_gb: number };
};

export function ModelTierTable() {
  const [data, setData] = useState<TierPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setupRequest<TierPayload>("/api/setup/model-tiers")
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setError("Model tiers are unavailable.");
      });
    return () => { cancelled = true; };
  }, []);

  const toggleTierL = async (enabled: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await setupRequest("/api/setup/intent", {
        method: "PATCH",
        body: JSON.stringify({ tier_l_enabled: enabled }),
      });
      setData((current) => current
        ? { ...current, tier_l: { ...current.tier_l, enabled } }
        : current);
    } catch {
      setError("Could not save the large model setting.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title="Local model tiers"
      description="Models are promoted only after the Phase 2 bench and the route's regression bench both pass."
    >
      {error ? <p className="mb-3 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
      {!data && !error ? <p className="text-sm text-[var(--text-dim)]">Loading model tiers…</p> : null}
      {data && Array.isArray(data.tiers) ? (
        <>
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--text-dim)]">
              <tr>
                <th className="py-2 font-medium">Tier</th>
                <th className="py-2 font-medium">Route</th>
                <th className="py-2 font-medium">Model</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2 font-medium">Deadline</th>
              </tr>
            </thead>
            <tbody>
              {data.tiers.map((row) => (
                <tr key={row.tier} className="border-t border-[var(--border)]">
                  <td className="py-2 font-mono text-xs text-[var(--text)]">{row.tier}</td>
                  <td className="py-2 text-[var(--text)]">{row.route}</td>
                  <td className="py-2 text-[var(--text)]">{row.display_name}</td>
                  <td className="py-2 text-[var(--text-dim)]">{row.status}</td>
                  <td className="py-2 font-mono text-xs text-[var(--text-dim)]">{row.deadline_s}s</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.tier_l?.available ? (
            <label className="mt-4 flex items-center gap-2 text-sm text-[var(--text)]">
              <input
                type="checkbox"
                checked={data.tier_l.enabled}
                disabled={saving}
                onChange={(event) => void toggleTierL(event.target.checked)}
              />
              Enable the large model (Tier L)
            </label>
          ) : null}
        </>
      ) : null}
    </SectionCard>
  );
}
