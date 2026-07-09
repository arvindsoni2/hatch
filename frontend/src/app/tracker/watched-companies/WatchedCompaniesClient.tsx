"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { ArrowLeft, Pause, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface CompanyWatchlistItem {
  id: string;
  company_name: string;
  company_website: string | null;
  careers_url: string;
  source_type: string;
  status: "active" | "paused" | "error";
  scan_frequency: "manual" | "daily" | "weekly";
  role_keywords: string[] | null;
  location_preferences: string[] | null;
  remote_preference: "any" | "remote" | "hybrid" | "onsite";
  min_match_score: number | null;
  last_scanned_at: string | null;
  last_successful_scan_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  last_scan_new_count: number;
}

interface WatchlistListResponse {
  items: CompanyWatchlistItem[];
  total: number;
}

interface ScanRun {
  status: string;
  new_count: number;
  duplicate_count: number;
  imported_count: number;
  error_message?: string | null;
}

interface FormState {
  companyName: string;
  companyWebsite: string;
  careersUrl: string;
  sourceType: string;
  scanFrequency: string;
  roleKeywords: string;
  locations: string;
  remotePreference: string;
  minMatchScore: string;
}

const initialForm: FormState = {
  companyName: "",
  companyWebsite: "",
  careersUrl: "",
  sourceType: "generic_careers_page",
  scanFrequency: "daily",
  roleKeywords: "",
  locations: "",
  remotePreference: "any",
  minMatchScore: "65",
};

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function WatchedCompaniesClient({
  initialItems,
  initialTotal,
}: {
  initialItems: CompanyWatchlistItem[];
  initialTotal: number;
}) {
  const [items, setItems] = useState(initialItems);
  const [total, setTotal] = useState(initialTotal);
  const [showForm, setShowForm] = useState(initialItems.length === 0);
  const [form, setForm] = useState<FormState>(initialForm);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const refresh = async () => {
    const response = await api<WatchlistListResponse>("/api/watchlist/companies");
    setItems(response.items);
    setTotal(response.total);
  };

  const save = () => {
    startTransition(async () => {
      setMessage(null);
      try {
        await api<CompanyWatchlistItem>("/api/watchlist/companies", {
          method: "POST",
          body: JSON.stringify({
            company_name: form.companyName,
            company_website: form.companyWebsite || null,
            careers_url: form.careersUrl,
            source_type: form.sourceType,
            scan_frequency: form.scanFrequency,
            role_keywords: splitCsv(form.roleKeywords),
            location_preferences: splitCsv(form.locations),
            remote_preference: form.remotePreference,
            min_match_score: form.minMatchScore ? Number(form.minMatchScore) : null,
          }),
        });
        setForm(initialForm);
        setShowForm(false);
        await refresh();
        setMessage("Watched company saved.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not save watched company.");
      }
    });
  };

  const scan = (item: CompanyWatchlistItem) => {
    startTransition(async () => {
      setMessage(null);
      try {
        const result = await api<ScanRun>(`/api/watchlist/companies/${item.id}/scan`, { method: "POST" });
        await refresh();
        setMessage(
          result.status === "completed"
            ? `Scan completed: ${result.new_count} new, ${result.duplicate_count} duplicate.`
            : `Scan failed: ${result.error_message ?? "Unknown error"}`,
        );
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not scan watched company.");
      }
    });
  };

  const setStatus = (item: CompanyWatchlistItem, status: "active" | "paused") => {
    startTransition(async () => {
      await api<CompanyWatchlistItem>(`/api/watchlist/companies/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await refresh();
    });
  };

  const remove = (item: CompanyWatchlistItem) => {
    startTransition(async () => {
      await api<void>(`/api/watchlist/companies/${item.id}`, { method: "DELETE" });
      await refresh();
      setMessage("Watched company deleted.");
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-[var(--accent)]" href="/tracker">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Applications
          </Link>
          <h1 className="text-[28px] font-semibold tracking-[-0.025em] text-[var(--text)]">Watched companies</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--text-muted)]">
            Scout-powered monitoring for explicit careers pages and job-board URLs.
          </p>
        </div>
        <Button disabled={isPending} onClick={() => setShowForm(true)} type="button">
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add company
        </Button>
      </header>

      <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
        <p className="text-sm text-[var(--text-muted)]">
          Only scan URLs you explicitly add. You are responsible for respecting website terms; Hatch will not bypass authentication or paywalls.
        </p>
      </section>

      {message ? (
        <p className="rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]" role="status">
          {message}
        </p>
      ) : null}

      {showForm ? (
        <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Company name
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.companyName} onChange={(event) => setForm((current) => ({ ...current, companyName: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Company website
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.companyWebsite} onChange={(event) => setForm((current) => ({ ...current, companyWebsite: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)] md:col-span-2">
              Careers/job-board URL
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.careersUrl} onChange={(event) => setForm((current) => ({ ...current, careersUrl: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Source type
              <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.sourceType} onChange={(event) => setForm((current) => ({ ...current, sourceType: event.target.value }))}>
                <option value="generic_careers_page">Generic careers page</option>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
                <option value="workable">Workable</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Scan frequency
              <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.scanFrequency} onChange={(event) => setForm((current) => ({ ...current, scanFrequency: event.target.value }))}>
                <option value="manual">Manual</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Role keywords
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.roleKeywords} onChange={(event) => setForm((current) => ({ ...current, roleKeywords: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Locations
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.locations} onChange={(event) => setForm((current) => ({ ...current, locations: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Remote preference
              <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.remotePreference} onChange={(event) => setForm((current) => ({ ...current, remotePreference: event.target.value }))}>
                <option value="any">Any</option>
                <option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">Onsite</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Min match score
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" type="number" min="0" max="100" value={form.minMatchScore} onChange={(event) => setForm((current) => ({ ...current, minMatchScore: event.target.value }))} />
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button disabled={isPending} onClick={() => setShowForm(false)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={isPending || !form.companyName || !form.careersUrl} onClick={save} type="button">Save company</Button>
          </div>
        </section>
      ) : null}

      {total === 0 ? (
        <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-8 text-center">
          <h2 className="text-lg font-semibold text-[var(--text)]">No watched companies yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-muted)]">Add companies you care about. Hatch will watch for new suitable roles.</p>
        </section>
      ) : (
        <section className="grid gap-3">
          {items.map((item) => (
            <article className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5" key={item.id}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold text-[var(--text)]">{item.company_name}</h2>
                    <span className="rounded-full bg-[var(--surface-2)] px-2 py-1 text-xs font-medium text-[var(--text-muted)]">{item.status}</span>
                    <span className="rounded-full bg-[var(--accent-soft)] px-2 py-1 text-xs font-medium text-[var(--accent)]">{item.scan_frequency}</span>
                  </div>
                  <p className="mt-1 truncate text-sm text-[var(--text-muted)]">{item.careers_url}</p>
                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                    <div><dt className="font-semibold text-[var(--text)]">Last scan</dt><dd className="text-[var(--text-muted)]">{formatDate(item.last_scanned_at)}</dd></div>
                    <div><dt className="font-semibold text-[var(--text)]">New roles</dt><dd className="text-[var(--text-muted)]">{item.last_scan_new_count}</dd></div>
                    <div><dt className="font-semibold text-[var(--text)]">Source</dt><dd className="text-[var(--text-muted)]">{item.source_type.replace(/_/g, " ")}</dd></div>
                  </dl>
                  {item.last_error ? <p className="mt-3 text-sm text-[var(--danger)]">{item.last_error}</p> : null}
                </div>
                <div className="grid gap-2 sm:grid-cols-3 lg:min-w-[340px]">
                  <Button aria-label={`Run scan for ${item.company_name}`} disabled={isPending || item.status === "paused"} onClick={() => scan(item)} type="button" variant="outline">
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Scan
                  </Button>
                  <Button aria-label={`${item.status === "paused" ? "Resume" : "Pause"} ${item.company_name}`} disabled={isPending} onClick={() => setStatus(item, item.status === "paused" ? "active" : "paused")} type="button" variant="secondary">
                    {item.status === "paused" ? <Play className="h-4 w-4" aria-hidden="true" /> : <Pause className="h-4 w-4" aria-hidden="true" />}
                    {item.status === "paused" ? "Resume" : "Pause"}
                  </Button>
                  <Button aria-label={`Delete ${item.company_name}`} disabled={isPending} onClick={() => remove(item)} type="button" variant="ghost">
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    Delete
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
