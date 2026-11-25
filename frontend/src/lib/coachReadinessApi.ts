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

export interface CoverageOverviewSignal {
  display: string;
  fingerprint: string;
  asked_rounds: number;
  low_rating_debriefs: number;
  last_at: string | null;
}

export interface CoverageOverview {
  gaps: CoverageGap[];
  signals: CoverageOverviewSignal[];
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
  questions_added: number;
  proposals?: DebriefProposal[];
}

export interface SaveDebriefInput {
  expected_version: number;
  // Null saves a notes-only draft.
  overall: number | null;
  expectation?: "yes" | "unsure" | "no" | null;
  questions?: DebriefQuestion[];
  went_well?: string | null;
  do_differently?: string | null;
  notes_text?: string | null;
}

export interface DebriefProposal {
  id: string;
  kind: "question_bank" | "story_use";
  questions: string[];
  story_id: string | null;
  story_title: string | null;
  accepted: boolean;
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

let displayTimeZonePromise: Promise<string | null> | null = null;

export type MemoryKind =
  | "dismissed_patterns"
  | "focus_areas_and_plans"
  | "briefs"
  | "debriefs"
  | "explain_tips"
  | "competency_overrides"
  | "job_competencies";

export interface MemoryKindSummary {
  kind: MemoryKind;
  count: number;
  last_updated: string | null;
}

export interface MemoryInventory {
  kinds: MemoryKindSummary[];
}

export function fetchMemoryInventory(): Promise<MemoryInventory> {
  return request<MemoryInventory>("/api/coach/readiness/memory");
}

export function deleteMemoryKind(
  kind: MemoryKind,
  clearRoundQuestions = false,
): Promise<{ kind: MemoryKind; removed: number }> {
  const query = clearRoundQuestions ? "?clear_round_questions=true" : "";
  return request(`/api/coach/readiness/memory/${encodeURIComponent(kind)}${query}`, {
    method: "DELETE",
  });
}

export function deleteAllReadinessData(): Promise<{ removed: Record<MemoryKind, number> }> {
  return request("/api/coach/readiness/memory", { method: "DELETE" });
}

export function fetchDisplayTimeZone(): Promise<string | null> {
  if (displayTimeZonePromise === null) {
    displayTimeZonePromise = request<{ display_timezone: string | null }>(
      "/api/coach/readiness/display-timezone",
    )
      .then((response) => response.display_timezone)
      .catch(() => null);
  }
  return displayTimeZonePromise;
}

export type PatternKind = "focus" | "strength" | "mixed" | "forming";
export type PatternTrendLabel =
  | "improving"
  | "easier_difficulty"
  | "getting_weaker"
  | "harder_difficulty";

export interface PatternGroup {
  role_family: string;
  interview_type: string;
  contract_version: string;
}

export interface PatternSupport {
  session_id: string;
  completed_at: string;
  level: string;
  difficulty: string | null;
  role_level: string | null;
}

export interface Pattern {
  fingerprint: string;
  group: PatternGroup;
  dimension: string;
  kind: PatternKind;
  trend: string;
  trend_label: PatternTrendLabel | null;
  supporting: PatternSupport[];
  stale: boolean;
  dismissed: boolean;
  seen_again: boolean;
}

export interface PatternGroupSection {
  role_family: string;
  interview_type: string;
  contract_version: string;
  session_count: number;
  patterns: Pattern[];
}

export interface PatternList {
  groups: PatternGroupSection[];
  include_stale: boolean;
}

export interface PatternWhyExcerpt {
  session_id: string;
  completed_at: string;
  text: string;
}

export interface PatternWhy {
  pattern: Pattern;
  excerpts: PatternWhyExcerpt[];
}

export function fetchPatterns(includeStale = true): Promise<PatternList> {
  return request<PatternList>(
    `/api/coach/readiness/patterns?include_stale=${includeStale ? "true" : "false"}`,
  );
}

export function fetchPatternWhy(fingerprint: string): Promise<PatternWhy> {
  return request<PatternWhy>(
    `/api/coach/readiness/patterns/${encodeURIComponent(fingerprint)}/why`,
  );
}

export function dismissPattern(fingerprint: string): Promise<void> {
  return request(
    `/api/coach/readiness/patterns/${encodeURIComponent(fingerprint)}/dismiss`,
    { method: "POST" },
  );
}

export function undoPatternDismissal(fingerprint: string): Promise<void> {
  return request(
    `/api/coach/readiness/patterns/${encodeURIComponent(fingerprint)}/dismiss`,
    { method: "DELETE" },
  );
}

export interface FocusGroup {
  role_family: string;
  interview_type: string;
  contract_version: string;
}

export interface FocusCriterion {
  kind: "level" | "practice";
  label: string;
  status: "not_started" | "in_progress" | "met" | "no_evidence_yet";
  completed: number;
  target: number;
}

export interface FocusArea {
  id: string;
  version: number;
  status: "active" | "paused" | "achieved" | "archived";
  active_slot: number | null;
  title: string;
  dimension: string;
  group: FocusGroup | null;
  application_id: string | null;
  criteria: FocusCriterion[];
  every_criterion_met: boolean;
  created_at: string;
}

export interface FocusAreaList {
  items: FocusArea[];
  active_count: number;
  active_limit: number;
}

export interface PlanItem {
  id: string;
  type: "practice_session" | "story_work" | "review_answer";
  title: string;
  minutes: number;
  status: "todo" | "done" | "skipped";
  group: FocusGroup | null;
  difficulty: string | null;
  focus_area_ids: string[];
  due_at: string | null;
  story_competency: string | null;
  question_id: string | null;
  auto: boolean;
  completed_at: string | null;
}

export interface PracticePlan {
  id: string;
  version: number;
  status: "draft" | "active" | "completed" | "superseded" | "expired" | "discarded";
  minutes: number;
  target_round_id: string | null;
  items: PlanItem[];
  unallocated_minutes: number;
  done_count: number;
  total_count: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface PlanList {
  active: PracticePlan | null;
  draft: PracticePlan | null;
}

export function fetchFocusAreas(): Promise<FocusAreaList> {
  return request<FocusAreaList>("/api/coach/readiness/focus-areas");
}

export function createFocusArea(input: {
  title: string;
  dimension: string;
  group?: FocusGroup | null;
  application_id?: string | null;
  criteria: { kind: "level" | "practice"; count?: number | null }[];
}): Promise<FocusArea> {
  return request<FocusArea>("/api/coach/readiness/focus-areas", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function patchFocusArea(
  id: string,
  patch: {
    expected_version: number;
    title?: string;
    status?: FocusArea["status"];
  },
): Promise<FocusArea> {
  return request<FocusArea>(`/api/coach/readiness/focus-areas/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function fetchPlans(): Promise<PlanList> {
  return request<PlanList>("/api/coach/readiness/plans");
}

export function createPlan(input: {
  minutes: number;
  target_round_id?: string | null;
}): Promise<PracticePlan> {
  return request<PracticePlan>("/api/coach/readiness/plans", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function startPlan(id: string): Promise<PracticePlan> {
  return request<PracticePlan>(
    `/api/coach/readiness/plans/${encodeURIComponent(id)}/start`,
    { method: "POST" },
  );
}

export function patchPlanItem(
  planId: string,
  itemId: string,
  action: "done" | "skipped" | "todo",
  expectedVersion: number,
): Promise<PracticePlan> {
  return request<PracticePlan>(
    `/api/coach/readiness/plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ action, expected_version: expectedVersion }),
    },
  );
}

export interface PatternTipsResponse {
  tips?: string[];
  operation_id?: string | null;
  status: string;
  reason?: string;
}

export function requestPatternTips(fingerprint: string): Promise<PatternTipsResponse> {
  return request<PatternTipsResponse>(
    `/api/coach/readiness/patterns/${encodeURIComponent(fingerprint)}/tips`,
    { method: "POST" },
  );
}

export function fetchGenerationOperation(operationId: string): Promise<PatternTipsResponse> {
  return request<PatternTipsResponse>(
    `/api/coach/readiness/operations/${encodeURIComponent(operationId)}`,
  );
}

export interface BriefEnhancement {
  state: "none" | "enhancing" | "current" | "outdated" | "unavailable";
  fingerprint: string;
  operation_id: string | null;
  model_identity: string | null;
}

export interface InterviewBriefData {
  round_id: string;
  state: "active" | "archived";
  header: {
    company: string;
    role: string;
    round_type: string;
    starts_at: string | null;
    display_timezone: string | null;
    duration_minutes: number | null;
    interviewer: string | null;
    location: string | null;
  };
  likely_questions: { id: string; text: string; source: string }[];
  stories: {
    story_id: string; title: string; competencies: string[];
    score: number; has_metric: boolean; talking_point: string | null;
  }[];
  watch_outs: {
    fingerprint: string; dimension: string; source: string; sentence: string | null;
  }[];
  gaps: { competency: string; action: string }[];
  ask_them: string[];
  enhancement: BriefEnhancement;
}

export function extractDebriefNotes(roundId: string): Promise<{ questions: string[] }> {
  return request<{ questions: string[] }>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/debrief/extract`,
    { method: "POST" },
  );
}

export function acceptDebriefProposal(
  roundId: string,
  proposalId: string,
): Promise<DebriefRead> {
  return request<DebriefRead>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/debrief/proposals/${encodeURIComponent(proposalId)}/accept`,
    { method: "POST" },
  );
}

export function fetchInterviewBrief(roundId: string): Promise<InterviewBriefData> {
  return request<InterviewBriefData>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/brief`,
  );
}

export function retryInterviewBriefTips(roundId: string): Promise<InterviewBriefData> {
  return request<InterviewBriefData>(
    `/api/coach/readiness/rounds/${encodeURIComponent(roundId)}/brief/tips`,
    { method: "POST" },
  );
}
