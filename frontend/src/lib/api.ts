/**
 * Hatch API client — typed wrappers around the FastAPI backend.
 */

// Server-side (SSR/RSC) calls the backend directly using IPv4 to avoid
// browser-style localhost→IPv6 resolution. Client-side uses relative paths
// so the browser's request goes to the same origin (proxied by Next.js rewrites).
export const API_BASE =
  typeof window === "undefined"
    ? (process.env.API_URL ?? "http://127.0.0.1:8000")
    : "";

export interface AppLockStatus {
  enabled: boolean;
  configured_source: "env" | "database" | "none";
  is_configured: boolean;
  is_unlocked: boolean;
  last_unlocked_at?: string | null;
  last_password_changed_at?: string | null;
  failed_attempt_count?: number;
  retry_after_seconds?: number;
  password_policy?: PasswordPolicy;
  onboarding: OnboardingState;
}

export type OnboardingStatus = "not_started" | "in_progress" | "finalization_pending" | "complete";

export interface OnboardingState {
  status: OnboardingStatus;
  last_completed_step: string | null;
}

export interface PasswordPolicy {
  min_length: number;
  max_length: number;
  require_letter: boolean;
  require_number: boolean;
  require_symbol?: boolean;
  reject_edge_whitespace: boolean;
}

export const APP_LOCK_QUERY_KEY = ["app-lock-status"] as const;

export interface ProfileSummary {
  identity: { name: string; title: string; email?: string; phone?: string };
  target_roles: string[];
  skills: string[];
  unverified_skills: string[];
  domains: string[];
  certifications: string[];
  education: Array<Record<string, unknown>>;
  proof_points: Array<Record<string, unknown>>;
  master_cv: {
    status: "present" | "missing" | "invalid";
    path: string;
    last_validated_at: string | null;
    last_updated_at: string | null;
  };
  warnings: Array<{ code: string; message: string }>;
}

export interface BackendCapabilityStatus {
  configured: boolean;
  installed: boolean;
  available: boolean;
  reason: string | null;
  enable_command: string | null;
}

export interface SystemCapabilities {
  backend_profile: "core" | "browser" | "local-embeddings" | "full" | string;
  ai_mode: string;
  capabilities: {
    core_backend: BackendCapabilityStatus;
    browser_automation: BackendCapabilityStatus;
    local_embeddings: BackendCapabilityStatus;
    perception_advanced_coach: BackendCapabilityStatus;
  };
}

// ──────────────────────── Types ────────────────────────

export interface Job {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  rate_text: string | null;
  rate_min: number | null;
  rate_max: number | null;
  currency: string;
  ir35_status: "inside" | "outside" | "unknown" | null;
  legal_fields?: Record<string, string>;
  contract_length: string | null;
  description: string | null;
  url: string;
  source: string;
  posted_at: string | null;
  scraped_at: string;
  skills: string[] | null;
  is_active: boolean;
  sync_status: string;
  created_at: string;
  updated_at: string;
  // V2 fields
  employment_type: string | null;
  working_pattern: string | null;
  match_score: number | null;
  match_reasons: string[] | null;
  // Per-dimension scores + transparency (from job_scores join)
  skill_match: number | null;
  experience_match: number | null;
  rate_match: number | null;
  location_match: number | null;
  scoring_method: "local" | "llm" | "semantic" | null;  // "local"=quick estimate, "llm"/"semantic"=AI assessment
  score_reasoning: string | null;
  keyword_matches: string[] | null;
  keyword_misses: string[] | null;
  fit_reasoning: string | null;
  score_strengths: string[] | null;
  score_gaps: string[] | null;
  // Ghost detection fields
  ghost_score: number | null;
  ghost_verdict: string | null;
  ghost_signals: unknown[] | null;
  ghost_analysed_at: string | null;
  opportunity_score?: number | null;
  outcome_adjustment?: number | null;
  outcome_confidence?: "insufficient" | "low" | "medium" | "high" | null;
  outcome_sample_size?: number | null;
  outcome_reasons?: OutcomeReason[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export interface ScrapeResult {
  source: string;
  jobs_found: number;
  jobs_new: number;
  errors: number;
  duration_seconds: number;
}

export interface StatsResponse {
  total_jobs: number;
  by_source: Record<string, number>;
  by_ir35: Record<string, number>;
  new_today: number;
  new_this_week: number;
}

export interface JobFilters {
  search?: string;
  legal_fields?: Record<string, string>;
  source?: string;
  min_rate?: number;
  max_rate?: number;
  // V2 filters
  job_type?: string;
  min_match_score?: number;
  posted_after?: string;
  // Ghost filter
  hide_ghosts?: boolean;
  sort_by?: "newest" | "fit" | "opportunity" | "rate";
}

// ──────────────────────── Helpers ────────────────────────

export class ApiError<T = unknown> extends Error {
  readonly status: number;
  readonly data: T | null;
  readonly code: string | null;

  constructor(message: string, status: number, data: T | null, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.code = code;
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const isFormData = options?.body instanceof FormData;
  const res = await fetch(url, {
    headers: isFormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const raw = await res.text().catch(() => res.statusText);
    let detail = raw || res.statusText;
    let data: unknown = raw || null;
    let code: string | null = null;
    try {
      const parsed = JSON.parse(raw) as {
        detail?: unknown;
        error?: { code?: unknown; message?: unknown };
      };
      data = parsed;
      if (typeof parsed.detail === "string") detail = parsed.detail;
      if (typeof parsed.error?.message === "string") detail = parsed.error.message;
      if (typeof parsed.error?.code === "string") code = parsed.error.code;
    } catch {
      // Preserve plain-text API errors as-is.
    }
    throw new ApiError(detail, res.status, data, code);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const getAppLockStatus = () =>
  apiFetch<AppLockStatus>("/api/app-lock/status");

export const setupAppLock = (password: string) =>
  apiFetch<{ unlocked: boolean; onboarding: OnboardingState }>("/api/app-lock/setup", {
    method: "POST",
    body: JSON.stringify({ password }),
  });

export const updateOnboardingProgress = (stepId: string) =>
  apiFetch<{ onboarding: OnboardingState }>("/api/setup/onboarding/progress", {
    method: "POST",
    body: JSON.stringify({ step_id: stepId }),
  });

export const finalizeOnboarding = (finalizationId: string, profile: Record<string, unknown>) =>
  apiFetch<{ onboarding: OnboardingState }>("/api/setup/onboarding/finalize", {
    method: "POST",
    body: JSON.stringify({ finalization_id: finalizationId, profile }),
  });

export const unlockApp = (password: string) =>
  apiFetch<{ unlocked: boolean }>("/api/app-lock/unlock", {
    method: "POST",
    body: JSON.stringify({ password }),
  });

export const lockApp = () =>
  apiFetch<{ locked: boolean }>("/api/app-lock/lock", { method: "POST" });

export const changeAppLockPassword = (currentPassword: string, newPassword: string) =>
  apiFetch<{ changed: boolean }>("/api/app-lock/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

export const fetchProfileSummary = () =>
  apiFetch<ProfileSummary>("/api/v2/profile/summary");

export const getSystemCapabilities = () =>
  apiFetch<SystemCapabilities>("/api/system/capabilities", { cache: "no-store" });

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  const qs = entries
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return `?${qs}`;
}

// ──────────────────────── API Functions ────────────────────────

/**
 * Fetch a paginated list of jobs with optional filters.
 */
export async function fetchJobs(
  filters: JobFilters = {},
  page = 0,
  limit = 50,
): Promise<PaginatedResponse<Job>> {
  const params: Record<string, string | number | boolean | undefined> = {
    skip: page * limit,
    limit,
    ...(filters.search ? { search: filters.search } : {}),
    ...(filters.legal_fields?.ir35_status ? { ir35_status: filters.legal_fields.ir35_status } : {}),
    ...(filters.source ? { source: filters.source } : {}),
    ...(filters.min_rate !== undefined ? { min_rate: filters.min_rate } : {}),
    ...(filters.max_rate !== undefined ? { max_rate: filters.max_rate } : {}),
    ...(filters.job_type === "permanent" ? { employment_type: "permanent" } : {}),
    ...(filters.job_type === "temporary" ? { employment_type: "contract" } : {}),
    ...(filters.job_type === "hybrid" ? { working_pattern: "hybrid" } : {}),
    ...(filters.job_type === "remote" ? { working_pattern: "remote" } : {}),
    ...(filters.min_match_score !== undefined ? { min_match_score: filters.min_match_score } : {}),
    ...(filters.posted_after ? { posted_after: filters.posted_after } : {}),
    ...(filters.hide_ghosts !== undefined ? { hide_ghosts: filters.hide_ghosts } : {}),
    ...(filters.sort_by ? { sort_by: filters.sort_by } : {}),
  };
  const qs = buildQueryString(params);
  return apiFetch<PaginatedResponse<Job>>(`/api/jobs${qs}`);
}

/**
 * Fetch a single job by ID.
 */
export async function fetchJob(id: string): Promise<Job> {
  return apiFetch<Job>(`/api/jobs/${id}`);
}

/**
 * Fetch dashboard statistics.
 */
export async function fetchStats(): Promise<StatsResponse> {
  return apiFetch<StatsResponse>("/api/jobs/stats");
}

/**
 * Trigger all scrapers (or a specific one if source is provided).
 */
export async function triggerScrape(source?: string): Promise<ScrapeResult[]> {
  const qs = source ? `?source=${encodeURIComponent(source)}` : "";
  return apiFetch<ScrapeResult[]>(`/api/jobs/scrape${qs}`, { method: "POST" });
}

export interface OutcomeReason {
  signal: string;
  value: string;
  direction: "positive" | "negative";
  contribution: number;
  segment_rate: number;
  baseline_rate: number;
  sample_size: number;
  message: string;
}

export interface VariantRecommendation {
  document_type: "cv" | "cover_letter";
  recommended_variant: string;
  reason: string;
  sample_size: number;
  confidence: string;
}

export interface OutcomeLearningSummary {
  enabled: boolean;
  model_version: string;
  confidence: "insufficient" | "low" | "medium" | "high";
  resolved_applications: number;
  effective_sample_size: number;
  positive_responses: number;
  global_response_rate: number;
  minimum_required: number;
  additional_required: number;
  learning_since: string | null;
  top_positive_signals: OutcomeReason[];
  top_negative_signals: OutcomeReason[];
  variant_recommendations: VariantRecommendation[];
  variant_performance: Record<string, Array<Record<string, string | number>>>;
  last_recomputed_at: string | null;
}

export async function fetchOutcomeLearningSummary(): Promise<OutcomeLearningSummary> {
  return apiFetch<OutcomeLearningSummary>("/api/outcome-learning/summary", { cache: "no-store" });
}

export async function recomputeOutcomeLearning(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>("/api/outcome-learning/recompute", { method: "POST" });
}

export async function backfillOutcomeLearning(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>("/api/outcome-learning/backfill", { method: "POST" });
}

export async function resetOutcomeLearning(): Promise<{ learning_since: string }> {
  return apiFetch<{ learning_since: string }>("/api/outcome-learning/reset", {
    method: "POST",
    body: JSON.stringify({ confirmation: "RESET" }),
  });
}

/**
 * Soft-delete a job posting.
 */
export async function deleteJob(id: string): Promise<void> {
  await apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" });
}

// ─────────────────── Phase 2 — Tracker Types ───────────────────

export type ApplicationStatus =
  | "discovered" | "shortlisted" | "applied" | "interview"
  | "offered" | "accepted" | "rejected" | "withdrawn" | "declined"
  | "parked" | "ready" | "approved" | "preparing" | "ready_to_apply" | "saved";

export interface JobImportDraft {
  source_url: string; normalized_url?: string | null; final_url?: string | null;
  title?: string | null; company?: string | null; location?: string | null;
  rate_text?: string | null; description?: string | null; apply_url?: string | null;
}
export interface JobImportPreview extends JobImportDraft {
  confidence: "high" | "medium" | "low"; extraction_method: "direct" | "firecrawl" | "manual_required";
  warnings: string[]; duplicate: boolean; existing_job_id?: string | null; existing_application_id?: string | null;
}
export const previewJobUrl = (url: string) => apiFetch<JobImportPreview>("/api/jobs/import-url/preview", { method: "POST", body: JSON.stringify({ url }) });
export const saveImportedJob = (draft: JobImportDraft, next_action: "save_as_job_only" | "save_to_applications" | "save_and_tailor") =>
  apiFetch<{ job_id: string; application_id: string | null; next_action: string; stage: string; warnings: string[] }>("/api/jobs/import-url/save", {
    method: "POST", body: JSON.stringify({ draft, next_action }),
  });

export type Priority = "low" | "normal" | "high" | "urgent";

export interface InterviewRound {
  id: string;
  application_id: string;
  round_number: number;
  type: string;
  scheduled_at: string | null;
  duration_minutes: number | null;
  location: string | null;
  interviewer_name: string | null;
  feedback: string | null;
  prep_notes: string | null;
  questions_asked: string[] | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface FollowUp {
  id: string;
  application_id: string;
  due_date: string;
  type: string;
  note: string | null;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface ActivityLogEntry {
  id: number;
  application_id: string;
  action: string;
  old_value: string | null;
  new_value: string | null;
  detail: string | null;
  created_at: string;
}

export interface ApplicationListItem {
  id: string;
  job_id: string | null;
  status: ApplicationStatus;
  priority: Priority;
  applied_date: string | null;
  recruiter_name: string | null;
  agency_name: string | null;
  salary_offered: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  job_title: string | null;
  job_company: string | null;
  job_location: string | null;
  job_rate_text: string | null;
  job_rate_min: number | null;
  job_source: string | null;
  job_url: string | null;
  // Agentic fields
  agent_score: number | null;
  latest_cv_ats_score?: number | null;
  agent_created: boolean;
  approval_status: string | null;
}

export interface ApplicationJob {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  rate_text: string | null;
  rate_min: number | null;
  rate_max: number | null;
  url: string;
  source: string;
  ir35_status: string | null;
}

export interface Application {
  id: string;
  job_id: string | null;
  status: ApplicationStatus;
  priority: Priority;
  applied_date: string | null;
  cv_version: string | null;
  cover_letter_version: string | null;
  notes: string | null;
  recruiter_name: string | null;
  recruiter_email: string | null;
  recruiter_phone: string | null;
  agency_name: string | null;
  salary_offered: number | null;
  rejection_reason: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  interviews: InterviewRound[];
  follow_ups: FollowUp[];
  activity: ActivityLogEntry[];
  agent_created: boolean;
  approval_status: string | null;
  job: ApplicationJob | null;
}

export interface KanbanStats {
  active_count: number;
  applied_count: number;
  response_rate: number;
  overdue_count: number;
}

export interface KanbanResponse {
  columns: Record<string, ApplicationListItem[]>;
  stats: KanbanStats;
}

export interface FunnelStage {
  status: string;
  count: number;
  conversion_rate: number | null;
}

export interface AnalyticsDashboard {
  stats: KanbanStats;
  funnel: { stages: FunnelStage[]; total_tracked: number };
  trends: { weeks: Array<{ week_start: string; new_applications: number; reached_interview: number }> };
  sources: Array<{ source: string; total: number; applied: number; interview_rate: number }>;
  avg_days_to_interview: number | null;
  avg_days_to_offer: number | null;
}

// ─────────────────── Phase 2 — API Functions ───────────────────

export async function fetchKanban(): Promise<KanbanResponse> {
  return apiFetch<KanbanResponse>("/api/applications/kanban");
}

export async function fetchApplications(
  filters: { status?: string; priority?: string; search?: string } = {},
  skip = 0,
  limit = 50,
): Promise<PaginatedResponse<ApplicationListItem>> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.search) params.set("search", filters.search);
  params.set("skip", String(skip));
  params.set("limit", String(limit));
  return apiFetch<PaginatedResponse<ApplicationListItem>>(`/api/applications?${params}`);
}

export async function fetchApplication(id: string): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${id}`);
}

export async function createApplication(data: {
  job_id?: string;
  status?: string;
  priority?: string;
  notes?: string;
  agency_name?: string;
}): Promise<Application> {
  return apiFetch<Application>("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function createManualApplication(data: {
  job_title: string;
  company_name?: string | null;
  job_url?: string | null;
  job_description?: string | null;
  location?: string | null;
  status?: ApplicationStatus;
  applied_date?: string | null;
  notes?: string | null;
  recruiter_name?: string | null;
  recruiter_email?: string | null;
  agency_name?: string | null;
  prepare_with_coach?: boolean;
}): Promise<Application> {
  return apiFetch<Application>("/api/applications/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateApplicationStatus(
  id: string,
  status: ApplicationStatus,
  notes?: string,
): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, notes }),
  });
}

export async function updateApplication(
  id: string,
  data: Partial<Application>,
): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function addApplicationNote(id: string, note: string): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${id}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
}

export async function trackFromJob(jobId: string): Promise<Application> {
  return apiFetch<Application>(`/api/applications/from-job/${jobId}`, {
    method: "POST",
  });
}

export async function deleteApplication(id: string): Promise<void> {
  await apiFetch<{ status: string }>(`/api/applications/${id}`, { method: "DELETE" });
}

export async function createInterview(data: {
  application_id: string;
  round_number?: number;
  type?: string;
  scheduled_at?: string;
  duration_minutes?: number;
  location?: string;
  interviewer_name?: string;
  prep_notes?: string;
}): Promise<InterviewRound> {
  return apiFetch<InterviewRound>("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateInterview(
  id: string,
  data: Partial<InterviewRound>,
): Promise<InterviewRound> {
  return apiFetch<InterviewRound>(`/api/interviews/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function completeInterview(
  id: string,
  feedback?: string,
): Promise<InterviewRound> {
  return apiFetch<InterviewRound>(`/api/interviews/${id}/complete`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
  });
}

export async function deleteInterview(id: string): Promise<void> {
  await apiFetch<{ status: string }>(`/api/interviews/${id}`, { method: "DELETE" });
}

export async function getUpcomingInterviews(days = 30): Promise<InterviewRound[]> {
  return apiFetch<InterviewRound[]>(`/api/interviews/upcoming?days=${days}`);
}

export async function createFollowUp(data: {
  application_id: string;
  due_date: string;
  type?: string;
  note?: string;
}): Promise<FollowUp> {
  return apiFetch<FollowUp>("/api/interviews/follow-ups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function completeFollowUp(id: string): Promise<FollowUp> {
  return apiFetch<FollowUp>(`/api/interviews/follow-ups/${id}/complete`, {
    method: "PATCH",
  });
}

export async function getOverdueFollowUps(): Promise<FollowUp[]> {
  return apiFetch<FollowUp[]>("/api/interviews/follow-ups/overdue");
}

export async function fetchAnalyticsDashboard(): Promise<AnalyticsDashboard> {
  return apiFetch<AnalyticsDashboard>("/api/analytics/dashboard");
}

export interface JobSourceCount {
  source: string;
  total: number;
  applied: number;
  interview_rate: number;
}

export async function fetchJobSources(): Promise<JobSourceCount[]> {
  return apiFetch<JobSourceCount[]>("/api/analytics/sources");
}

// ─────────────────── Phase 3 — Tailor Types ───────────────────

export interface ContractDetails {
  rate_range: string | null;
  ir35_status: string | null;
  duration: string | null;
  location: string | null;
  remote_policy: string | null;
  start_date: string | null;
}

export interface ATSKeywords {
  technical: string[];
  methodologies: string[];
  soft_skills: string[];
  domain: string[];
  certifications: string[];
}

export interface JDAnalysisResult {
  role_title: string;
  seniority_level: string | null;
  contract_details: ContractDetails;
  requirements: { must_have: string[]; nice_to_have: string[]; years_experience: string | null };
  responsibilities: string[];
  ats_keywords: ATSKeywords;
  tone_analysis: { formality: string; emphasis: string; red_flags: string[] };
  raw_text_length: number | null;
}

export interface SkillMatch {
  matched: string[];
  missing: string[];
  match_pct: number;
  domain_match: boolean;
  recommendations: string[];
}

export interface JDAnalysisResponse {
  job_id: string;
  analysis: JDAnalysisResult;
  skill_match: SkillMatch | null;
}

export interface TailoredExperience {
  role: string;
  company: string;
  period: string;
  achievements: string[];
}

export interface TailoredEducation {
  qualification: string;
  institution: string;
  year: string;
  field?: string;
  location?: string;
  details?: string[];
}

export interface TailoredCV {
  summary: string;
  skills: Array<{ category?: string; display_name?: string; items?: string[] }>;
  experience: TailoredExperience[];
  education: TailoredEducation[];
  certifications: string[];
  ats_keywords_embedded: string[];
  tailoring_notes: string;
  structural_warnings: string[];
  validation_status: "passed" | "repaired" | "failed";
  blocking_issues: string[];
  fabrication_warnings: string[];
}

export interface CoverLetter {
  subject_line: string;
  greeting: string;
  body_paragraphs: string[];
  sign_off: string;
  word_count: number;
  key_keywords_used: string[];
}

export interface KeywordMatch {
  keyword: string;
  found: boolean;
  context: string | null;
}

export interface ATSScore {
  overall_score: number;
  algorithmic_score: number | null;
  semantic_score: number | null;
  keyword_matches: KeywordMatch[];
  format_warnings: string[];
  missing_critical: string[];
  improvement_suggestions: string[];
}

export interface GeneratedDocument {
  id: string;
  application_id: string;
  document_type: string;
  version: number;
  file_path: string | null;
  file_size_bytes: number | null;
  ats_score: number | null;
  variant_label: string | null;
  status: string;
  created_at: string;
}

export interface GeneratedDocumentAsset {
  id: string;
  application_id: string;
  package_id: string;
  source_document_id: string;
  kind: "cv" | "cover_letter";
  format: "pdf";
  generation_status: string;
  error_message: string | null;
  created_at: string;
}

export interface TailorResultBundle {
  application_id: string;
  cv_document_id: string | null;
  cl_document_id: string | null;
  ats_score: ATSScore | null;
  analysis: JDAnalysisResult | null;
  skill_match: SkillMatch | null;
}

export interface TailorProgressEvent {
  stage: string;
  pct: number;
  message: string;
}

export interface ResumeTemplate {
  id: string;
  name: string;
  description: string;
  best_for: string[];
  layout: string;
  content_density: "standard" | "detailed" | "compact" | "transferable";
  default_page_target: ResumeDesignSettings["page_target"];
  default_section_order: ResumeDesignSettings["section_order_preset"];
  ats_safety_notes: string[];
}

export interface ResumeDesignSettings {
  template_id: string;
  page_target: "one_page" | "two_page" | "auto";
  density: "compact" | "standard" | "detailed" | "transferable";
  section_order_preset: "standard" | "skills_first" | "project_led" | "leadership_first" | "compact" | "career_switcher";
  accent_color: "navy" | "slate" | "teal" | "indigo" | "emerald" | "charcoal";
  font_family: "aptos" | "calibri" | "arial" | "georgia";
}

export interface ResumeTemplateResponse {
  templates: ResumeTemplate[];
  default_template_id: string;
  default_design_settings: ResumeDesignSettings;
  controls: Record<string, string[]>;
  warnings?: string[];
}

export interface TailoringReview {
  available?: boolean;
  message?: string;
  application_id: string;
  match_summary: { role_title: string; overall_match: number; summary: string };
  ats_keyword_coverage: { covered: string[]; missing: string[]; coverage_pct: number };
  evidence_used: Array<{ requirement: string; evidence: string; confidence: string }>;
  weak_or_unsupported_requirements: Array<{ requirement: string; reason: string; suggestion: string }>;
  warnings: Array<{ severity: string; message: string }>;
  documents: Array<{ id: string; type: string; template_id: string }>;
  template_id: string;
  variant: string;
  created_at: string;
  quality_gate?: {
    pre_generation: { status: string; keyword_gaps: string[] };
    post_generation: {
      ats_readability: string;
      keyword_coverage: { coverage_pct: number; missing: string[] };
      unsupported_claims: Array<{ claim: string; reason: string; severity: string }>;
      export_confidence: "good" | "review_recommended" | "acknowledge_required";
      core_sections: Record<string, boolean>;
    };
    document_id: string;
    pack_version: number;
  };
}

// ─────────────────── Phase 3 — API Functions ───────────────────

export async function analyseJob(jobId: string): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/tailor/analyse/${jobId}`, { method: "POST" });
}

export async function analyseJdText(
  jobDescription: string,
  jobUrl?: string,
): Promise<AsyncJobRef> {
  const params = new URLSearchParams({ job_description: jobDescription });
  if (jobUrl) params.set("job_url", jobUrl);
  return apiFetch<AsyncJobRef>(`/api/tailor/analyse?${params}`, { method: "POST" });
}

export async function generateAll(
  jdText: string,
  variant = "A",
  meta?: {
    applicationId?: string | null;
    jobTitle?: string | null;
    companyName?: string | null;
    jobUrl?: string | null;
    templateId?: string | null;
    regenerationInstruction?: string | null;
    designSettings?: ResumeDesignSettings;
  }
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/tailor/generate`, {
    method: "POST",
    body: JSON.stringify({
      application_id: meta?.applicationId ?? null,
      variant,
      jd_text: jdText,
      job_title: meta?.jobTitle ?? null,
      company_name: meta?.companyName ?? null,
      job_url: meta?.jobUrl ?? null,
      template_id: meta?.templateId ?? null,
      design_settings: meta?.designSettings ?? null,
      regeneration_instruction: meta?.regenerationInstruction ?? null,
      custom_instructions: meta?.regenerationInstruction ?? null,
    }),
  });
}

export const fetchResumeTemplates = () =>
  apiFetch<ResumeTemplateResponse>("/api/tailor/templates");

export const setDefaultResumeTemplate = (templateId: string, designSettings?: ResumeDesignSettings) =>
  apiFetch<{ default_template_id: string }>("/api/tailor/templates/default", {
    method: "PUT",
    body: JSON.stringify({ template_id: templateId, design_settings: designSettings }),
  });

export const fetchTailoringReview = (applicationId: string) =>
  apiFetch<TailoringReview>(`/api/tailor/review/${applicationId}`);

export const fetchQualityPrecheck = (analysis: JDAnalysisResult, design_settings: ResumeDesignSettings) =>
  apiFetch<{ status: string; keyword_gaps: string[]; weak_requirements: Array<{ requirement: string; reason: string; severity: string }> }>(
    "/api/tailor/quality/precheck", { method: "POST", body: JSON.stringify({ analysis, design_settings }) }
  );

export async function generateCV(
  applicationId: string,
  jdText: string,
  variant = "A",
  customInstructions?: string,
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/tailor/generate-cv`, {
    method: "POST",
    body: JSON.stringify({
      application_id: applicationId,
      variant,
      jd_text: jdText,
      custom_instructions: customInstructions,
    }),
  });
}

export async function generateCL(
  applicationId: string,
  jdText: string,
  variant = "A",
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/tailor/generate-cl`, {
    method: "POST",
    body: JSON.stringify({ application_id: applicationId, variant, jd_text: jdText }),
  });
}

export async function getDocumentHistory(
  applicationId: string,
  docType?: "cv" | "cover_letter",
): Promise<GeneratedDocument[]> {
  const params = new URLSearchParams();
  if (docType) params.set("doc_type", docType);
  return apiFetch<GeneratedDocument[]>(`/api/tailor/history/${applicationId}?${params}`);
}

export class DocumentQualityAcknowledgementRequiredError extends Error {
  constructor() {
    super("This CV includes issues Hatch could not fully verify. Review the quality warnings before exporting.");
    this.name = "DocumentQualityAcknowledgementRequiredError";
  }
}

export async function downloadDocument(documentId: string, options?: { acknowledgeQualityWarnings?: boolean }): Promise<void> {
  const quality = await apiFetch<TailoringReview["quality_gate"]>(`/api/tailor/quality/document/${documentId}`);
  if (quality?.post_generation?.export_confidence === "acknowledge_required") {
    const key = `quality-ack:${documentId}:${quality.pack_version}`;
    if (!sessionStorage.getItem(key)) {
      if (!options?.acknowledgeQualityWarnings) {
        throw new DocumentQualityAcknowledgementRequiredError();
      }
      sessionStorage.setItem(key, new Date().toISOString());
    }
  }
  const url = `${API_BASE}/api/tailor/document/${documentId}/download`;
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function exportPackagePdf(
  packageId: string,
  kind: "cv" | "cover_letter" = "cv",
): Promise<GeneratedDocumentAsset> {
  const params = new URLSearchParams({ kind });
  return apiFetch<GeneratedDocumentAsset>(`/api/documents/${packageId}/export/pdf?${params}`, { method: "POST" });
}

export async function downloadDocumentAsset(assetId: string, filename?: string): Promise<void> {
  const url = `${API_BASE}/api/documents/assets/${assetId}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = filename ?? "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function getATSScore(documentId: string): Promise<{ ats_score: number; details: ATSScore | null }> {
  return apiFetch(`/api/tailor/ats-score/${documentId}`);
}

export function streamTailoringProgress(
  applicationId: string,
  jdText: string,
  variant: string,
  onProgress: (event: TailorProgressEvent) => void,
  onComplete: (data: TailorProgressEvent) => void,
  onError: (err: Error) => void,
): () => void {
  const params = new URLSearchParams({
    application_id: applicationId,
    jd_text: jdText,
    variant,
  });
  const es = new EventSource(`${API_BASE}/api/tailor/generate/stream?${params}`);

  const STREAM_TIMEOUT_MS = 5 * 60 * 1000;
  const timeoutId = setTimeout(() => {
    es.close();
    onError(new Error("Tailor stream timed out — please try again"));
  }, STREAM_TIMEOUT_MS);

  es.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data) as TailorProgressEvent & Record<string, unknown>;
      if (parsed.stage === "complete") {
        clearTimeout(timeoutId);
        onComplete(parsed);
        es.close();
      } else {
        onProgress(parsed);
      }
    } catch {
      clearTimeout(timeoutId);
      onError(new Error("Invalid SSE event"));
    }
  };

  es.onerror = () => {
    clearTimeout(timeoutId);
    onError(new Error("SSE connection error"));
    es.close();
  };

  return () => { clearTimeout(timeoutId); es.close(); };
}

// ═══════════════════════════════════════════════════════════════
// Coach Module — Types
// ═══════════════════════════════════════════════════════════════

export interface SpeechMetrics {
  filler_count: number;
  wpm: number;
  hedging_count: number;
  duration_ms: number;
  pause_count: number;
}

export interface VideoMetrics {
  eye_contact_pct: number;
  head_stability: number;
  expression: string;
  gesture_freq: number;
}

export interface SessionConfig {
  question_count: number;
  categories: string[];
  recording_mode: "audio" | "video" | "text";
  difficulty: "easy" | "medium" | "hard";
  interviewer_persona?: string | null;
}

export interface CreateSessionRequest {
  application_id?: string | null;
  company_name: string;
  role_title: string;
  jd_text?: string | null;
  interview_date?: string | null;
  config: SessionConfig;
}

export interface QuestionPresentation {
  id: string;
  text: string;
  category: string;
  difficulty: string;
  context: string | null;
  requirement_id?: string | null;
  num: number;
  total: number;
}

export interface SessionQuestion {
  id: string;
  session_id: string;
  question_num: number;
  text: string;
  category: string;
  difficulty: string;
  context: string | null;
  model_answer: string | null;
  requirement_id?: string | null;
  model_answer_diagnostics?: CoachDiagnostic | null;
  order_in_session: number;
}

export interface CoachDiagnostic {
  validation_schema_version: "1.0.0";
  stage: string;
  outcome: string;
  execution_mode: "llm" | "deterministic" | "cache" | "not_run";
  prompt_id?: string | null;
  prompt_version?: string | null;
  output_schema_version?: string | null;
  model_id?: string | null;
  attempt_count: number;
  repair_count: number;
  gate_codes: string[];
  duration_ms: number;
}

export interface AnswerEvaluation {
  evaluation_state?: "completed" | "unavailable" | "invalid";
  diagnostic?: CoachDiagnostic | null;
  scores: Record<string, number>;
  overall: number | null;
  feedback: string;
  strengths: string[];
  improvements: string[];
  follow_up_question: string | null;
  speech_coaching: string[];
  retryable?: boolean;
}

export type CoachExperienceVersion = "legacy_v1" | "conversational_v1";

export type ConversationState =
  | "planning"
  | "ready"
  | "asking"
  | "listening"
  | "processing_answer"
  | "awaiting_next_action"
  | "coaching"
  | "asking_follow_up"
  | "advancing"
  | "paused"
  | "reporting"
  | "completed"
  | "recoverable_error"
  | "abandoned"
  | "failed";

export type ConversationStatus = "setup" | "active" | "completed" | "abandoned" | "failed";
export type ConversationAnswerMode = "audio" | "text";
export type ConversationAudioRetentionPolicy = "delete_after_processing" | "retain_until_deleted";
export type ConversationAudioRetentionState =
  | "not_applicable"
  | "temporary"
  | "retained"
  | "delete_pending"
  | "deleted"
  | "delete_failed";

export type ConversationCommandType =
  | "start"
  | "begin_answer"
  | "finish_answer"
  | "keep_speaking"
  | "pause"
  | "resume"
  | "cancel_attempt"
  | "record_capture_hard_stop"
  | "retry_answer"
  | "retry_setup"
  | "rebuild_plan"
  | "retry_processing"
  | "retry_report"
  | "request_hint"
  | "request_coaching"
  | "return_to_review"
  | "edit_transcript"
  | "accept_attempt"
  | "record_self_assessment"
  | "update_retention"
  | "skip_question"
  | "end_session"
  | "delete_audio"
  | "delete_transcript";

type EmptyConversationCommandPayload = { [key: string]: never };
type ConversationCommandEnvelope<T extends ConversationCommandType, P> = {
  command_id: string;
  command_type: T;
  expected_state_version: number;
  payload: P;
  contract_version: "coach_conversation_command_v1";
};

type FinishConversationAnswerPayload =
  | { attempt_id: string; transcript: string; upload_id?: null }
  | { attempt_id: string; transcript?: null; upload_id: string };

type EndConversationSessionPayload =
  | {
      unaccepted_attempt_action: "accept_attempt";
      attempt_id: string;
      paused_draft_action?: "discard_draft" | null;
    }
  | {
      unaccepted_attempt_action: "exclude_attempt" | "not_applicable";
      attempt_id?: null;
      paused_draft_action?: "discard_draft" | null;
    };

export type ConversationCommandRequest =
  | ConversationCommandEnvelope<"start", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"begin_answer", { recording_type: ConversationAnswerMode; client_attempt_id: string }>
  | ConversationCommandEnvelope<"finish_answer", FinishConversationAnswerPayload>
  | ConversationCommandEnvelope<"keep_speaking", { attempt_id: string }>
  | ConversationCommandEnvelope<"pause", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"resume", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"cancel_attempt", { attempt_id: string }>
  | ConversationCommandEnvelope<"record_capture_hard_stop", { attempt_id: string }>
  | ConversationCommandEnvelope<"retry_answer", { question_id?: string | null }>
  | ConversationCommandEnvelope<"retry_setup", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"rebuild_plan", { refresh_sources: true }>
  | ConversationCommandEnvelope<"retry_processing", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"retry_report", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"request_hint", {
      hint_type: "star_structure" | "competency_reminder" | "experience_category" | "clarify_question";
    }>
  | ConversationCommandEnvelope<"request_coaching", { attempt_id: string }>
  | ConversationCommandEnvelope<"return_to_review", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"edit_transcript", {
      attempt_id: string;
      transcript: string;
      edit_reason: "transcription_error";
    }>
  | ConversationCommandEnvelope<"accept_attempt", { attempt_id: string }>
  | ConversationCommandEnvelope<"record_self_assessment", {
      attempt_id: string;
      comfort_level: "low" | "medium" | "high";
      felt_complete: boolean;
      note?: string | null;
    }>
  | ConversationCommandEnvelope<"update_retention", { audio: ConversationAudioRetentionPolicy }>
  | ConversationCommandEnvelope<"skip_question", EmptyConversationCommandPayload>
  | ConversationCommandEnvelope<"end_session", EndConversationSessionPayload>
  | ConversationCommandEnvelope<"delete_audio", { attempt_id: string }>
  | ConversationCommandEnvelope<"delete_transcript", { attempt_id: string }>;

export interface ConversationCommandResult {
  command_id: string;
  result:
    | "completed"
    | "accepted_processing"
    | "duplicate"
    | "invalid_state"
    | "version_conflict"
    | "idempotency_conflict"
    | "invalid_payload"
    | "resource_blocked"
    | "not_found"
    | "permission_denied"
    | "stale_claim";
  session_id: string;
  state: ConversationState;
  state_version: number;
  active_question_id: string | null;
  active_attempt_id: string | null;
  async_job_id: string | null;
  allowed_commands: ConversationCommandType[];
  contract_version: "coach_conversation_command_result_v1";
}

export interface ConversationalQuestionRead {
  id: string;
  text: string;
  category: "behavioural" | "situational" | "culture" | "technical" | "domain" | "commercial";
  difficulty: "supportive" | "realistic" | "challenging";
  question_kind: "planned" | "adaptive_follow_up";
  question_state: "pending" | "asked" | "answered" | "skipped";
  root_question_id: string | null;
  parent_question_id: string | null;
  follow_up_depth: number;
  follow_up_reason:
    | "clarify_example"
    | "measurable_result"
    | "personal_action"
    | "reasoning"
    | "role_depth"
    | "resolve_ambiguity"
    | "evidence_consistency"
    | null;
  attempts_created_count: number;
  attempt_limit: number;
  attempts_remaining: number;
}

export interface ConversationTranscriptVersionRead {
  id: string;
  version_number: number;
  transcript: string;
  source: "transcription" | "candidate_text" | "candidate_edit" | "recovered_transcription";
  edit_reason: "transcription_error" | null;
  created_by: "system" | "candidate";
  processing_generation: number | null;
  created_at: string;
}

export interface InterviewAttemptRead {
  id: string;
  question_id: string;
  recording_type: ConversationAnswerMode;
  attempt_number: number;
  attempt_state:
    | "draft"
    | "uploaded"
    | "pending_processing"
    | "completed"
    | "recoverable_error"
    | "unavailable"
    | "invalid"
    | "cancelled"
    | "deleted"
    | "skipped";
  attempt_version: number;
  processing_generation: number;
  processing_retry_count: number;
  processing_retry_limit: number;
  processing_retries_remaining: number;
  audio_retention_policy: ConversationAudioRetentionPolicy | null;
  audio_retention_state: ConversationAudioRetentionState | null;
  transcript_version: ConversationTranscriptVersionRead | null;
}

export type ConversationAttemptStage =
  | "audio_persist"
  | "transcription"
  | "speech_analysis"
  | "content_evaluation"
  | "evidence_grounding"
  | "follow_up_decision"
  | "coaching_enrichment"
  | "audio_cleanup";

export type ConversationAttemptStageState =
  | "not_started"
  | "pending"
  | "running"
  | "completed"
  | "reused"
  | "not_applicable"
  | "unavailable"
  | "failed_retryable"
  | "failed_terminal";

export interface ConversationLiveView {
  session_id: string;
  experience_version: "conversational_v1";
  status: ConversationStatus;
  conversation_state: ConversationState;
  state_version: number;
  activity_version: number;
  retention_version: number;
  active_question: ConversationalQuestionRead | null;
  root_question: ConversationalQuestionRead | null;
  active_attempt: InterviewAttemptRead | null;
  processing: {
    job_id: string | null;
    stage: ConversationAttemptStage | null;
    state: ConversationAttemptStageState;
    retryable: boolean;
    retry_count: number;
    retry_limit: number;
    retries_remaining: number;
  };
  progress: {
    planned_questions_total: number;
    planned_questions_completed: number;
    follow_ups_completed: number;
    current_planned_position: number | null;
  };
  retention: {
    audio_policy: ConversationAudioRetentionPolicy;
    current_audio_state: ConversationAudioRetentionState | null;
    retryable_audio_cleanup_attempt_id: string | null;
  };
  allowed_commands: ConversationCommandType[];
  silence_policy: { warning_ms: number; finish_prompt_ms: number };
  recoverable_error: {
    code: string;
    message: string;
    retryable: boolean;
    scope: "setup" | "attempt_processing" | "initial_report" | "completed_report_rebuild";
    details: Record<string, never>;
  } | null;
  report_state: "not_started" | "building" | "completed" | "fallback" | "failed" | "invalidated";
  contract_version: "coach_live_view_v1";
}

export interface ConversationErrorResponse {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    current_state: ConversationState | null;
    current_state_version: number | null;
    correlation_id: string;
    details: Record<string, never>;
  };
}

export interface AttemptAudioUploadRead {
  attempt_id: string;
  upload_id: string;
  result: "pending" | "completed" | "failed" | "deleted";
  content_sha256: string;
  byte_size: number;
  mime_type: string;
  audio_retention_state: ConversationAudioRetentionState;
  contract_version: "coach_attempt_audio_upload_v1";
}

export interface SessionResponse {
  id: string;
  application_id: string | null;
  company_name: string;
  role_title: string;
  status: string;
  overall_score: number | null;
  questions: SessionQuestion[];
  created_at: string;
  interview_date?: string | null;
  experience_version: CoachExperienceVersion | null;
  conversation_state: string | null;
  retention_summary: Record<string, unknown> | null;
}

export interface SessionListItem {
  id: string;
  company_name: string;
  role_title: string;
  status: string;
  overall_score: number | null;
  created_at: string;
  started_at?: string | null;
  experience_version: CoachExperienceVersion | null;
  conversation_state: string | null;
  session_level: string | null;
  retention_summary: Record<string, unknown> | null;
}

export interface PracticePlanDay {
  day: number;
  focus: string;
  activity: string;
  resource: string | null;
}

export interface QuestionEvaluationSummary {
  question_id: string;
  question_text: string;
  category: string;
  overall_score: number;
  scores?: Record<string, number>;
  strengths: string[];
  improvements: string[];
}

export interface SessionFeedbackReport {
  session_id: string;
  report_state?: "completed" | "fallback";
  diagnostic?: CoachDiagnostic | null;
  overall_score: number | null;
  question_count_total?: number;
  question_count_evaluated?: number;
  question_count_skipped?: number;
  question_count_unavailable?: number;
  question_count_unanswered?: number;
  category_scores: Record<string, number>;
  executive_summary: string;
  strengths: string[];
  improvement_areas: string[];
  coaching_points: string[];
  practice_plan: PracticePlanDay[];
  question_evaluations: QuestionEvaluationSummary[];
}

export interface CompanyResearchResponse {
  company_name: string;
  sector: string | null;
  website: string | null;
  description: string | null;
  recent_news: string[];
  key_products: string[];
  tech_stack_signals: string[];
}

// ═══════════════════════════════════════════════════════════════
// Coach Module — API Functions
// ═══════════════════════════════════════════════════════════════

export async function createSession(
  request: CreateSessionRequest
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>("/api/coach/sessions", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listSessions(
  limit = 20,
  status?: string
): Promise<SessionListItem[]> {
  const params = buildQueryString({ limit, status });
  return apiFetch<SessionListItem[]>(`/api/coach/sessions${params}`);
}

export async function getSession(id: string): Promise<SessionResponse> {
  return apiFetch<SessionResponse>(`/api/coach/sessions/${id}`);
}

export async function getCoachConversationLive(
  sessionId: string,
): Promise<ConversationLiveView> {
  return apiFetch<ConversationLiveView>(
    `/api/coach/sessions/${sessionId}/live`,
    { cache: "no-store" },
  );
}

export async function sendCoachConversationCommand(
  sessionId: string,
  command: ConversationCommandRequest,
): Promise<ConversationCommandResult> {
  return apiFetch<ConversationCommandResult>(
    `/api/coach/sessions/${sessionId}/commands`,
    {
      method: "POST",
      body: JSON.stringify(command),
    },
  );
}

export async function uploadCoachAttemptAudio(
  sessionId: string,
  attemptId: string,
  request: { uploadId: string; contentSha256: string; audio: Blob },
): Promise<AttemptAudioUploadRead> {
  const form = new FormData();
  form.set("upload_id", request.uploadId);
  form.set("content_sha256", request.contentSha256);
  form.set("audio", request.audio);
  return apiFetch<AttemptAudioUploadRead>(
    `/api/coach/sessions/${sessionId}/attempts/${attemptId}/audio`,
    { method: "POST", body: form },
  );
}

export async function retrySession(id: string): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/coach/sessions/${id}/retry`, {
    method: "POST",
  });
}

export async function endSession(id: string): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/coach/sessions/${id}/end`, {
    method: "POST",
  });
}

export async function getSessionReport(
  id: string
): Promise<SessionFeedbackReport> {
  return apiFetch<SessionFeedbackReport>(`/api/coach/sessions/${id}/report`);
}

export async function getNextQuestion(
  sessionId: string
): Promise<QuestionPresentation | null> {
  return apiFetch<QuestionPresentation | null>(
    `/api/coach/sessions/${sessionId}/next-question`
  );
}

export async function submitAnswer(
  sessionId: string,
  questionId: string,
  transcript: string,
  durationMs: number,
  speechMetrics?: SpeechMetrics,
  videoMetrics?: VideoMetrics
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(
    `/api/coach/sessions/${sessionId}/submit-answer?question_id=${questionId}`,
    {
      method: "POST",
      body: JSON.stringify({
        transcript,
        duration_ms: durationMs,
        speech_metrics: speechMetrics ?? null,
        video_metrics: videoMetrics ?? null,
      }),
    }
  );
}

export async function submitAudio(
  sessionId: string,
  questionId: string,
  audioBlob: Blob,
  filename?: string,
  faceSummary?: { eye_contact_pct: number; avg_arousal: number; head_stability: number; engagement_trend: string } | null
): Promise<AsyncJobRef> {
  const form = new FormData();
  form.append("question_id", questionId);
  form.append("audio", audioBlob, filename ?? "answer.webm");
  if (faceSummary) {
    form.append("face_summary", JSON.stringify(faceSummary));
  }
  return apiFetch<AsyncJobRef>(
    `/api/coach/sessions/${sessionId}/submit-audio`,
    { method: "POST", body: form }
  );
}

export async function skipQuestion(
  sessionId: string,
  questionId: string
): Promise<void> {
  await apiFetch<void>(
    `/api/coach/sessions/${sessionId}/skip?question_id=${questionId}`,
    { method: "POST" }
  );
}

export async function researchCompany(
  companyName: string,
  sector?: string
): Promise<CompanyResearchResponse> {
  const params = buildQueryString({ company_name: companyName, sector });
  return apiFetch<CompanyResearchResponse>(`/api/coach/research${params}`, {
    method: "POST",
  });
}

export async function abandonSession(sessionId: string): Promise<void> {
  await apiFetch<void>(`/api/coach/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

// ═══════════════════════════════════════════════════════════════
// Coach Module — Phase C types + API
// ═══════════════════════════════════════════════════════════════

export interface TechnicalDrill {
  question_id: string;
  question_text: string;
  walkthrough: string;
  drill_prompt: string;
  category: string;
}

export interface ProgressTrendItem {
  session_id: string;
  created_at: string;
  overall_score: number | null;
  rubric_scores: Record<string, number>;
  focus_areas: string[];
}

export interface PlanFollowUpResponse {
  followup_session_id: string;
  focus_areas: string[];
  message: string;
}

export interface CoachCapabilities {
  face_analysis: boolean;
  tts: boolean;
}

/** Plan a follow-up session targeting the weakest rubric dimensions. */
export async function planFollowUpSession(sessionId: string): Promise<PlanFollowUpResponse> {
  return apiFetch<PlanFollowUpResponse>(
    `/api/coach/sessions/${sessionId}/plan-followup`,
    { method: "POST" }
  );
}

/** Return per-session progress trend for the session chain. */
export async function getProgressTrend(sessionId: string): Promise<ProgressTrendItem[]> {
  return apiFetch<ProgressTrendItem[]>(`/api/coach/progress/${sessionId}/trend`);
}

/** Return which perception capabilities are enabled. */
export async function getCoachCapabilities(): Promise<CoachCapabilities> {
  return apiFetch<CoachCapabilities>("/api/coach/capabilities");
}

// ═══════════════════════════════════════════════════════════════
// Coach Module — Phase E (TTS)
// ═══════════════════════════════════════════════════════════════

/**
 * Returns the URL for streaming TTS audio of a question.
 * Use as `<audio src={getTTSQuestionUrl(...)}>` — no fetch needed.
 */
export function getTTSQuestionUrl(sessionId: string, questionId: string): string {
  return `/api/coach/sessions/${sessionId}/tts-question?question_id=${questionId}`;
}

// ─── V2 Types ───────────────────────────────────────────────────────────────

export interface FilterCounts {
  employment_type: Record<string, number>
  working_pattern: Record<string, number>
  ir35_status: Record<string, number>
}

export interface ApplicationAttempt {
  id: string
  application_id: string
  job_url: string
  apply_url?: string
  platform?: string
  status: string
  form_data?: string
  custom_questions?: string
  cv_path?: string
  cl_path?: string
  screenshot_before?: string
  screenshot_after?: string
  error_message?: string
  submitted_at?: string
  created_at: string
}

export interface ApplicationPreview extends ApplicationAttempt {
  form_fields?: Array<{ label: string; value: string; field_type: string; filled: boolean }>
  questions?: Array<{ question: string; answer: string }>
}

// ─── V2 API Functions ────────────────────────────────────────────────────────

export async function fetchFilterCounts(): Promise<FilterCounts> {
  return apiFetch<FilterCounts>('/api/jobs/filter-counts')
}

export async function createAutoApplyAttempt(applicationId: string): Promise<ApplicationAttempt> {
  return apiFetch<ApplicationAttempt>(`/api/auto-apply/prepare/${applicationId}`, { method: 'POST' })
}

export async function getAutoApplyPreview(attemptId: string): Promise<ApplicationAttempt> {
  return apiFetch<ApplicationAttempt>(`/api/auto-apply/preview/${attemptId}`)
}

export async function updateAutoApplyPreview(attemptId: string, updates: Partial<ApplicationAttempt>): Promise<ApplicationAttempt> {
  return apiFetch<ApplicationAttempt>(`/api/auto-apply/preview/${attemptId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

export async function approveAutoApply(attemptId: string): Promise<ApplicationAttempt> {
  return apiFetch<ApplicationAttempt>(`/api/auto-apply/approve/${attemptId}`, { method: 'POST' })
}

export async function submitAutoApply(attemptId: string): Promise<ApplicationAttempt> {
  return apiFetch<ApplicationAttempt>(`/api/auto-apply/submit/${attemptId}`, { method: 'POST' })
}

export async function getAutoApplyHistory(applicationId?: string): Promise<ApplicationAttempt[]> {
  const qs = applicationId ? `?application_id=${applicationId}` : ''
  return apiFetch<ApplicationAttempt[]>(`/api/auto-apply/history${qs}`)
}

export async function getDigestPreview(): Promise<string> {
  // Returns HTML text, not JSON — keep raw fetch
  const res = await fetch(`${API_BASE}/api/digest/preview`)
  if (!res.ok) throw new Error('Failed to fetch digest preview')
  return res.text()
}

export async function sendDigest(): Promise<{ sent: boolean; message: string }> {
  return apiFetch<{ sent: boolean; message: string }>('/api/digest/send', { method: 'POST' })
}

export interface DigestStatus {
  enabled: boolean
  time: string
  timezone: string
  frequency: string
  smtp_configured: boolean
  recipient: string | null
}

export async function getDigestStatus(): Promise<DigestStatus> {
  return apiFetch<DigestStatus>('/api/digest/status')
}

export async function updateDigestSettings(
  updates: Partial<Pick<DigestStatus, 'timezone' | 'time' | 'frequency' | 'enabled'>>
): Promise<DigestStatus> {
  return apiFetch<DigestStatus>('/api/digest/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

// ─────────────────────── Follow-Up Emails ───────────────────────

export interface FollowUpEmailRead {
  id: string
  application_id: string
  follow_up_id?: string
  email_type: string
  recipient_email?: string
  recipient_name?: string
  subject: string
  body_html: string
  body_plain: string
  status: string
  sent_via?: string
  sent_at?: string
  created_at: string
  job_title?: string
  company?: string
}

export interface FollowUpEmailListItem {
  id: string
  application_id: string
  email_type: string
  recipient_email?: string
  subject: string
  status: string
  created_at: string
  job_title?: string
  company?: string
}

export interface EmailStats {
  sent_this_week: number
  sent_total: number
  pending_drafts: number
  by_type: Record<string, number>
}

export async function fetchPendingEmails(): Promise<FollowUpEmailListItem[]> {
  return apiFetch<FollowUpEmailListItem[]>('/api/emails/pending')
}

export async function fetchEmailById(emailId: string): Promise<FollowUpEmailRead> {
  return apiFetch<FollowUpEmailRead>(`/api/emails/${emailId}`)
}

export async function generateEmail(
  applicationId: string,
  emailType: string
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/emails/generate/${applicationId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email_type: emailType }),
  })
}

export async function updateEmail(
  emailId: string,
  updates: { subject?: string; body?: string; recipient_email?: string }
): Promise<FollowUpEmailRead> {
  return apiFetch<FollowUpEmailRead>(`/api/emails/${emailId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

export async function sendEmail(
  emailId: string,
  request: { send_via: string; recipient_email: string; subject?: string; body?: string }
): Promise<{ success: boolean; message: string; mailto_link?: string }> {
  const res = await fetch(`${API_BASE}/api/emails/${emailId}/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string }).detail ?? 'Failed to send email')
  }
  return res.json() as Promise<{ success: boolean; message: string; mailto_link?: string }>
}

export async function skipEmail(emailId: string): Promise<FollowUpEmailRead> {
  return apiFetch<FollowUpEmailRead>(`/api/emails/${emailId}/skip`, { method: 'POST' })
}

export async function regenerateEmail(emailId: string): Promise<FollowUpEmailRead> {
  return apiFetch<FollowUpEmailRead>(`/api/emails/${emailId}/regenerate`, { method: 'POST' })
}

export async function fetchEmailStats(): Promise<EmailStats> {
  return apiFetch<EmailStats>('/api/emails/stats')
}

// ── Ghost Detection ──────────────────────────────────────────────────

export interface GhostStats {
  likely_real: number
  uncertain: number
  suspicious: number
  likely_ghost: number
  total_analysed: number
  total_pending: number
}

export interface GhostScore {
  job_id: string
  score: number
  verdict: string
  signals: [string, unknown][]
  analysed_at: string
}

export async function fetchGhostStats(): Promise<GhostStats> {
  return apiFetch<GhostStats>('/api/ghost/stats')
}

export async function fetchFlaggedJobs(minScore = 50, limit = 50): Promise<Job[]> {
  return apiFetch<Job[]>(`/api/ghost/flagged?min_score=${minScore}&limit=${limit}`)
}

export async function analyseGhostJob(jobId: string): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/ghost/analyse/${jobId}`, { method: 'POST' })
}

export async function overrideGhostVerdict(jobId: string, verdict: string): Promise<Job> {
  return apiFetch<Job>(`/api/ghost/override/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ override_verdict: verdict }),
  })
}

// ──────────────────────── Async Jobs ────────────────────────

export interface AsyncJobRef {
  job_id: string
  status: string
  type: string
  session_id?: string
}

export interface AsyncJobResponse<T = unknown> {
  id: string
  type: string
  status: "pending" | "running" | "done" | "failed"
  result: T | null
  error: string | null
  created_at: string
}

export async function getAsyncJob<T = unknown>(
  jobId: string
): Promise<AsyncJobResponse<T>> {
  return apiFetch<AsyncJobResponse<T>>(`/api/async-jobs/${jobId}`)
}

export async function listCompletedJobs(
  since: string,
  limit = 20
): Promise<AsyncJobResponse[]> {
  const qs = `?status=done&status=failed&since=${encodeURIComponent(since)}&limit=${limit}`
  return apiFetch<AsyncJobResponse[]>(`/api/async-jobs${qs}`)
}

export async function listTailorHistory(
  limit = 10
): Promise<AsyncJobResponse<JDAnalysisResponse>[]> {
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString()
  const qs = `?type=tailor_analyse&status=done&status=failed&status=pending&status=running&since=${encodeURIComponent(since)}&limit=${limit}`
  return apiFetch<AsyncJobResponse<JDAnalysisResponse>[]>(`/api/async-jobs${qs}`)
}

// ── Agentic pipeline ────────────────────────────────────────

export interface AgentStatusSummary {
  agent_name: string
  status: 'idle' | 'running' | 'waiting_approval' | 'error' | 'never_run'
  last_run_at: string | null
}

export interface AllAgentStatus {
  agents: AgentStatusSummary[]
  database: string
  uptime_seconds: number
}

export interface AgentEvent {
  id: string
  event_type: string
  source_agent: string
  payload: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  processed_at: string | null
  error_message: string | null
}

export interface AgentEventList {
  items: AgentEvent[]
  total: number
}

export interface PendingApproval {
  application_id: string
  job_id: string | null
  job_title: string | null
  company: string | null
  rate_text: string | null
  job_url: string | null
  overall_score: number | null
  latest_cv_ats_score?: number | null
  skill_match: number | null
  experience_match: number | null
  rate_match: number | null
  location_match: number | null
  status: string
  approval_status: string
  created_at: string | null
}

export interface PipelineStats {
  discovered: number
  scored: number
  shortlisted: number
  tailored: number
  approved: number
  coach_sessions: number
}

export async function fetchAllAgentStatus(): Promise<AllAgentStatus> {
  return apiFetch<AllAgentStatus>('/api/agents/status')
}

export async function fetchAgentEvents(
  params?: { event_type?: string; status?: string; limit?: number }
): Promise<AgentEventList> {
  const qs = new URLSearchParams()
  if (params?.event_type) qs.set('event_type', params.event_type)
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  return apiFetch<AgentEventList>(`/api/events?${qs}`)
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  return apiFetch<PendingApproval[]>('/api/agents/approvals/pending')
}

export async function fetchApprovalDetail(applicationId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/agents/approvals/${applicationId}`)
}

export async function approveApplication(applicationId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/agents/approvals/${applicationId}/approve`, { method: 'POST' })
}

export async function rejectApplication(applicationId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/agents/approvals/${applicationId}/reject`, { method: 'POST' })
}

export async function fetchPipelineStats(): Promise<PipelineStats> {
  return apiFetch<PipelineStats>('/api/agents/dashboard/pipeline')
}

export async function triggerAgent(agentName: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/agents/${agentName}/trigger`, { method: 'POST' })
}

// ──────────────────────── Story Bank ────────────────────────

export interface StoryListItem {
  id: string;
  title: string;
  slug: string;
  summary: string | null;
  tags: string[] | null;
  archetype_fit: string[] | null;
  strength_score: number;
  times_used: number;
  version: number;
  manual_rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface StoryRead extends StoryListItem {
  situation: string | null;
  task: string | null;
  action: string | null;
  result: string | null;
  reflection: string | null;
  skills: string[] | null;
  metrics: Record<string, unknown> | null;
  source_session_id: string | null;
  source_question_id: string | null;
  is_active: boolean;
}

export interface PaginatedStories {
  items: StoryListItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface StoryCreate {
  title: string;
  summary?: string;
  situation?: string;
  task?: string;
  action?: string;
  result?: string;
  reflection?: string;
  tags?: string[];
  skills?: string[];
  metrics?: Record<string, unknown>;
  archetype_fit?: string[];
}

export type StoryUpdate = Partial<StoryCreate>;

export interface StoryMatchResult {
  story: StoryListItem;
  confidence: number;
  match_stage: string;
  match_reason: string | null;
}

export interface StoryMatchResponse {
  matches: StoryMatchResult[];
  question: string;
}

export async function listStories(params?: {
  skip?: number;
  limit?: number;
  archetype?: string;
  tag?: string;
  skill?: string;
  min_strength?: number;
}): Promise<PaginatedStories> {
  const q = new URLSearchParams();
  if (params?.skip) q.set("skip", String(params.skip));
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.archetype) q.set("archetype", params.archetype);
  if (params?.tag) q.set("tag", params.tag);
  if (params?.skill) q.set("skill", params.skill);
  if (params?.min_strength !== undefined) q.set("min_strength", String(params.min_strength));
  const qs = q.toString();
  return apiFetch<PaginatedStories>(`/api/stories${qs ? "?" + qs : ""}`);
}

export async function getStory(id: string): Promise<StoryRead> {
  return apiFetch<StoryRead>(`/api/stories/${id}`);
}

export async function createStory(data: StoryCreate): Promise<StoryRead> {
  return apiFetch<StoryRead>("/api/stories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateStory(id: string, data: StoryUpdate): Promise<StoryRead> {
  return apiFetch<StoryRead>(`/api/stories/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteStory(id: string): Promise<void> {
  return apiFetch<void>(`/api/stories/${id}`, { method: "DELETE" });
}

export async function rateStory(id: string, rating: number): Promise<StoryRead> {
  return apiFetch<StoryRead>(`/api/stories/${id}/rate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  });
}

export async function recordStoryUse(id: string): Promise<void> {
  return apiFetch<void>(`/api/stories/${id}/record-use`, { method: "POST" });
}

export async function suggestStories(params?: {
  archetype?: string;
  tags?: string;
  top_n?: number;
}): Promise<StoryListItem[]> {
  const q = new URLSearchParams();
  if (params?.archetype) q.set("archetype", params.archetype);
  if (params?.tags) q.set("tags", params.tags);
  if (params?.top_n) q.set("top_n", String(params.top_n));
  const qs = q.toString();
  return apiFetch<StoryListItem[]>(`/api/stories/suggest${qs ? "?" + qs : ""}`);
}

export async function matchStories(question: string, tags?: string[]): Promise<StoryMatchResponse> {
  return apiFetch<StoryMatchResponse>("/api/stories/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, tags }),
  });
}

// ──────────────────────── Question Bank ────────────────────────

export type QuestionBankItemType =
  | "interview_question"
  | "star_story"
  | "proof_point"
  | "company_research_note"
  | "role_specific_answer";

export type QuestionBankConfidence = "draft" | "reviewed" | "final";

export interface QuestionBankItem {
  id: string;
  type: QuestionBankItemType | string;
  question: string | null;
  title: string;
  answer_draft: string;
  situation: string | null;
  task: string | null;
  action: string | null;
  result: string | null;
  skills: string[];
  tags: string[];
  seniority: string | null;
  role_family: string | null;
  linked_applications: string[];
  source: "manual" | "interview_prep" | "cv_import" | "ai_suggested" | string;
  confidence: QuestionBankConfidence | string;
  source_session_id: string | null;
  source_question_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuestionBankList {
  items: QuestionBankItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface QuestionBankCreate {
  type?: QuestionBankItemType;
  question?: string | null;
  title: string;
  answer_draft: string;
  situation?: string | null;
  task?: string | null;
  action?: string | null;
  result?: string | null;
  skills?: string[];
  tags?: string[];
  seniority?: string | null;
  role_family?: string | null;
  linked_applications?: string[];
  source?: "manual" | "interview_prep" | "cv_import" | "ai_suggested";
  confidence?: QuestionBankConfidence;
}

export type QuestionBankUpdate = Partial<QuestionBankCreate>;

export async function listQuestionBank(params?: {
  skip?: number;
  limit?: number;
  search?: string;
  type?: string;
  tag?: string;
  skill?: string;
  confidence?: string;
  application_id?: string;
}): Promise<QuestionBankList> {
  const q = new URLSearchParams();
  if (params?.skip) q.set("skip", String(params.skip));
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.search) q.set("search", params.search);
  if (params?.type) q.set("type", params.type);
  if (params?.tag) q.set("tag", params.tag);
  if (params?.skill) q.set("skill", params.skill);
  if (params?.confidence) q.set("confidence", params.confidence);
  if (params?.application_id) q.set("application_id", params.application_id);
  const qs = q.toString();
  return apiFetch<QuestionBankList>(`/api/question-bank${qs ? "?" + qs : ""}`);
}

export async function createQuestionBankItem(data: QuestionBankCreate): Promise<QuestionBankItem> {
  return apiFetch<QuestionBankItem>("/api/question-bank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateQuestionBankItem(id: string, data: QuestionBankUpdate): Promise<QuestionBankItem> {
  return apiFetch<QuestionBankItem>(`/api/question-bank/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteQuestionBankItem(id: string): Promise<void> {
  return apiFetch<void>(`/api/question-bank/${id}`, { method: "DELETE" });
}

export async function saveQuestionBankFromInterviewAnswer(data: {
  session_id: string;
  question_id: string;
  answer_draft: string;
  title?: string | null;
  situation?: string | null;
  task?: string | null;
  action?: string | null;
  result?: string | null;
  skills?: string[];
  tags?: string[];
  confidence?: QuestionBankConfidence;
}): Promise<QuestionBankItem> {
  return apiFetch<QuestionBankItem>("/api/question-bank/from-interview-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ──────────────────────── Profile ────────────────────────

export interface ProfileStatus {
  exists: boolean;
  complete: boolean;
  onboarding_required: boolean;
  candidate_name?: string;
  llm_provider?: string;
  target_roles?: string[];
  errors?: string[];
}

export async function fetchProfileStatus(): Promise<ProfileStatus> {
  return apiFetch<ProfileStatus>("/api/v2/profile/status", { cache: "no-store" });
}

export interface RawProfile {
  candidate?: { name?: string; title?: string; years_experience?: number };
  search?: {
    target_roles?: string[];
    locations?: Array<{ city?: string; country?: string; remote_preference?: string }>;
    contract_type?: string;
  };
  compensation?: { min_rate?: number; max_rate?: number; rate_type?: string; currency?: string; ir35_preference?: string; legal_preferences?: Record<string, string> };
  skills?: { primary?: string[]; secondary?: string[]; certifications?: string[] };
  preferences?: { scrape_interval_hours?: number; max_tailor_batch?: number };
  scoring?: { shortlist_threshold?: number };
  llm?: { provider?: string; primary_model?: string; triage_model?: string };
  perception?: { face?: { provider?: string; enabled?: boolean } };
  outcome_learning?: {
    enabled?: boolean;
    minimum_total_applications?: number;
    minimum_segment_size?: number;
    maximum_score_adjustment?: number;
    maximum_signal_adjustment?: number;
    no_response_after_days?: number;
    recency_half_life_days?: number;
    enabled_signals?: string[];
    learning_since?: string | null;
  };
}

export async function fetchRawProfile(): Promise<RawProfile> {
  return apiFetch<RawProfile>("/api/v2/profile", { cache: "no-store" });
}

export async function saveProfile(data: Record<string, unknown>): Promise<RawProfile> {
  return apiFetch<RawProfile>("/api/v2/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function testLLMConnection(provider: string, apiKey: string): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>("/api/v2/profile/test-connection", {
    method: "POST",
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
}

// ──────────────────────── Locales ────────────────────────

export interface LocaleSummary {
  id: string;
  name: string;
  flag: string;
  currency: string;
  currency_symbol: string;
  default_rate_type: string;
}

export interface LocaleLegalField {
  id: string;
  label: string;
  help?: string;
  type: "select" | "text";
  options?: Array<{ value: string; label: string }>;
  default: string;
}

export interface LocaleBoard {
  id: string;
  name: string;
  enabled: boolean;
  scraper: string;
}

export async function fetchLocales(): Promise<LocaleSummary[]> {
  return apiFetch<LocaleSummary[]>("/api/v2/locales");
}

export async function fetchLocaleLegalFields(localeId: string): Promise<LocaleLegalField[]> {
  return apiFetch<LocaleLegalField[]>(`/api/v2/locales/${localeId}/legal-fields`);
}

export async function fetchLocaleBoards(localeId: string): Promise<LocaleBoard[]> {
  return apiFetch<LocaleBoard[]>(`/api/v2/locales/${localeId}/boards?enabled_only=false`);
}

// ──────────────────────── Archive ────────────────────────

export async function runArchive(days?: number): Promise<{ archived: number }> {
  const qs = days !== undefined ? `?days=${days}` : "";
  return apiFetch<{ archived: number }>(`/api/jobs/archive/run${qs}`, { method: "POST" });
}

export async function unarchiveJob(jobId: string): Promise<{ status: string; id: string }> {
  return apiFetch<{ status: string; id: string }>(`/api/jobs/${jobId}/unarchive`, { method: "POST" });
}

export async function rescoreUnscored(): Promise<{ queued: number }> {
  return apiFetch<{ queued: number }>("/api/jobs/rescore-unscored", { method: "POST" });
}

// ──────────────────────── Activity Timeline ────────────────────────

export interface ActivityItem {
  id: string;
  timestamp: string;
  agent: string;
  event_type: string;
  status: string;
  title: string;
  detail: string | null;
  job_id: string | null;
  cost_estimate: number | null;
  model_used: string | null;
}

export interface ActivityList {
  items: ActivityItem[];
  total: number;
}

export async function fetchActivity(limit = 20, hours = 24): Promise<ActivityList> {
  return apiFetch<ActivityList>(`/api/events/activity?limit=${limit}&hours=${hours}`);
}

export async function fetchCostSummary(days = 30): Promise<{
  total_cost_usd: number;
  by_agent: Record<string, number>;
  total_calls: number;
}> {
  return apiFetch(`/api/events/costs?days=${days}`);
}

// ──────────────────────── Decision Trail ────────────────────────

export interface DecisionStep {
  step: number;
  agent: string;
  event_type: string;
  status: string;
  timestamp: string;
  summary: string;
  reasoning: string | null;
  score: number | null;
  skill_match: number | null;
  experience_match: number | null;
  rate_match: number | null;
  location_match: number | null;
  model_used: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_estimate: number | null;
  duration_ms: number | null;
  ats_score: number | null;
}

export interface DecisionTrail {
  job_id: string;
  job_title: string | null;
  steps: DecisionStep[];
  total_cost_usd: number;
}

export async function fetchJobDecisions(jobId: string): Promise<DecisionTrail> {
  return apiFetch<DecisionTrail>(`/api/jobs/${jobId}/decisions`);
}

// ──────────────────────── Resume / CV Management ────────────────────────

export interface ResumeStatus {
  exists: boolean;
  filename: string | null;
  uploaded_at: string | null;
  parsed: boolean;
  sections: Record<string, boolean>;
  skills_count: number;
  experience_count: number;
  proof_points_count: number;
}

export interface ParsePreviewResponse {
  parsed_cv: Record<string, unknown>;
  warnings: string[];
  filename: string;
  raw_text_saved: boolean;
}

export async function fetchResumeStatus(): Promise<ResumeStatus> {
  return apiFetch<ResumeStatus>("/api/resume/status");
}

export async function uploadResume(file: File): Promise<ParsePreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ParsePreviewResponse>("/api/resume/upload", {
    method: "POST",
    body: formData,
  });
}

export async function confirmCv(
  parsedCv: Record<string, unknown>,
  filename?: string
): Promise<ResumeStatus> {
  return apiFetch<ResumeStatus>("/api/resume/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parsed_cv: parsedCv, filename }),
  });
}

export async function fetchMasterCvJson(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>("/api/resume/json");
}

// ──────────────────────── Follow-up Reminders ────────────────────────

export interface FollowUpReminder {
  application_id: string;
  job_title: string | null;
  company: string | null;
  applied_date: string | null;
  days_since_applied: number;
  follow_up_number: number;
  due_date: string;
  overdue: boolean;
}

export async function fetchFollowUpReminders(): Promise<FollowUpReminder[]> {
  return apiFetch<FollowUpReminder[]>("/api/applications/follow-up-reminders");
}

// ──────────────────────── Analytics Enhancements ────────────────────────

export interface AtsCorrelationBucket {
  range: string;
  label: string;
  total: number;
  responses: number;
  response_rate_pct: number;
}

export interface AtsCorrelation {
  buckets: AtsCorrelationBucket[];
  total_scored: number;
  message?: string;
}

export async function fetchAtsCorrelation(): Promise<AtsCorrelation> {
  return apiFetch<AtsCorrelation>("/api/analytics/ats-correlation");
}

export interface SkillFrequencyItem {
  skill: string;
  count: number;
}

export interface SkillFrequency {
  skills: SkillFrequencyItem[];
  total_jobs_analyzed: number;
  message?: string;
}

export async function fetchSkillFrequency(limit = 20): Promise<SkillFrequency> {
  return apiFetch<SkillFrequency>(`/api/analytics/skill-frequency?limit=${limit}`);
}

export interface ScoreDistributionBucket { bucket: string; min: number; max: number; count: number }
export interface ScoreDistribution { buckets: ScoreDistributionBucket[]; threshold: number; total: number }
export async function fetchScoreDistribution(): Promise<ScoreDistribution> {
  return apiFetch<ScoreDistribution>('/api/analytics/score-distribution');
}

export interface MonthlyCosts { total: number; currency: string; by_agent: Record<string, number>; budget: number; budget_pct: number }
export async function fetchCostsMonthly(): Promise<MonthlyCosts> {
  return apiFetch<MonthlyCosts>('/api/analytics/costs/monthly');
}

export interface DailyCostEntry { date: string; total: number; by_agent: Record<string, number> }
export interface DailyCosts { days: DailyCostEntry[] }
export async function fetchCostsDaily(days = 30): Promise<DailyCosts> {
  return apiFetch<DailyCosts>(`/api/analytics/costs/daily?days=${days}`);
}

export interface AgentPerformanceRow { agent: string; runs_today: number; runs_this_week: number; success_rate: number; last_error: string | null; last_run_at: string | null }
export interface AgentPerformance { agents: AgentPerformanceRow[] }
export async function fetchAgentPerformance(): Promise<AgentPerformance> {
  return apiFetch<AgentPerformance>('/api/analytics/agent-performance');
}

export interface SearchQuality { total_discovered: number; passed_triage: number; shortlisted: number; triage_pass_rate: number; shortlist_rate: number; threshold: number }
export async function fetchSearchQuality(): Promise<SearchQuality> {
  return apiFetch<SearchQuality>('/api/analytics/search-quality');
}

export interface SkillGapEntry { skill: string; count: number }
export interface SkillGaps { skills: SkillGapEntry[]; message?: string }
export async function fetchSkillGaps(limit = 15): Promise<SkillGaps> {
  return apiFetch<SkillGaps>(`/api/analytics/skill-gaps?limit=${limit}`);
}

export interface OllamaModelsResult {
  models: string[];
  base_url: string;
  error?: string;
}

export async function fetchOllamaModels(): Promise<OllamaModelsResult> {
  return apiFetch<OllamaModelsResult>('/api/v2/settings/ollama-models');
}

export async function saveOllamaModel(primaryModel: string, triageModel?: string): Promise<{ saved: boolean; primary_model: string; triage_model: string }> {
  return apiFetch('/api/v2/settings/ollama-model', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ primary_model: primaryModel, triage_model: triageModel ?? '' }),
  });
}

// ── Rate limit status ────────────────────────────────────────────────

export interface RateLimitStatus {
  rpm_used: number;
  rpm_limit: number;
  rpm_remaining: number;
  rpd_used: number;
  rpd_limit: number;
  rpd_remaining: number;
  wait_seconds: number;
  throttled: boolean;
  last_429_at: number | null;
}

export async function fetchRateLimitStatus(): Promise<RateLimitStatus> {
  return apiFetch<RateLimitStatus>('/api/agents/rate-limit-status');
}

// ── Gap Analysis ──────────────────────────────────────────────────────

export interface GapAnalysis {
  matched_skills: string[];
  missing_skills: string[];
  match_percentage: number;
  jd_only_keywords: string[];
  recommendations: string[];
}

export async function fetchGapAnalysis(jobId: string): Promise<GapAnalysis> {
  return apiFetch<GapAnalysis>(`/api/v2/jobs/${jobId}/gap-analysis`);
}

// ── Interview .ics export ─────────────────────────────────────────────

// ── Scoring insights ───────────────────────────────────────────────────

export interface ScoreBucket {
  bucket: string;
  count: number;
}

export interface ScoringInsights {
  threshold: number;
  scored_last_7d: number;
  above_threshold: number;
  in_band_below: number;
  avg_score: number | null;
  distribution: ScoreBucket[];
  recommendation: string | null;
  total_jobs_in_db: number;
  total_scored: number;
}

export async function fetchScoringInsights(): Promise<ScoringInsights> {
  return apiFetch<ScoringInsights>("/api/v2/scoring/insights");
}

export interface JobScoreRead {
  id: string;
  job_id: string;
  overall_score: number;
  skill_match: number | null;
  experience_match: number | null;
  rate_match: number | null;
  location_match: number | null;
  reasoning: string | null;
  scored_at: string;
}

export async function fetchJobScore(jobId: string): Promise<JobScoreRead | null> {
  try {
    return await apiFetch<JobScoreRead>(`/api/v2/scoring/${jobId}`);
  } catch {
    return null;
  }
}

// ── Assisted Apply ──────────────────────────────────────────────────────────

export interface ApplicationPackage {
  job_id: string;
  job_url: string;
  cv_path: string | null;
  cover_letter_path: string | null;
  cv_document_id?: string | null;
  cl_document_id?: string | null;
  prefill_map: Record<string, string>;
  screening_answers: Record<string, string>;
  paste_map: Record<string, string>;
}

export async function prepareApplication(applicationId: string): Promise<ApplicationPackage> {
  return apiFetch<ApplicationPackage>(`/api/applications/${applicationId}/prepare`, {
    method: "POST",
  });
}

export interface ApproveJobRef {
  async_job_id: string
  job_id: string
  status: "preparing"
  message: string
}

export async function approveJob(jobId: string): Promise<ApproveJobRef> {
  return apiFetch<ApproveJobRef>(`/api/jobs/${jobId}/approve`, { method: "POST" });
}

export async function getApplicationPackage(appId: string): Promise<ApplicationPackage> {
  return apiFetch<ApplicationPackage>(`/api/applications/${appId}/package`);
}

export async function markApplied(appId: string): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${appId}/mark-applied`, { method: "POST" });
}

export async function revertApplication(appId: string): Promise<Application> {
  return apiFetch<Application>(`/api/applications/${appId}/revert`, { method: "POST" });
}

export async function downloadInterviewIcs(interviewId: string): Promise<void> {
  const url = `/api/v2/interviews/${interviewId}/ical`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to download .ics: ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `interview_${interviewId}.ics`;
  a.click();
  URL.revokeObjectURL(a.href);
}
