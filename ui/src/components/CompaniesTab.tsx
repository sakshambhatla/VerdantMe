import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  discoverCompaniesStream,
  getCompanies,
  getCompanyRun,
  getCompanyRuns,
  getResume,
  type CompanyRun,
  type CompanyRunSummary,
  type DiscoveredCompany,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { MotivationChat } from "@/components/MotivationChat";

const ATS_COLORS: Record<string, string> = {
  greenhouse: "bg-emerald-500/20 text-emerald-300 border border-emerald-400/30",
  lever:      "bg-blue-500/20    text-blue-300    border border-blue-400/30",
  ashby:      "bg-violet-500/20  text-violet-300  border border-violet-400/30",
  workday:    "bg-orange-500/20  text-orange-300  border border-orange-400/30",
  linkedin:   "bg-sky-500/20     text-sky-300     border border-sky-400/30",
  unknown:    "bg-white/10       text-white/60    border border-white/20",
};

const glassTableStyle = {
  background: "rgba(255,255,255,0.05)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
  borderColor: "rgba(255,255,255,0.15)",
};

const glassSelectStyle = {
  background: "rgba(255,255,255,0.10)",
  backdropFilter: "blur(4px)",
  WebkitBackdropFilter: "blur(4px)",
  border: "1px solid rgba(255,255,255,0.20)",
};

function CompanyTable({ companies }: { companies: DiscoveredCompany[] }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={glassTableStyle}>
      <table className="w-full text-sm">
        <thead className="border-b" style={{ background: "rgba(255,255,255,0.08)", borderColor: "rgba(255,255,255,0.12)" }}>
          <tr>
            <th className="px-4 py-3 text-left font-medium text-white/80">Company</th>
            <th className="px-4 py-3 text-left font-medium text-white/80">ATS</th>
            <th className="px-4 py-3 text-left font-medium text-white/80">Why it's a fit</th>
            <th className="px-4 py-3 text-left font-medium text-white/80">Career Page</th>
          </tr>
        </thead>
        <tbody style={{ borderColor: "rgba(255,255,255,0.08)" }}>
          {companies.map((c) => (
            <tr
              key={c.name}
              className="transition-colors"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.07)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}
            >
              <td className="px-4 py-3 font-medium text-white">{c.name}</td>
              <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${ATS_COLORS[c.ats_type] ?? ATS_COLORS.unknown}`}>
                  {c.ats_type}
                </span>
              </td>
              <td className="px-4 py-3 text-white/60 max-w-xs">{c.reason}</td>
              <td className="px-4 py-3">
                <a
                  href={c.career_page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2 text-xs"
                  style={{ color: "rgba(147,210,255,0.85)" }}
                >
                  Open ↗
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Run History ──────────────────────────────────────────────────────────────

const RUNS_PER_PAGE = 5;

function RunCard({ summary }: { summary: CompanyRunSummary }) {
  const [expanded, setExpanded] = useState(false);
  const { data: run, isFetching } = useQuery<CompanyRun>({
    queryKey: ["company-run", summary.id],
    queryFn: () => getCompanyRun(summary.id),
    enabled: expanded,
  });

  const date = new Date(summary.created_at).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });

  return (
    <div
      className="rounded-xl border"
      style={{
        background: "rgba(255,255,255,0.05)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        borderColor: "rgba(255,255,255,0.12)",
      }}
    >
      {/* Summary row */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-semibold text-white text-sm">{summary.run_name}</span>
          <Badge className="text-[10px] bg-white/10 text-white/55 border border-white/20">
            {summary.source_type === "seed" ? "seed" : "resume"}
          </Badge>
          {summary.focus === "startups" && (
            <Badge className="text-[10px] bg-orange-500/15 text-orange-300 border border-orange-400/25">
              startups
            </Badge>
          )}
          <span className="text-xs text-white/45 tabular-nums">
            {summary.company_count} {summary.company_count === 1 ? "company" : "companies"}
          </span>
          <span className="text-xs text-white/35">{date}</span>
        </div>
        <span className="text-white/40 text-sm ml-2 shrink-0">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {/* Expanded company table */}
      {expanded && (
        <div className="px-4 pb-4">
          {isFetching ? (
            <div className="flex items-center gap-2 py-4 text-white/45 text-sm">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white/80" />
              Loading…
            </div>
          ) : run && run.companies.length > 0 ? (
            <CompanyTable companies={run.companies} />
          ) : (
            <p className="text-white/35 text-sm py-4 text-center">No companies in this run.</p>
          )}
        </div>
      )}
    </div>
  );
}

function RunHistory() {
  const [page, setPage] = useState(1);

  const { data, isFetching } = useQuery({
    queryKey: ["company-runs", page],
    queryFn: () => getCompanyRuns(page, RUNS_PER_PAGE),
    retry: false,
  });

  if (!data && !isFetching) return null;
  if (data && data.total === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide">
          Previous Runs
        </h3>
        {isFetching && (
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white/70" />
        )}
      </div>

      {data && data.runs.length > 0 && (
        <>
          <div className="space-y-2">
            {data.runs.map((run) => (
              <RunCard key={run.id} summary={run} />
            ))}
          </div>

          {/* Pagination */}
          {data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-4 pt-1">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                style={{
                  background: "rgba(255,255,255,0.10)",
                  border: "1px solid rgba(255,255,255,0.20)",
                  color: "rgba(255,255,255,0.75)",
                }}
              >
                ← Previous
              </button>
              <span className="text-sm text-white/60 tabular-nums">
                Page {page} of {data.total_pages}
              </span>
              <button
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                style={{
                  background: "rgba(255,255,255,0.10)",
                  border: "1px solid rgba(255,255,255,0.20)",
                  color: "rgba(255,255,255,0.75)",
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Main tab ─────────────────────────────────────────────────────────────────

type DiscoveryMode = "resume" | "seed";
type CompanyFocus = "regular" | "startups";

function parseSeedCompanies(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function CompaniesTab() {
  const qc = useQueryClient();
  const [maxCompanies, setMaxCompanies] = useState<string>("20");
  const [provider, setProvider] = useState<string>("gemini");
  const [mode, setMode] = useState<DiscoveryMode>("resume");
  const [seedInput, setSeedInput] = useState<string>("");
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [focus, setFocus] = useState<CompanyFocus>("regular");
  const [error, setError] = useState<string | null>(null);

  // Load resumes for the selector
  const { data: resumeData } = useQuery({
    queryKey: ["resume"],
    queryFn: getResume,
    retry: false,
  });
  const resumes = resumeData?.resumes ?? [];

  const { data: cached } = useQuery({
    queryKey: ["companies"],
    queryFn: getCompanies,
    retry: false,
  });

  const discover = useMutation({
    mutationFn: () => {
      const seeds = mode === "seed" ? parseSeedCompanies(seedInput) : undefined;
      const resume_id =
        mode === "resume"
          ? selectedResumeId || undefined
          : undefined;
      return discoverCompaniesStream({
        max_companies: maxCompanies ? parseInt(maxCompanies, 10) : undefined,
        model_provider: provider || undefined,
        seed_companies: seeds && seeds.length > 0 ? seeds : undefined,
        resume_id,
        focus: mode === "resume" ? focus : undefined,
      });
    },
    onSuccess: (data) => {
      qc.setQueryData(["companies"], data);
      // Invalidate run history so the new run appears
      qc.invalidateQueries({ queryKey: ["company-runs"] });
      setError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      setError(err.response?.data?.detail ?? err.message);
    },
  });

  const companies = discover.data?.companies ?? cached?.companies ?? [];
  const isSeedMode = mode === "seed";
  const latestRunName = discover.data?.run_name;

  const canDiscover =
    !discover.isPending &&
    (isSeedMode
      ? parseSeedCompanies(seedInput).length > 0
      : resumes.length > 0);

  return (
    <div className="space-y-6">
      {/* Config form */}
      <Card>
        <CardContent className="pt-6 space-y-4">
          {/* Mode toggle */}
          <div className="space-y-1.5">
            <Label className="text-white/75">Discovery Mode</Label>
            <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "rgba(255,255,255,0.20)", width: "fit-content" }}>
              {(["resume", "seed"] as DiscoveryMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className="px-4 py-1.5 text-sm font-medium transition-colors"
                  style={{
                    background: mode === m ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.06)",
                    color: mode === m ? "white" : "rgba(255,255,255,0.50)",
                    cursor: "pointer",
                  }}
                >
                  {m === "resume" ? "From Resume" : "From Seed List"}
                </button>
              ))}
            </div>
          </div>

          {/* Resume selector (resume mode only) */}
          {!isSeedMode && resumes.length > 0 && (
            <div className="space-y-1.5">
              <Label htmlFor="resume-select" className="text-white/75">
                Active Resume
              </Label>
              <select
                id="resume-select"
                value={selectedResumeId || resumes[0]?.id}
                onChange={(e) => setSelectedResumeId(e.target.value)}
                className="flex h-8 w-72 rounded-lg px-3 py-1 text-sm text-white transition-colors outline-none focus-visible:ring-2 focus-visible:ring-white/20"
                style={glassSelectStyle}
              >
                {resumes.map((r) => (
                  <option
                    key={r.id}
                    value={r.id}
                    style={{ background: "#1b4332", color: "white" }}
                  >
                    {r.filename}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!isSeedMode && resumes.length === 0 && (
            <p className="text-sm text-amber-400/80 bg-amber-500/10 border border-amber-400/20 rounded-lg px-3 py-2">
              Upload a resume first in the Upload Resume tab.
            </p>
          )}

          {/* Company focus toggle (resume mode only) */}
          {!isSeedMode && (
            <div className="space-y-1.5">
              <Label className="text-white/75">Company Type</Label>
              <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "rgba(255,255,255,0.20)", width: "fit-content" }}>
                {(["regular", "startups"] as CompanyFocus[]).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFocus(f)}
                    className="px-4 py-1.5 text-sm font-medium transition-colors"
                    style={{
                      background: focus === f ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.06)",
                      color: focus === f ? "white" : "rgba(255,255,255,0.50)",
                      cursor: "pointer",
                    }}
                  >
                    {f === "regular" ? "Regular" : "Startups"}
                  </button>
                ))}
              </div>
              {focus === "startups" && (
                <p className="text-xs text-white/40">
                  Includes YC Jobs API results during role discovery
                </p>
              )}
            </div>
          )}

          {/* Motivation chat (optional — describe what you're looking for) */}
          <MotivationChat
            resumeId={!isSeedMode ? (selectedResumeId || resumes[0]?.id) : undefined}
            provider={provider}
          />

          {/* Seed input (only in seed mode) */}
          {isSeedMode && (
            <div className="space-y-1.5">
              <Label htmlFor="seed-companies" className="text-white/75">
                Seed Companies <span className="text-white/40 font-normal">(one per line or comma-separated)</span>
              </Label>
              <textarea
                id="seed-companies"
                rows={4}
                placeholder={"Zillow\nRedfin\nCompass"}
                value={seedInput}
                onChange={(e) => setSeedInput(e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm text-white resize-none outline-none focus-visible:ring-2 focus-visible:ring-white/20"
                style={{ ...glassSelectStyle, minWidth: "280px" }}
              />
            </div>
          )}

          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1.5">
              <Label htmlFor="max-companies" className="text-white/75">Max companies</Label>
              <Input
                id="max-companies"
                type="number"
                min={1}
                max={50}
                value={maxCompanies}
                onChange={(e) => setMaxCompanies(e.target.value)}
                className="w-28"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="provider" className="text-white/75">LLM Provider</Label>
              <select
                id="provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="flex h-8 w-36 rounded-lg px-3 py-1 text-sm text-white transition-colors outline-none focus-visible:ring-3 focus-visible:ring-white/20 focus-visible:border-white/40"
                style={glassSelectStyle}
              >
                <option value="gemini" style={{ background: "#1b4332", color: "white" }}>Gemini</option>
                <option value="anthropic" style={{ background: "#1b4332", color: "white" }}>Anthropic</option>
              </select>
            </div>
            <Button
              onClick={() => discover.mutate()}
              disabled={!canDiscover}
              className="self-end"
            >
              {discover.isPending ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                  Discovering…
                </>
              ) : (
                "Discover Companies"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {discover.isPending && (
        <div className="flex flex-col items-center gap-3 py-12 text-white/55">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/40 border-t-white/80" />
          {isSeedMode ? (
            <p className="text-sm">Finding companies similar to your seeds…</p>
          ) : (
            <p className="text-sm">Analyzing your resume and discovering companies…</p>
          )}
          <p className="text-xs text-white/40">This may take 20–40 seconds</p>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-300 bg-red-500/15 border border-red-400/25 rounded-lg px-4 py-2">{error}</p>
      )}

      {!discover.isPending && companies.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide">
              {companies.length} Companies
              {latestRunName && (
                <span className="ml-2 font-normal normal-case text-white/40">
                  — run: <span className="text-white/60 font-semibold">{latestRunName}</span>
                </span>
              )}
            </h3>
            <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
              {discover.data ? "Fresh" : "Cached"}
            </Badge>
          </div>
          <CompanyTable companies={companies} />
        </div>
      )}

      {/* Run History */}
      <RunHistory />
    </div>
  );
}
