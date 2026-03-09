import axios from "axios";

const api = axios.create({ baseURL: "/api" });

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

// ─── Companies ────────────────────────────────────────────────────────────────

export interface DiscoverCompaniesParams {
  max_companies?: number;
  model_provider?: string;
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

export async function getRolesCheckpoint(): Promise<RolesCheckpoint | null> {
  try {
    const { data } = await api.get<RolesCheckpoint>("/roles/checkpoint");
    return data;
  } catch {
    return null;
  }
}
