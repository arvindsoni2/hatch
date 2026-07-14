import type { DiscoveryResult, Provider } from "@/lib/setup";

type Props = {
  mode: "none" | "local" | "cloud" | "not_configured" | "custom";
  providers: Provider[];
  providerId: string;
  primaryModel: string;
  triageModel: string;
  discovery: DiscoveryResult | null;
  discoveryError: string | null;
  onProviderChange: (provider: Provider) => void;
  onPrimaryChange: (model: string) => void;
  onTriageChange: (model: string) => void;
};

export function ModelRoutingSelector(props: Props) {
  if (props.mode === "local") {
    const models = props.discovery?.compatible ?? [];
    return (
      <section aria-labelledby="local-routing-title">
        <h3 className="font-semibold text-[var(--text)]" id="local-routing-title">Hugging Face recommendations</h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          {props.discoveryError ?? (props.discovery ? `Curated ${props.discovery.source} results for this hardware.` : "Checking this computer's probe results...")}
        </p>
        {models.length > 0 ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-medium text-[var(--text)]">
              Primary local model
              <select aria-label="Primary local model" className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] p-2" onChange={(event) => props.onPrimaryChange(event.target.value)} value={props.primaryModel}>
                <option value="">Select a model</option>
                {models.map((model) => <option key={model.catalog_id} value={model.catalog_id}>{model.filename} ({model.download_size_gb} GB)</option>)}
              </select>
            </label>
            <label className="text-sm font-medium text-[var(--text)]">
              Triage local model
              <select aria-label="Triage local model" className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] p-2" onChange={(event) => props.onTriageChange(event.target.value)} value={props.triageModel}>
                <option value="">Select a model</option>
                {models.map((model) => <option key={model.catalog_id} value={model.catalog_id}>{model.filename} ({model.download_size_gb} GB)</option>)}
              </select>
            </label>
          </div>
        ) : null}
      </section>
    );
  }
  if (props.mode !== "cloud") return null;
  const provider = props.providers.find((item) => item.id === props.providerId) ?? props.providers[0];
  const models = provider?.models ?? [];
  return (
    <section className="grid gap-3" aria-labelledby="cloud-routing-title">
      <h3 className="font-semibold text-[var(--text)]" id="cloud-routing-title">Provider-hosted model routing</h3>
      <label className="text-sm font-medium text-[var(--text)]">
        Cloud provider
        <select aria-label="Cloud provider" className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] p-2" onChange={(event) => {
          const next = props.providers.find((item) => item.id === event.target.value);
          if (next) props.onProviderChange(next);
        }} value={provider?.id ?? ""}>
          {props.providers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium text-[var(--text)]">
          Primary cloud model
          <select aria-label="Primary cloud model" className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] p-2" onChange={(event) => props.onPrimaryChange(event.target.value)} value={props.primaryModel}>
            {models.map((model) => <option key={model} value={model}>{model}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-[var(--text)]">
          Triage cloud model
          <select aria-label="Triage cloud model" className="mt-1 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] p-2" onChange={(event) => props.onTriageChange(event.target.value)} value={props.triageModel}>
            {models.map((model) => <option key={model} value={model}>{model}</option>)}
          </select>
        </label>
      </div>
      {provider ? <p className="text-xs text-[var(--text-muted)]">{provider.privacy} {provider.cost} Add secrets only with <code>hatch secrets set {provider.id}</code>.</p> : null}
    </section>
  );
}
