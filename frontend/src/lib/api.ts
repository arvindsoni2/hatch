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
}

// ──────────────────────── Helpers ────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const isFormData = options?.body instanceof FormData;
  const res = await fetch(url, {
    headers: isFormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

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
  | "preparing" | "ready_to_apply";

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
  // Agentic fields
  agent_score: number | null;
  agent_created: boolean;
  approval_status: string | null;
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

export interface TailoredCV {
  summary: string;
  skills: Array<{ display_name?: string; items?: string[] }>;
  experience: TailoredExperience[];
  certifications: string[];
  ats_keywords_embedded: string[];
  tailoring_notes: string;
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
  applicationId: string,
  jdText: string,
  variant = "A",
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>(`/api/tailor/generate`, {
    method: "POST",
    body: JSON.stringify({ application_id: applicationId, variant, jd_text: jdText }),
  });
}

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

export async function downloadDocument(documentId: string): Promise<void> {
  const url = `${API_BASE}/api/tailor/document/${documentId}/download`;
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  link.click();
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
  config: SessionConfig;
}

export interface QuestionPresentation {
  id: string;
  text: string;
  category: string;
  difficulty: string;
  context: string | null;
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
  order_in_session: number;
}

export interface AnswerEvaluation {
  scores: Record<string, number>;
  overall: number;
  feedback: string;
  strengths: string[];
  improvements: string[];
  follow_up_question: string | null;
  speech_coaching: string[];
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
}

export interface SessionListItem {
  id: string;
  company_name: string;
  role_title: string;
  status: string;
  overall_score: number | null;
  created_at: string;
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
  strengths: string[];
  improvements: string[];
}

export interface SessionFeedbackReport {
  session_id: string;
  overall_score: number;
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
  status: "pending"
  type: string
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

export async function fetchResumeStatus(): Promise<ResumeStatus> {
  return apiFetch<ResumeStatus>("/api/resume/status");
}

export async function uploadResume(file: File): Promise<ResumeStatus> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ResumeStatus>("/api/resume/upload", {
    method: "POST",
    body: formData,
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

// ── Settings / API key management ───────────────────────────────────

export interface ProviderStatus {
  env_var: string | null;
  set: boolean;
  masked: string | null;
}

export interface EnvStatus {
  configured_providers: Record<string, ProviderStatus>;
  current_provider: string;
  tier: string;
  api_keys_file: string;
}

export async function fetchEnvStatus(): Promise<EnvStatus> {
  return apiFetch<EnvStatus>('/api/v2/settings/env/status');
}

export interface SaveApiKeyResult {
  valid: boolean;
  provider?: string;
  models_available?: string[];
  tier?: string;
  error?: string;
}

export async function saveApiKey(keyName: string, keyValue: string): Promise<SaveApiKeyResult> {
  return apiFetch<SaveApiKeyResult>('/api/v2/settings/env', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key_name: keyName, key_value: keyValue }),
  });
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
}

export async function fetchScoringInsights(): Promise<ScoringInsights> {
  return apiFetch<ScoringInsights>("/api/v2/scoring/insights");
}

// ── Assisted Apply ──────────────────────────────────────────────────────────

export interface ApplicationPackage {
  job_id: string;
  job_url: string;
  cv_path: string | null;
  cover_letter_path: string | null;
  prefill_map: Record<string, string>;
}

export async function prepareApplication(applicationId: string): Promise<ApplicationPackage> {
  return apiFetch<ApplicationPackage>(`/api/applications/${applicationId}/prepare`, {
    method: "POST",
  });
}

export async function downloadInterviewIcs(interviewId: string): Promise<void> {
  const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  const url = `${BASE}/api/v2/interviews/${interviewId}/ical`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to download .ics: ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `interview_${interviewId}.ics`;
  a.click();
  URL.revokeObjectURL(a.href);
}
