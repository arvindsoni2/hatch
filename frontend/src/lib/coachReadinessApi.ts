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

export class CoachReadinessError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "CoachReadinessError";
    this.status = status;
  }
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
    throw new CoachReadinessError(detail, response.status);
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

export type DebriefStatus = "due" | "draft" | "saved" | "skipped";

export interface DebriefQuestion {
  id: string;
  text: string;
  source_ref: { kind: "question_bank_item"; id: string } | null;
  asked: boolean;
  rating: number | null;
  story_id: string | null;
  note: string | null;
}

export interface DebriefRead {
  round_id: string;
  application_id: string;
  round_status: string | null;
  scheduled_at: string | null;
  duration_minutes: number | null;
  status: DebriefStatus;
  version: number;
  overall: number | null;
  expectation: "yes" | "unsure" | "no" | null;
  questions: DebriefQuestion[];
  went_well: string | null;
  do_differently: string | null;
  notes_text: string | null;
}

export interface SaveDebriefInput {
  expected_version: number;
  overall: number;
  expectation?: "yes" | "unsure" | "no" | null;
  questions?: DebriefQuestion[];
  went_well?: string | null;
  do_differently?: string | null;
  notes_text?: string | null;
}

export interface ReadinessNextAction {
  application_id: string;
  round_id: string;
  action: string;
  reason: string;
  urgency: string;
  kind: string;
}

export function fetchDebrief(roundId: string): Promise<DebriefRead> {
  return request<DebriefRead>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/debrief`,
  );
}

export function saveDebrief(
  roundId: string,
  input: SaveDebriefInput,
): Promise<DebriefRead> {
  return request<DebriefRead>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/debrief`,
    { method: "PUT", body: JSON.stringify(input) },
  );
}

export function skipDebrief(
  roundId: string,
  expectedVersion: number,
): Promise<DebriefRead> {
  return request<DebriefRead>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/debrief/skip`,
    {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
  );
}

export function fetchReadinessNextActions(): Promise<ReadinessNextAction[]> {
  return request<ReadinessNextAction[]>("/api/coach/readiness/next-actions");
}
