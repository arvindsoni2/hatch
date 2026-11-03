/**
 * Typed client for the Coach readiness coverage routes (P1).
 */
import { API_BASE } from "./api";

export type CoverageStatus = "covered" | "thin" | "gap";

export interface CoverageStory {
  story_id: string;
  title: string;
  score: number;
  has_metric: boolean;
}

export interface CompetencyCoverage {
  competency: string;
  status: CoverageStatus;
  action: "use" | "strengthen" | "draft";
  stories: CoverageStory[];
}

export interface CoverageMap {
  application_id: string;
  covered_count: number;
  thin_count: number;
  gap_count: number;
  competencies: CompetencyCoverage[];
}

export interface CoverageGap {
  competency: string;
  application_count: number;
}

export interface CoverageOverview {
  gaps: CoverageGap[];
}

export interface CompetencyOverride {
  original: string;
  replacement?: string | null;
  hidden: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const raw = await response.text().catch(() => response.statusText);
    let detail = raw || response.statusText;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // Keep the plain-text response.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function fetchCoverage(applicationId: string): Promise<CoverageMap> {
  return request<CoverageMap>(
    `/api/coach/readiness/coverage?application_id=${encodeURIComponent(applicationId)}`,
  );
}

export function fetchCoverageOverview(): Promise<CoverageOverview> {
  return request<CoverageOverview>("/api/coach/readiness/coverage/overview");
}

export function updateCoverageOverrides(
  applicationId: string,
  overrides: CompetencyOverride[],
): Promise<CoverageMap> {
  return request<CoverageMap>(
    `/api/coach/readiness/coverage/${encodeURIComponent(applicationId)}/overrides`,
    { method: "PUT", body: JSON.stringify({ overrides }) },
  );
}
