import axios from "axios";
import { supabase } from "@/lib/supabase";

const api = axios.create({ baseURL: "/api" });

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

// Redirect to login on 401 (expired/invalid token) — only in managed mode
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const mode = localStorage.getItem("verdantme-mode");
    if (error.response?.status === 401 && supabase && mode === "managed") {
      supabase.auth.signOut();
    }
    return Promise.reject(error);
  },
);

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ParsedResume {
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
}

export async function discoverCompanies(
  params: DiscoverCompaniesParams
): Promise<{ companies: DiscoveredCompany[] }> {
  const { data } = await api.post<{ companies: DiscoveredCompany[] }>(
    "/companies/discover",
    params
  );
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
  posted_after?: string;
  location?: string;
  confidence?: string;
}

export interface DiscoverRolesParams {
  company_names?: string[];
  refresh?: boolean;
  resume?: boolean;
  use_cache?: boolean;
  role_filters?: RoleFiltersParams;
  relevance_score_criteria?: string;
  model_provider?: string;
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
  let url = `/api/roles/fetch-browser/stream?company_name=${encodeURIComponent(company_name)}`;
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

/** Send a kill signal to a running browser agent. */
export async function killBrowserAgent(
  company_name: string
): Promise<{ killed: boolean; partial_jobs: number }> {
  const { data } = await api.delete<{ killed: boolean; partial_jobs: number }>(
    `/roles/fetch-browser/${encodeURIComponent(company_name)}`
  );
  return data;
}
