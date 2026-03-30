import axios from "axios";
import { supabase } from "@/lib/supabase";

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || "/api" });

// Attach Supabase JWT to every request when in managed mode
api.interceptors.request.use(async (config) => {
  const mode = localStorage.getItem("verdantme-mode");
  if (supabase && mode === "managed") {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`;
    }
  }
  return config;
});

// On 401, try refreshing the JWT before signing out — only in managed mode.
// This handles the case where the access token expires mid-request (e.g. during
// a slow Gemini key validation call).
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const mode = localStorage.getItem("verdantme-mode");
    if (error.response?.status === 401 && supabase && mode === "managed") {
      // Avoid infinite retry loops: only attempt refresh once per request.
      if (!error.config._retried) {
        const { data: { session }, error: refreshErr } =
          await supabase.auth.refreshSession();
        if (session && !refreshErr) {
          // Retry the original request with the fresh token.
          error.config._retried = true;
          error.config.headers.Authorization = `Bearer ${session.access_token}`;
          return api.request(error.config);
        }
      }
      // Refresh failed or already retried — session is truly expired.
      supabase.auth.signOut();
    }
    return Promise.reject(error);
  },
);

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ParsedResume {
  id: string;
  filename: string;
  skills: string[];
  job_titles: string[];
  years_of_experience: number | null;
  companies_worked_at: string[];
  education: string[];
  parsed_at: string;
}

export interface DiscoveredCompany {
  name: string;
  reason: string;
  career_page_url: string;
  ats_type: string;
  discovered_at: string;
}

export interface CompanyRunSummary {
  id: string;
  run_name: string;
  source_type: "resume" | "seed";
  source_id: string;
  focus?: string | null;
  company_count: number;
  created_at: string;
}

export interface CompanyRun {
  id: string;
  run_name: string;
  source_type: "resume" | "seed";
  source_id: string;
  focus?: string | null;
  seed_companies: string[] | null;
  companies: DiscoveredCompany[];
  created_at: string;
}

export interface CompanyRunsPage {
  runs: CompanyRunSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DiscoveredRole {
  company_name: string;
  title: string;
  location: string;
  url: string;
  ats_type: string;
  department: string | null;
  posted_at: string | null;
  published_at: string | null;
  relevance_score: number | null;
  filter_score: number | null;
  summary: string | null;
}

export interface FlaggedCompany {
  name: string;
  ats_type: string;
  career_page_url: string;
  reason: string;
}

export interface RolesResponse {
  fetched_at: string;
  total_roles: number;
  roles_after_filter: number;
  companies_fetched: number;
  companies_flagged: number;
  flagged_companies: FlaggedCompany[];
  roles: DiscoveredRole[];
  in_progress?: boolean;
  job_run_id?: string;
  job_run_name?: string;
}

export interface JobRunMetrics {
  companies_total: number;
  companies_succeeded: number;
  companies_failed: number;
  ats_visits: Record<string, number>;
  jobs_per_ats: Record<string, number>;
  jobs_per_company: Record<string, number>;
  career_page_per_company: Record<string, number>;
  playwright_uses: number;
  browser_agent_uses: number;
  total_roles_fetched: number;
  total_roles_after_filter: number;
  total_roles_after_score: number;
  filter_batches: number;
  score_batches: number;
  errors: string[];
  elapsed_seconds: number;
}

export interface JobRun {
  id: string;
  run_name: string;
  company_run_id: string | null;
  parent_job_run_id: string | null;
  run_type: string;
  status: string;
  companies_input: string[];
  metrics: JobRunMetrics;
  created_at: string;
  completed_at: string | null;
}

export interface JobRunsPage {
  runs: JobRun[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ─── Resume ───────────────────────────────────────────────────────────────────

export async function uploadResume(file: File): Promise<{ resumes: ParsedResume[] }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<{ resumes: ParsedResume[] }>("/resume/upload", form);
  return data;
}

export async function getResume(): Promise<{ resumes: ParsedResume[] }> {
  const { data } = await api.get<{ resumes: ParsedResume[] }>("/resume");
  return data;
}

export async function deleteResume(filename: string): Promise<{ resumes: ParsedResume[] }> {
  const { data } = await api.delete<{ resumes: ParsedResume[] }>(`/resume/${encodeURIComponent(filename)}`);
  return data;
}

// ─── Companies ────────────────────────────────────────────────────────────────

export interface DiscoverCompaniesParams {
  max_companies?: number;
  model_provider?: string;
  seed_companies?: string[];
  resume_id?: string;
  focus?: string;
}

export interface DiscoverCompaniesResponse {
  companies: DiscoveredCompany[];
  run_id: string;
  run_name: string;
  discovered_at: string;
}

export async function discoverCompanies(
  params: DiscoverCompaniesParams
): Promise<DiscoverCompaniesResponse> {
  const { data } = await api.post<DiscoverCompaniesResponse>(
    "/companies/discover",
    params,
    { timeout: 180_000 } // 3 min — LLM batches + parallel URL validation
  );
  return data;
}

/**
 * SSE-streaming version of discoverCompanies.
 *
 * Uses POST + fetch (not EventSource) so we can send a JSON body.
 * The server sends keepalive pings every 15 s, preventing proxy timeouts.
 */
export async function discoverCompaniesStream(
  params: DiscoverCompaniesParams,
  onProgress?: (message: string) => void,
): Promise<DiscoverCompaniesResponse> {
  const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  const mode = localStorage.getItem("verdantme-mode");
  if (supabase && mode === "managed") {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      headers["Authorization"] = `Bearer ${session.access_token}`;
    }
  }

  const resp = await fetch(`${baseURL}/companies/discover/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(params),
  });

  if (!resp.ok) {
    const text = await resp.text();
    let detail: string;
    try { detail = JSON.parse(text).detail; } catch { detail = text; }
    throw { response: { data: { detail } }, message: detail };
  }

  const reader = resp.body?.getReader();
  if (!reader) throw { message: "No response body" };

  const decoder = new TextDecoder();
  let buffer = "";
  let result: DiscoverCompaniesResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      let eventType = "";
      let dataStr = "";
      for (const line of part.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!eventType || !dataStr) continue;

      if (eventType === "progress") {
        try {
          const parsed = JSON.parse(dataStr);
          onProgress?.(parsed.message);
        } catch { /* ignore malformed progress */ }
      } else if (eventType === "done") {
        result = JSON.parse(dataStr) as DiscoverCompaniesResponse;
      } else if (eventType === "error") {
        const parsed = JSON.parse(dataStr);
        throw { response: { data: { detail: parsed.detail } }, message: parsed.detail };
      }
    }
  }

  // Drain any remaining buffered event (stream may close without trailing blank line)
  if (buffer.trim()) {
    for (const part of buffer.split(/\r?\n\r?\n/)) {
      if (!part.trim()) continue;
      let eventType = "";
      let dataStr = "";
      for (const line of part.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (eventType === "done" && dataStr) {
        result = JSON.parse(dataStr) as DiscoverCompaniesResponse;
      } else if (eventType === "error" && dataStr) {
        const parsed = JSON.parse(dataStr);
        throw { response: { data: { detail: parsed.detail } }, message: parsed.detail };
      }
    }
  }

  if (!result) throw { message: "Stream ended without a result" };
  return result;
}

export async function getCompanyRuns(
  page = 1,
  pageSize = 10
): Promise<CompanyRunsPage> {
  const { data } = await api.get<CompanyRunsPage>("/company-runs", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function getCompanyRun(runId: string): Promise<CompanyRun> {
  const { data } = await api.get<CompanyRun>(`/company-runs/${encodeURIComponent(runId)}`);
  return data;
}

export async function getCompanies(): Promise<{ companies: DiscoveredCompany[] }> {
  const { data } = await api.get<{ companies: DiscoveredCompany[] }>("/companies");
  return data;
}

export interface CompanyRegistryEntry {
  name: string;
  ats_type: string;
  ats_board_token: string | null;
  career_page_url: string;
  searchable: boolean | null;  // null=untested; true=LLM found jobs; false=failed
}

export async function getCompanyRegistry(): Promise<CompanyRegistryEntry[]> {
  const { data } = await api.get<{ companies: CompanyRegistryEntry[] }>("/companies/registry");
  return data.companies;
}

// ─── Roles ────────────────────────────────────────────────────────────────────

export interface RoleFiltersParams {
  title?: string;
  posted_after?: string;  // legacy natural-language date (CLI backward compat)
  posted_within_value?: number;   // deterministic: e.g. 2
  posted_within_unit?: "days" | "weeks" | "months";
  location?: string;
  confidence?: string;
  filter_strategy?: "llm" | "fuzzy" | "semantic" | "gemini-embedding";
}

export interface DiscoverRolesParams {
  company_names?: string[];
  company_run_id?: string;
  refresh?: boolean;
  resume?: boolean;
  use_cache?: boolean;
  role_filters?: RoleFiltersParams;
  relevance_score_criteria?: string;
  model_provider?: string;
  skip_career_page?: boolean;
  enable_yc_jobs?: boolean;
  enable_theirstack?: boolean;
  theirstack_max_results?: number;
}

export interface RolesCheckpoint {
  exists: boolean;
  phase: string;
  filter_batches_done: number;
  filter_total_batches: number;
  raw_roles_count: number;
  filter_kept_count: number;
  summary: string;
}

export async function discoverRoles(params: DiscoverRolesParams): Promise<RolesResponse> {
  const { data } = await api.post<RolesResponse>("/roles/discover", params);
  return data;
}

/**
 * SSE-streaming version of discoverRoles.
 *
 * Uses POST + fetch (not EventSource) so we can send a JSON body.
 * The server sends keepalive pings every 15 s, preventing proxy timeouts.
 */
export async function discoverRolesStream(
  params: DiscoverRolesParams,
  onProgress?: (message: string) => void,
  onFilterResult?: (kept: number, total: number) => void,
): Promise<RolesResponse> {
  const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  // Attach JWT in managed mode (mirrors the axios interceptor)
  const mode = localStorage.getItem("verdantme-mode");
  if (supabase && mode === "managed") {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      headers["Authorization"] = `Bearer ${session.access_token}`;
    }
  }

  const resp = await fetch(`${baseURL}/roles/discover/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(params),
  });

  if (!resp.ok) {
    const text = await resp.text();
    let detail: string;
    try { detail = JSON.parse(text).detail; } catch { detail = text; }
    throw { response: { data: { detail } }, message: detail };
  }

  const reader = resp.body?.getReader();
  if (!reader) throw { message: "No response body" };

  const decoder = new TextDecoder();
  let buffer = "";
  let result: RolesResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from the buffer
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      let eventType = "";
      let dataStr = "";
      for (const line of part.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
        // Ignore comments (keepalive pings starting with ":")
      }
      if (!eventType || !dataStr) continue;

      if (eventType === "progress") {
        try {
          const parsed = JSON.parse(dataStr);
          onProgress?.(parsed.message);
        } catch { /* ignore malformed progress */ }
      } else if (eventType === "filter_result") {
        try {
          const parsed = JSON.parse(dataStr);
          onFilterResult?.(parsed.kept as number, parsed.total as number);
        } catch { /* ignore malformed filter_result */ }
      } else if (eventType === "done") {
        result = JSON.parse(dataStr) as RolesResponse;
      } else if (eventType === "error") {
        const parsed = JSON.parse(dataStr);
        throw { response: { data: { detail: parsed.detail } }, message: parsed.detail };
      }
    }
  }

  // Drain any remaining buffered event (stream may close without trailing blank line)
  if (buffer.trim()) {
    for (const part of buffer.split(/\r?\n\r?\n/)) {
      if (!part.trim()) continue;
      let eventType = "";
      let dataStr = "";
      for (const line of part.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (eventType === "done" && dataStr) {
        result = JSON.parse(dataStr) as RolesResponse;
      } else if (eventType === "error" && dataStr) {
        const parsed = JSON.parse(dataStr);
        throw { response: { data: { detail: parsed.detail } }, message: parsed.detail };
      }
    }
  }

  if (!result) throw { message: "Stream ended without a result" };
  return result;
}

export async function getRoles(): Promise<RolesResponse> {
  const { data } = await api.get<RolesResponse>("/roles");
  return data;
}

export async function getUnfilteredRoles(): Promise<RolesResponse> {
  const { data } = await api.get<RolesResponse>("/roles/unfiltered");
  return data;
}

export async function getRolesCheckpoint(): Promise<RolesCheckpoint | null> {
  try {
    const { data } = await api.get<RolesCheckpoint>("/roles/checkpoint");
    return data;
  } catch {
    return null;
  }
}

// ─── Job Runs ─────────────────────────────────────────────────────────────────

export async function getJobRuns(
  page = 1,
  pageSize = 10
): Promise<JobRunsPage> {
  const { data } = await api.get<JobRunsPage>("/job-runs", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function getJobRun(runId: string): Promise<JobRun> {
  const { data } = await api.get<JobRun>(`/job-runs/${encodeURIComponent(runId)}`);
  return data;
}

export interface BrowserFetchResult {
  company_name: string;
  roles_found: number;
  roles: DiscoveredRole[];
}

export async function fetchBrowserRoles(
  company_name: string
): Promise<BrowserFetchResult> {
  const { data } = await api.post<BrowserFetchResult>("/roles/fetch-browser", {
    company_name,
  });
  return data;
}

// ─── Browser Agent Streaming (SSE) ────────────────────────────────────────────

export interface BrowserAgentMetrics {
  company_name: string;
  steps_taken: number;
  jobs_collected: number;
  jobs_announced?: number;
  rate_limit_hits: number;
  elapsed_seconds: number;
  status: string;
}

/** SSE payload: new batch of jobs found by the agent */
export interface BrowserAgentJobsBatchEvent {
  type: "jobs_batch";
  jobs: DiscoveredRole[];
  total_so_far: number;
}

/** SSE payload: LLM filter pipeline processed a batch */
export interface BrowserAgentFilterResultEvent {
  type: "filter_result";
  filtered: DiscoveredRole[];
  kept: number;
  dropped: number;
}

/** SSE payload: clean completion */
export interface BrowserAgentDoneEvent {
  type: "done";
  metrics: BrowserAgentMetrics;
}

/** SSE payload: relevance scoring completed, emitted just before done/killed */
export interface BrowserAgentScoreResultEvent {
  type: "score_result";
  scored: number;
}

/** SSE payload: agent killed by time limit or user request */
export interface BrowserAgentKilledEvent {
  type: "killed";
  reason: "user_request" | "time_limit";
  partial_jobs: number;
  metrics: BrowserAgentMetrics;
}

/** SSE payload: agent encountered an unrecoverable error */
export interface BrowserAgentErrorEvent {
  type: "error";
  error_type: string;
  message: string;
  can_resume: boolean;
}

/**
 * Build the SSE URL for a company's browser-agent stream.
 * Pass this to `new EventSource(url)` — do NOT use axios for SSE.
 *
 * @param careerPageUrlOverride  Provide when the registry has no career page URL
 *   for the company (e.g. Workday companies). The backend will use this URL
 *   instead of the one in the registry.
 */
/**
 * Build the SSE URL for a company's browser-agent stream.
 * Pass this to `new EventSource(url)` — do NOT use axios for SSE.
 *
 * When Supabase auth is configured, the JWT is appended as a query param
 * because EventSource doesn't support custom headers.
 */
export async function browserAgentStreamUrl(
  company_name: string,
  careerPageUrlOverride?: string,
): Promise<string> {
  const _base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
  let url = `${_base}/roles/fetch-browser/stream?company_name=${encodeURIComponent(company_name)}`;
  if (careerPageUrlOverride) {
    url += `&career_page_url_override=${encodeURIComponent(careerPageUrlOverride)}`;
  }
  // EventSource doesn't support custom headers — append JWT as query param (managed mode only)
  const mode = localStorage.getItem("verdantme-mode");
  if (supabase && mode === "managed") {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      url += `&token=${encodeURIComponent(session.access_token)}`;
    }
  }
  return url;
}

// ─── API Keys (Settings) ──────────────────────────────────────────────────────

export interface ApiKeyStatus {
  anthropic: boolean;
  gemini: boolean;
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const { data } = await api.get<ApiKeyStatus>("/settings/api-keys");
  return data;
}

export async function storeApiKey(
  provider: "anthropic" | "gemini",
  apiKey: string
): Promise<void> {
  await api.post("/settings/api-keys", { provider, api_key: apiKey });
}

export async function deleteApiKey(
  provider: "anthropic" | "gemini"
): Promise<void> {
  await api.delete(`/settings/api-keys/${provider}`);
}

export async function validateStoredApiKey(
  provider: "anthropic" | "gemini"
): Promise<void> {
  await api.post(`/settings/api-keys/${provider}/validate`);
}

// ─── Motivation Chat ──────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface UserMotivation {
  resume_id: string | null;
  chat_history: ChatMessage[];
  summary: string;
  status: "in_progress" | "completed";
  created_at: string;
  updated_at: string;
}

export interface MotivationChatResponse {
  reply: string;
  ready: boolean;
  summary?: string;
  status: string;
  chat_history: ChatMessage[];
}

export async function sendMotivationChat(
  message: string,
  resumeId?: string,
  modelProvider?: string,
): Promise<MotivationChatResponse> {
  const body: Record<string, unknown> = { message };
  if (resumeId) body.resume_id = resumeId;
  if (modelProvider) body.model_provider = modelProvider;
  const { data } = await api.post<MotivationChatResponse>("/motivation/chat", body);
  return data;
}

export async function getMotivation(): Promise<UserMotivation | null> {
  try {
    const { data } = await api.get<UserMotivation>("/motivation");
    return data;
  } catch {
    return null;
  }
}

export async function deleteMotivation(): Promise<void> {
  await api.delete("/motivation");
}

// ─── Browser Agent ───────────────────────────────────────────────────────────

// ─── Pipeline ────────────────────────────────────────────────────────────────

export type PipelineStage =
  | "not_started"
  | "outreach"
  | "recruiter"
  | "hm_screen"
  | "onsite"
  | "offer"
  | "blocked"
  | "rejected"
  | "archived"
  | "deleted";

export type PipelineBadge = "done" | "new" | "panel" | "await" | "sched";

export interface PipelineEntry {
  id: string;
  company_name: string;
  role_title: string | null;
  stage: PipelineStage;
  note: string;
  next_action: string | null;
  badge: PipelineBadge | null;
  tags: string[];
  sort_order: number;
  source: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineUpdate {
  id: string;
  entry_id: string;
  update_type: "note" | "stage_change" | "created";
  from_stage: string | null;
  to_stage: string | null;
  message: string;
  created_at: string;
}

export interface PipelineStats {
  stage_counts: Partial<Record<PipelineStage, number>>;
  total: number;
}

export async function getPipelineEntries(
  stage?: PipelineStage,
): Promise<{ entries: PipelineEntry[]; total: number }> {
  const { data } = await api.get("/pipeline/entries", {
    params: stage ? { stage } : {},
  });
  return data;
}

export async function getPipelineEntry(id: string): Promise<PipelineEntry> {
  const { data } = await api.get(`/pipeline/entries/${encodeURIComponent(id)}`);
  return data;
}

export async function createPipelineEntry(
  entry: {
    company_name: string;
    role_title?: string | null;
    stage?: PipelineStage;
    note?: string;
    next_action?: string | null;
    badge?: PipelineBadge | null;
    tags?: string[];
  },
): Promise<PipelineEntry> {
  const { data } = await api.post("/pipeline/entries", entry);
  return data;
}

export async function updatePipelineEntry(
  id: string,
  updates: Partial<PipelineEntry>,
): Promise<PipelineEntry> {
  const { data } = await api.put(
    `/pipeline/entries/${encodeURIComponent(id)}`,
    updates,
  );
  return data;
}

export async function deletePipelineEntry(id: string): Promise<void> {
  await api.delete(`/pipeline/entries/${encodeURIComponent(id)}`);
}

export async function reorderPipelineEntries(
  moves: Array<{ id: string; stage: string; sort_order: number }>,
): Promise<void> {
  await api.post("/pipeline/entries/reorder", { moves });
}

export async function getPipelineUpdates(
  entryId?: string,
  limit = 50,
): Promise<{ updates: PipelineUpdate[]; total: number }> {
  const { data } = await api.get("/pipeline/updates", {
    params: { ...(entryId ? { entry_id: entryId } : {}), limit },
  });
  return data;
}

export async function createPipelineUpdate(
  entryId: string,
  message: string,
): Promise<PipelineUpdate> {
  const { data } = await api.post("/pipeline/updates", {
    entry_id: entryId,
    message,
  });
  return data;
}

export async function getPipelineStats(): Promise<PipelineStats> {
  const { data } = await api.get("/pipeline/stats");
  return data;
}

// ─── Google Integration ─────────────────────────────────────────────────────

export async function getGoogleTokenStatus(): Promise<{ connected: boolean }> {
  const { data } = await api.get("/settings/google-tokens");
  return data;
}

export async function storeGoogleTokens(
  accessToken: string,
  refreshToken: string = "",
): Promise<void> {
  await api.post("/settings/google-tokens", {
    access_token: accessToken,
    refresh_token: refreshToken,
  });
}

export async function deleteGoogleTokens(): Promise<void> {
  await api.delete("/settings/google-tokens");
}

// ─── Pipeline Sync ──────────────────────────────────────────────────────────

export interface GmailSignal {
  company_name: string;
  signal_type: string;
  subject: string;
  snippet: string;
  date: string;
  is_new_company: boolean;
  source: "gmail" | "linkedin";
}

export interface CalendarSignal {
  company_name: string | null;
  event_type: string;
  title: string;
  start_time: string;
  end_time: string;
  organizer: string | null;
  status: string;
}

export interface PipelineSuggestion {
  id: string;
  entry_id: string | null;
  company_name: string;
  suggested_stage: string | null;
  suggested_badge: string | null;
  suggested_next_action: string | null;
  reason: string;
  confidence: string;
  source: string;
}

/** Frontend view model for the 3-column sync review modal.
 *  Built from PipelineSuggestion + signal data. Maps 1:1 to PipelineEntry
 *  fields shown on Kanban cards. The conversion layer is swappable —
 *  today it's LLM/rule-based, later it could be something else. */
export interface JobUpdate {
  id: string;
  source: "gmail" | "calendar";
  company_name: string;
  stage: string;
  badge: string | null;
  next_action: string | null;
  note: string;
  updated_at: string;
  recommendation: "add" | "update" | "ignore";
  // Original signal context for the left column
  signal_type: string;
  signal_subject: string;
  signal_date: string;
  // Back-reference to apply via existing backend
  entry_id: string | null;
  confidence: string;
  // Current stage of the entry (null for new companies)
  current_stage: string | null;
}

export interface SyncResult {
  gmail_signals: GmailSignal[];
  calendar_signals: CalendarSignal[];
  suggestions: PipelineSuggestion[];
  new_companies: PipelineSuggestion[];
  summary: string | null;
  google_connected: boolean;
  google_auth_expired: boolean;
  llm_available: boolean;
}

export async function syncPipeline(params?: {
  modelProvider?: string;
  lookback_days?: number;
  custom_phrases?: string[];
}): Promise<SyncResult> {
  const { data } = await api.post("/pipeline/sync", {
    ...(params?.modelProvider ? { model_provider: params.modelProvider } : {}),
    ...(params?.lookback_days ? { lookback_days: params.lookback_days } : {}),
    ...(params?.custom_phrases?.length
      ? { custom_phrases: params.custom_phrases }
      : {}),
  });
  return data;
}

export async function applySyncSuggestions(
  suggestions: PipelineSuggestion[],
  newCompanies: PipelineSuggestion[],
): Promise<{ applied: number; created: number }> {
  const { data } = await api.post("/pipeline/sync/apply", {
    suggestions: suggestions.map((s) => ({
      entry_id: s.entry_id,
      company_name: s.company_name,
      suggested_stage: s.suggested_stage,
      suggested_badge: s.suggested_badge,
      suggested_next_action: s.suggested_next_action,
      reason: s.reason,
      source: s.source,
    })),
    new_companies: newCompanies.map((c) => ({
      entry_id: null,
      company_name: c.company_name,
      suggested_stage: c.suggested_stage,
      suggested_next_action: c.suggested_next_action,
      reason: c.reason,
      source: c.source,
    })),
  });
  return data;
}

// ─── Offer Analysis ─────────────────────────────────────────────────────────

export interface OfferDimension {
  name: string;
  score: number; // 1-5
  weight: number; // 1.0 or 1.5
  rationale: string;
  flag: "red" | "yellow" | "green";
}

export interface OfferAnalysis {
  id: string;
  company_name: string;
  personal_context: string;
  dimensions: OfferDimension[];
  weighted_score: number | null;
  raw_average: number | null;
  verdict: string | null;
  key_question: string | null;
  flags: { red: number; yellow: number; green: number };
  model_provider: string | null;
  model_name: string | null;
  created_at: string;
  updated_at: string;
}

export async function getOfferEntries(): Promise<{
  entries: PipelineEntry[];
  total: number;
}> {
  const { data } = await api.get("/pipeline/offers");
  return data;
}

export async function getOfferAnalyses(): Promise<{
  analyses: OfferAnalysis[];
}> {
  const { data } = await api.get("/pipeline/offer-analyses");
  return data;
}

export async function analyzeOffer(
  companyName: string,
  personalContext: string,
  modelProvider?: string,
): Promise<OfferAnalysis> {
  const { data } = await api.post("/pipeline/offer-analyses", {
    company_name: companyName,
    personal_context: personalContext,
    model_provider: modelProvider,
  });
  return data;
}

export async function saveOfferContext(
  companyName: string,
  personalContext: string,
): Promise<void> {
  await api.put(
    `/pipeline/offer-context/${encodeURIComponent(companyName)}`,
    { company_name: companyName, personal_context: personalContext },
  );
}

// ─── User Role ───────────────────────────────────────────────────────────────

export type UserRole = "superuser" | "devtest" | "customer" | "guest";

export interface MeResponse {
  user_id: string | null;
  role: UserRole;
  display_name?: string;
}

export async function getMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/me");
  return data;
}

// ─── Analytics ──────────────────────────────────────────────────────────────

export interface AnalyticsSummary {
  days: number;
  total_views: number;
  unique_sessions: number;
  unique_users: number;
  views_per_page: Array<{ page: string; views: number }>;
  top_referrers: Array<{ referrer: string; count: number }>;
  views_over_time: Array<{ date: string; views: number }>;
}

export async function getAnalyticsSummary(
  days = 30
): Promise<AnalyticsSummary> {
  const { data } = await api.get<AnalyticsSummary>("/analytics/summary", {
    params: { days },
  });
  return data;
}

// ─── Browser Agent ───────────────────────────────────────────────────────────

/** Send a kill signal to a running browser agent. */
export async function killBrowserAgent(
  company_name: string
): Promise<{ killed: boolean; partial_jobs: number }> {
  const { data } = await api.delete<{ killed: boolean; partial_jobs: number }>(
    `/roles/fetch-browser/${encodeURIComponent(company_name)}`
  );
  return data;
}
