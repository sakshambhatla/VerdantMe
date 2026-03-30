import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import {
  browserAgentStreamUrl,
  discoverRolesStream,
  getCompanyRuns,
  getJobRuns,
  killBrowserAgent,
  getRoles,
  getUnfilteredRoles,
  getRolesCheckpoint,
  getCompanyRegistry,
  type BrowserAgentMetrics,
  type CompanyRunSummary,
  type DiscoveredRole,
  type FlaggedCompany,
  type JobRun,
  type JobRunMetrics,
  type RolesResponse,
  type CompanyRegistryEntry,
} from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const col = createColumnHelper<DiscoveredRole>();

const columns = [
  col.accessor("relevance_score", {
    header: "Score",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return <span className="text-white/30">—</span>;
      const color = v >= 8 ? "text-emerald-400" : v >= 5 ? "text-yellow-400" : "text-white/35";
      return <span className={`font-bold tabular-nums ${color}`}>{v}</span>;
    },
    sortingFn: "basic",
  }),
  col.accessor("filter_score", {
    header: "Match",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return <span className="text-white/30">—</span>;
      const color = v >= 80 ? "text-emerald-400" : v >= 60 ? "text-yellow-400" : "text-orange-400";
      return <span className={`font-bold tabular-nums ${color}`}>{v}</span>;
    },
    sortingFn: "basic",
  }),
  col.accessor("company_name", {
    header: "Company",
    cell: (info) => <span className="text-white/90">{info.getValue()}</span>,
  }),
  col.accessor("title", {
    header: "Title",
    cell: (info) => <span className="font-medium text-white">{info.getValue()}</span>,
  }),
  col.accessor("location", {
    header: "Location",
    cell: (info) => <span className="text-white/65">{info.getValue()}</span>,
  }),
  col.accessor("summary", {
    header: "Summary",
    cell: (info) => (
      <span className="text-white/50 text-xs max-w-[220px] block">
        {info.getValue() ?? "—"}
      </span>
    ),
    enableSorting: false,
  }),
  col.accessor((row) => row.posted_at ?? row.published_at ?? null, {
    id: "posted",
    header: "Posted",
    cell: (info) => {
      const v = info.getValue();
      return <span className="text-white/45 text-xs">{v ? v.slice(0, 10) : "—"}</span>;
    },
  }),
  col.accessor("url", {
    header: "Apply",
    cell: (info) => (
      <a
        href={info.getValue()}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2 text-xs whitespace-nowrap"
        style={{ color: "rgba(147,210,255,0.85)" }}
      >
        Apply ↗
      </a>
    ),
    enableSorting: false,
  }),
];

const glassTableStyle = {
  background: "rgba(255,255,255,0.05)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
  borderColor: "rgba(255,255,255,0.15)",
};

function RolesTable({ roles }: { roles: DiscoveredRole[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "relevance_score", desc: true },
  ]);

  const table = useReactTable({
    data: roles,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="rounded-xl border overflow-auto" style={glassTableStyle}>
      <table className="w-full text-sm">
        <thead className="border-b" style={{ background: "rgba(255,255,255,0.08)", borderColor: "rgba(255,255,255,0.12)" }}>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`px-4 py-3 text-left font-medium whitespace-nowrap text-white/75 ${header.column.getCanSort() ? "cursor-pointer select-none hover:text-white" : ""}`}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="transition-colors"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.07)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Pagination helpers ─────────────────────────────────────────────────────

function PageSizeSelector({
  pageSize,
  setPageSize,
}: {
  pageSize: number;
  setPageSize: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-xs text-white/55">
      <span>Show</span>
      <select
        value={pageSize}
        onChange={(e) => setPageSize(Number(e.target.value))}
        className="h-7 rounded-md px-2 py-0.5 text-xs text-white outline-none focus-visible:ring-2 focus-visible:ring-white/20"
        style={{
          background: "rgba(255,255,255,0.10)",
          border: "1px solid rgba(255,255,255,0.20)",
        }}
      >
        <option value={20} style={{ background: "#1b4332", color: "white" }}>20</option>
        <option value={50} style={{ background: "#1b4332", color: "white" }}>50</option>
        <option value={100} style={{ background: "#1b4332", color: "white" }}>100</option>
      </select>
      <span>per page</span>
    </div>
  );
}

function PaginationControls({
  page,
  setPage,
  totalItems,
  pageSize,
}: {
  page: number;
  setPage: (n: number) => void;
  totalItems: number;
  pageSize: number;
}) {
  const totalPages = Math.ceil(totalItems / pageSize);
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-4 pt-4">
      <button
        disabled={page <= 1}
        onClick={() => setPage(page - 1)}
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
        Page {page} of {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => setPage(page + 1)}
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
  );
}

// ─── Browser-agent streaming state ───────────────────────────────────────────

type AgentStatus = "idle" | "running" | "done" | "killed" | "error";

interface CompanyAgentState {
  status: AgentStatus;
  jobsCollected: number;
  partialJobs?: number;
  scoredCount?: number;
  metrics?: BrowserAgentMetrics;
  errorMessage?: string;
}

/** Merge newly-arrived roles into an existing RolesResponse (dedup by URL). */
function mergeRolesIntoResponse(
  prev: RolesResponse | undefined,
  newRoles: DiscoveredRole[]
): RolesResponse {
  const empty: RolesResponse = {
    fetched_at: new Date().toISOString(),
    total_roles: newRoles.length,
    roles_after_filter: newRoles.length,
    companies_fetched: 0,
    companies_flagged: 0,
    flagged_companies: [],
    roles: newRoles,
  };
  if (!prev) return empty;
  const existingUrls = new Set(prev.roles.map((r) => r.url));
  const trulyNew = newRoles.filter((r) => !existingUrls.has(r.url));
  if (trulyNew.length === 0) return prev;
  return {
    ...prev,
    roles: [...prev.roles, ...trulyNew].sort(
      (a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0)
    ),
    total_roles: prev.total_roles + trulyNew.length,
    roles_after_filter: prev.roles_after_filter + trulyNew.length,
  };
}

function FlaggedBox({
  flagged,
  onDone,
}: {
  flagged: FlaggedCompany[];
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [agentStates, setAgentStates] = useState<Record<string, CompanyAgentState>>({});
  // Per-company custom URL, used when registry has no career_page_url
  const [customUrls, setCustomUrls] = useState<Record<string, string>>({});
  // One EventSource ref per company; cleanup happens inside event handlers
  const esRefs = useRef<Record<string, EventSource>>({});

  function updateState(
    name: string,
    updater: (prev: CompanyAgentState) => CompanyAgentState
  ) {
    setAgentStates((all) => ({
      ...all,
      [name]: updater(all[name] ?? { status: "idle", jobsCollected: 0 }),
    }));
  }

  async function startAgent(company: FlaggedCompany, urlOverride?: string) {
    if (esRefs.current[company.name]) return; // already running
    updateState(company.name, () => ({ status: "running", jobsCollected: 0 }));

    const url = await browserAgentStreamUrl(company.name, urlOverride);
    const es = new EventSource(url);
    esRefs.current[company.name] = es;

    es.addEventListener("jobs_batch", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      updateState(company.name, (prev) => ({
        ...prev,
        jobsCollected: data.total_so_far ?? prev.jobsCollected,
      }));
    });

    es.addEventListener("filter_result", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      if (data.filtered?.length) {
        qc.setQueryData(["roles"], (prev: RolesResponse | undefined) =>
          mergeRolesIntoResponse(prev, data.filtered)
        );
      }
    });

    es.addEventListener("score_result", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      updateState(company.name, (prev) => ({ ...prev, scoredCount: data.scored }));
    });

    es.addEventListener("done", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      updateState(company.name, (prev) => ({
        status: "done",
        jobsCollected: data.metrics?.jobs_collected ?? prev.jobsCollected,
        scoredCount: prev.scoredCount,
        metrics: data.metrics,
      }));
      es.close();
      delete esRefs.current[company.name];
      // Refresh after scoring — roles.json now has relevance_score set
      onDone();
    });

    es.addEventListener("killed", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      updateState(company.name, (prev) => ({
        status: "killed",
        jobsCollected: prev.jobsCollected,
        scoredCount: prev.scoredCount,
        partialJobs: data.partial_jobs,
        metrics: data.metrics,
      }));
      es.close();
      delete esRefs.current[company.name];
      // Refresh so scored partial roles saved to roles.json appear in the table
      onDone();
    });

    // "error" covers both our custom SSE error events and connection failures.
    // Custom events have .data; connection failures do not.
    es.addEventListener("error", (e) => {
      const msgEvent = e as MessageEvent;
      if (msgEvent.data) {
        const data = JSON.parse(msgEvent.data);
        updateState(company.name, (prev) => ({
          status: "error",
          jobsCollected: prev.jobsCollected,
          errorMessage: data.message ?? "Agent error",
        }));
      } else {
        updateState(company.name, (prev) => ({
          status: "error",
          jobsCollected: prev.jobsCollected,
          errorMessage: "Connection to agent lost.",
        }));
      }
      es.close();
      delete esRefs.current[company.name];
    });
  }

  async function killAgent(company: FlaggedCompany) {
    const es = esRefs.current[company.name];
    if (es) {
      es.close();
      delete esRefs.current[company.name];
    }
    // Optimistically mark as killed; the DELETE call signals the server
    updateState(company.name, (prev) => ({
      status: "killed",
      jobsCollected: prev.jobsCollected,
      partialJobs: prev.jobsCollected,
    }));
    try {
      await killBrowserAgent(company.name);
    } catch {
      // best-effort — agent may have already finished
    }
  }

  if (flagged.length === 0) return null;

  return (
    <div
      className="rounded-xl border p-4 space-y-4"
      style={{
        background: "rgba(234,179,8,0.10)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        borderColor: "rgba(234,179,8,0.30)",
      }}
    >
      <div>
        <p className="text-sm font-medium text-yellow-200">
          ⚠️ {flagged.length} {flagged.length === 1 ? "company" : "companies"} flagged — no public ATS API
        </p>
        <p className="text-xs text-yellow-300/60 mt-0.5">
          Use the browser agent below to attempt agentic role extraction. This is a separate manual step.
        </p>
      </div>

      <div className="space-y-3">
        {flagged.map((f) => {
          const state: CompanyAgentState = agentStates[f.name] ?? {
            status: "idle",
            jobsCollected: 0,
          };
          const isRunning = state.status === "running";
          // Effective URL: registry entry takes precedence; fall back to user-entered value
          const effectiveUrl = f.career_page_url || customUrls[f.name] || "";
          const needsUrl = !f.career_page_url;

          return (
            <div key={f.name} className="space-y-1.5">
              {/* Company header row */}
              <div className="flex flex-wrap items-center gap-2 text-xs text-yellow-300">
                <span className="font-semibold">{f.name}</span>
                <span className="text-yellow-400/60">({f.ats_type})</span>
                {effectiveUrl && (
                  <a
                    href={effectiveUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2 text-yellow-300/70 hover:text-yellow-200"
                  >
                    Open ↗
                  </a>
                )}
              </div>

              {/* Inline URL input for companies with no registry career page URL */}
              {needsUrl && state.status === "idle" && (
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    placeholder="Enter career page URL to enable browser agent…"
                    value={customUrls[f.name] ?? ""}
                    onChange={(e) =>
                      setCustomUrls((prev) => ({ ...prev, [f.name]: e.target.value }))
                    }
                    className="flex-1 h-7 rounded-md px-2.5 py-1 text-xs text-white/90 outline-none"
                    style={{
                      background: "rgba(234,179,8,0.12)",
                      border: "1px solid rgba(234,179,8,0.30)",
                    }}
                  />
                </div>
              )}

              {/* Status / action row */}
              <div className="flex flex-wrap items-center gap-2 text-xs pl-0">
                {state.status === "idle" && (
                  <button
                    onClick={() => startAgent(f, needsUrl ? effectiveUrl : undefined)}
                    disabled={!effectiveUrl}
                    title={!effectiveUrl ? "Enter a career page URL above to enable" : undefined}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: "rgba(234,179,8,0.20)",
                      border: "1px solid rgba(234,179,8,0.40)",
                      color: "rgba(253,224,71,0.90)",
                    }}
                  >
                    🤖 Fetch via Browser Agent
                  </button>
                )}

                {isRunning && (
                  <>
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-yellow-400/60 border-t-yellow-300 shrink-0" />
                    <span className="text-yellow-300/80">
                      {state.jobsCollected > 0
                        ? `${state.jobsCollected} jobs found…`
                        : "Starting agent…"}
                    </span>
                    <button
                      onClick={() => killAgent(f)}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors"
                      style={{
                        background: "rgba(239,68,68,0.18)",
                        border: "1px solid rgba(239,68,68,0.35)",
                        color: "rgba(252,165,165,0.90)",
                      }}
                    >
                      ■ Kill Agent
                    </button>
                  </>
                )}

                {state.status === "done" && (
                  <span className="text-emerald-400 font-medium">
                    ✓ {state.jobsCollected} job{state.jobsCollected !== 1 ? "s" : ""} found
                    {state.scoredCount != null && (
                      <span className="text-emerald-400/75 font-normal ml-1">
                        · {state.scoredCount} scored
                      </span>
                    )}
                    {state.metrics && (
                      <span className="text-emerald-400/60 font-normal ml-1">
                        ({Math.round(state.metrics.elapsed_seconds)}s)
                      </span>
                    )}
                  </span>
                )}

                {state.status === "killed" && (
                  <span className="text-yellow-500/90">
                    ✋ Stopped —{" "}
                    {(state.partialJobs ?? state.jobsCollected) > 0
                      ? `${state.partialJobs ?? state.jobsCollected} partial jobs saved${state.scoredCount != null ? ` · ${state.scoredCount} scored` : ""}`
                      : "no jobs collected"}
                    {state.status === "killed" && (
                      <button
                        onClick={() => startAgent(f, needsUrl ? effectiveUrl : undefined)}
                        className="ml-2 underline underline-offset-2 text-yellow-300/70 hover:text-yellow-200"
                      >
                        Retry
                      </button>
                    )}
                  </span>
                )}

                {state.status === "error" && (
                  <span className="text-red-400" title={state.errorMessage}>
                    ✗{" "}
                    {(state.errorMessage ?? "Unknown error").length > 80
                      ? (state.errorMessage ?? "Unknown error").slice(0, 80) + "…"
                      : (state.errorMessage ?? "Unknown error")}
                    <button
                      onClick={() => startAgent(f, needsUrl ? effectiveUrl : undefined)}
                      className="ml-2 underline underline-offset-2 text-red-300/70 hover:text-red-200"
                    >
                      Retry
                    </button>
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Source selector (Last Run vs Registry) ───────────────────────────────────

const modeBtn = (active: boolean) =>
  [
    "px-4 py-1.5 rounded-lg text-sm font-semibold transition-all",
    active
      ? "bg-white/20 text-white border border-white/30"
      : "bg-transparent text-white/45 border border-transparent hover:text-white/70 hover:bg-white/08",
  ].join(" ");

function CompanySourceCard({
  registry,
  sourceMode,
  setSourceMode,
  selectedNames,
  setSelectedNames,
  registrySearch,
  setRegistrySearch,
  selectedRunId,
  setSelectedRunId,
  allRuns,
}: {
  registry: CompanyRegistryEntry[];
  sourceMode: "last-run" | "registry" | "pick-run";
  setSourceMode: (m: "last-run" | "registry" | "pick-run") => void;
  selectedNames: string[];
  setSelectedNames: (n: string[]) => void;
  registrySearch: string;
  setRegistrySearch: (s: string) => void;
  selectedRunId: string;
  setSelectedRunId: (id: string) => void;
  allRuns: CompanyRunSummary[];
}) {
  const available = registry.filter(
    (e) =>
      !selectedNames.includes(e.name) &&
      e.name.toLowerCase().includes(registrySearch.toLowerCase()),
  );

  return (
    <Card>
      <CardContent className="pt-5 pb-4 space-y-4">
        {/* Mode toggle */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs font-semibold text-white/45 uppercase tracking-wider mr-2">
            Company Source
          </span>
          <button className={modeBtn(sourceMode === "last-run")} onClick={() => setSourceMode("last-run")}>
            Last Discovery Run
          </button>
          <button className={modeBtn(sourceMode === "pick-run")} onClick={() => setSourceMode("pick-run")}>
            Pick a Run
          </button>
          <button className={modeBtn(sourceMode === "registry")} onClick={() => setSourceMode("registry")}>
            Select from Registry
          </button>
        </div>

        {sourceMode === "last-run" && (
          <p className="text-xs text-white/40">
            Uses all companies from the most recent Discover Companies run.
          </p>
        )}

        {sourceMode === "pick-run" && (
          <div className="space-y-2">
            {allRuns.length === 0 ? (
              <p className="text-xs text-white/35 italic">
                No runs yet — run Discover Companies first.
              </p>
            ) : (
              <>
                <select
                  value={selectedRunId}
                  onChange={(e) => setSelectedRunId(e.target.value)}
                  className="flex h-8 w-full max-w-sm rounded-lg px-3 py-1 text-sm text-white outline-none focus-visible:ring-2 focus-visible:ring-white/20"
                  style={{
                    background: "rgba(255,255,255,0.10)",
                    border: "1px solid rgba(255,255,255,0.20)",
                  }}
                >
                  <option value="" style={{ background: "#1b4332", color: "white" }}>
                    — select a run —
                  </option>
                  {allRuns.map((r) => (
                    <option key={r.id} value={r.id} style={{ background: "#1b4332", color: "white" }}>
                      {r.run_name} · {r.company_count} companies · {new Date(r.created_at).toLocaleDateString()}
                    </option>
                  ))}
                </select>
                {!selectedRunId && (
                  <p className="text-xs text-amber-400/70">Select a run above to use its companies.</p>
                )}
              </>
            )}
          </div>
        )}

        {sourceMode === "registry" && (
          <div className="space-y-3">
            {/* Search */}
            <Input
              placeholder="Search registry…"
              value={registrySearch}
              onChange={(e) => setRegistrySearch(e.target.value)}
              className="h-8 text-sm"
            />

            {/* Selected chips */}
            {selectedNames.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {selectedNames.map((name) => (
                  <button
                    key={name}
                    onClick={() => setSelectedNames(selectedNames.filter((n) => n !== name))}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium
                               bg-white/20 text-white border border-white/25 hover:bg-white/30 transition-colors"
                  >
                    {name}
                    <span className="text-white/60 leading-none">×</span>
                  </button>
                ))}
              </div>
            )}

            {/* Available list */}
            {registry.length === 0 ? (
              <p className="text-xs text-white/35 italic">
                Registry is empty — run Discover Companies first.
              </p>
            ) : available.length === 0 && selectedNames.length > 0 ? (
              <p className="text-xs text-white/35 italic">All matching companies selected.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                {available.map((e) => (
                  <button
                    key={e.name}
                    onClick={() => setSelectedNames([...selectedNames, e.name])}
                    className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium
                               bg-white/08 text-white/60 border border-white/12
                               hover:bg-white/15 hover:text-white/90 hover:border-white/25 transition-colors"
                  >
                    {e.name}
                  </button>
                ))}
              </div>
            )}

            {selectedNames.length === 0 && (
              <p className="text-xs text-amber-400/70">
                ↑ Click companies above to add them to your selection.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Job Run History ──────────────────────────────────────────────────────────

const JOB_RUNS_PER_PAGE = 5;

function tierCounts(metrics: JobRunMetrics): { t1: number; t2: number } {
  const t2 = metrics.jobs_per_ats["career_page"] ?? 0;
  const t1 = Object.entries(metrics.jobs_per_ats)
    .filter(([k]) => k !== "career_page")
    .reduce((sum, [, v]) => sum + v, 0);
  return { t1, t2 };
}

function JobRunCard({ run }: { run: JobRun }) {
  const [expanded, setExpanded] = useState(false);
  const { t1, t2 } = tierCounts(run.metrics);
  const cpEntries = Object.entries(run.metrics.career_page_per_company ?? {});
  const date = new Date(run.created_at).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });

  const statusColor =
    run.status === "completed" ? "text-emerald-400" :
    run.status === "failed" ? "text-red-400" :
    run.status === "running" ? "text-yellow-400" :
    "text-white/40";

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
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3 flex-wrap min-w-0">
          <span className="font-semibold text-white text-sm">{run.run_name}</span>
          <span className="text-xs text-white/55 tabular-nums">
            T1: <span className="text-white/80">{t1}</span>
          </span>
          <span className={`text-xs tabular-nums ${t2 > 0 ? "text-amber-400 font-medium" : "text-white/25"}`}>
            T2: {t2}
          </span>
          {run.metrics.playwright_uses > 0 && (
            <Badge className="text-[10px] bg-white/8 text-white/45 border border-white/15">
              {run.metrics.playwright_uses} scraped
            </Badge>
          )}
          <span className="text-xs text-white/35">{date}</span>
          <span className={`text-xs ${statusColor}`}>{run.status}</span>
        </div>
        <span className="text-white/40 text-sm ml-2 shrink-0">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          {cpEntries.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs text-white/40 mb-2 uppercase tracking-wide">Tier 2 companies</p>
              {cpEntries.map(([company, count]) => (
                <div key={company} className="flex items-center justify-between text-sm">
                  <span className="text-white/70">{company}</span>
                  <span className={`tabular-nums text-xs ${count > 0 ? "text-amber-400" : "text-white/30"}`}>
                    {count} role{count !== 1 ? "s" : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/35 text-sm py-2">No Tier 2 scraping in this run.</p>
          )}
          <div className="mt-3 pt-3 border-t border-white/10 flex flex-wrap gap-4 text-xs text-white/45">
            <span>{run.metrics.companies_total} companies total</span>
            <span>{run.metrics.total_roles_fetched} roles fetched</span>
            {run.metrics.total_roles_after_filter > 0 && (
              <span>{run.metrics.total_roles_after_filter} after filter</span>
            )}
            <span>{Math.round(run.metrics.elapsed_seconds)}s elapsed</span>
          </div>
        </div>
      )}
    </div>
  );
}

function JobRunHistory() {
  const [page, setPage] = useState(1);

  const { data, isFetching } = useQuery({
    queryKey: ["job-runs", page],
    queryFn: () => getJobRuns(page, JOB_RUNS_PER_PAGE),
    retry: false,
  });

  if (!data && !isFetching) return null;
  if (data && data.total === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide">
          Run History
        </h3>
        {isFetching && (
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white/70" />
        )}
      </div>

      {data && data.runs.length > 0 && (
        <>
          <div className="space-y-2">
            {data.runs.map((run) => (
              <JobRunCard key={run.id} run={run} />
            ))}
          </div>

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

export function RolesTab() {
  const qc = useQueryClient();

  // Source selection state
  const [sourceMode, setSourceMode] = useState<"last-run" | "registry" | "pick-run">("last-run");
  const [selectedNames, setSelectedNames] = useState<string[]>([]);
  const [registrySearch, setRegistrySearch] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<string>("");

  // Filter / scoring / provider state
  const [provider, setProvider] = useState<string>("gemini");
  const [titleFilter, setTitleFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [postedWithinValue, setPostedWithinValue] = useState<number | undefined>(undefined);
  const [postedWithinUnit, setPostedWithinUnit] = useState<"days" | "weeks" | "months">("days");
  const [scoringCriteria, setScoringCriteria] = useState("");
  const [useCache, setUseCache] = useState(false);
  const [filterStrategy, setFilterStrategy] = useState<"llm" | "fuzzy" | "semantic" | "gemini-embedding">("llm");
  const [skipCareerPage, setSkipCareerPage] = useState(false);
  const [enableTheirstack, setEnableTheirstack] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterProgress, setFilterProgress] = useState<string | null>(null);

  // Pagination & tab state
  const [activeTab, setActiveTab] = useState<string>("all");
  const [allRolesPage, setAllRolesPage] = useState(1);
  const [filteredPage, setFilteredPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Reset pages when pageSize changes
  useEffect(() => {
    setAllRolesPage(1);
    setFilteredPage(1);
  }, [pageSize]);

  const { data: cached } = useQuery({
    queryKey: ["roles"],
    queryFn: getRoles,
    retry: false,
  });

  // Poll for checkpoint existence so we can show the "Continue" banner
  const { data: checkpoint } = useQuery({
    queryKey: ["roles-checkpoint"],
    queryFn: getRolesCheckpoint,
    retry: false,
    refetchInterval: false,
  });

  // Company registry for the source selector
  const { data: registry = [] } = useQuery({
    queryKey: ["company-registry"],
    queryFn: getCompanyRegistry,
    retry: false,
  });

  // Company runs for the "Pick a Run" mode
  const { data: runsData } = useQuery({
    queryKey: ["company-runs", 1],
    queryFn: () => getCompanyRuns(1, 50),
    retry: false,
  });
  const allRuns = runsData?.runs ?? [];

  const canDiscover =
    sourceMode === "last-run" ||
    (sourceMode === "registry" && selectedNames.length > 0) ||
    (sourceMode === "pick-run" && !!selectedRunId);

  const discover = useMutation({
    mutationFn: (resume: boolean) => {
      const hasFilters = titleFilter || locationFilter || postedWithinValue;
      setFilterProgress(null);
      return discoverRolesStream(
        {
          resume,
          use_cache: useCache,
          company_names: sourceMode === "registry" ? selectedNames : undefined,
          company_run_id: sourceMode === "pick-run" ? selectedRunId : undefined,
          role_filters: hasFilters
            ? {
                title: titleFilter || undefined,
                location: locationFilter || undefined,
                posted_within_value: postedWithinValue || undefined,
                posted_within_unit: postedWithinValue ? postedWithinUnit : undefined,
                confidence: "high",
                filter_strategy: filterStrategy,
              }
            : undefined,
          relevance_score_criteria: scoringCriteria || undefined,
          model_provider: provider || undefined,
          skip_career_page: skipCareerPage || undefined,
          enable_theirstack: enableTheirstack || undefined,
          theirstack_max_results: enableTheirstack ? 25 : undefined,
        },
        undefined,
        filterStrategy === "semantic"
          ? (kept, total) => setFilterProgress(`Filtering… ${kept} / ${total} matched so far`)
          : undefined,
      );
    },
    onSuccess: (data) => {
      qc.setQueryData(["roles"], data);
      qc.setQueryData(["roles-checkpoint"], null);
      qc.invalidateQueries({ queryKey: ["roles-unfiltered"] });
      qc.invalidateQueries({ queryKey: ["job-runs"] });
      setError(null);
      setFilterProgress(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      const detail = err.response?.data?.detail ?? err.message;
      setError(detail);
      setFilterProgress(null);
      // Refresh checkpoint status so "Continue" banner appears
      qc.invalidateQueries({ queryKey: ["roles-checkpoint"] });
    },
  });

  // Poll for unfiltered roles while discovery is pending
  const { data: unfilteredData } = useQuery({
    queryKey: ["roles-unfiltered"],
    queryFn: getUnfilteredRoles,
    retry: false,
    refetchInterval: discover.isPending ? 3000 : false,
  });

  const result = discover.data ?? cached;
  const filteredRoles = result?.roles ?? [];
  const allRoles = unfilteredData?.roles ?? [];
  const flagged = result?.flagged_companies ?? unfilteredData?.flagged_companies ?? [];

  // Paginated slices
  const paginatedAll = allRoles.slice((allRolesPage - 1) * pageSize, allRolesPage * pageSize);
  const paginatedFiltered = filteredRoles.slice((filteredPage - 1) * pageSize, filteredPage * pageSize);

  const showResults = discover.isPending || result || unfilteredData;

  return (
    <div className="space-y-6">
      {/* Checkpoint / resume banner */}
      {checkpoint && !discover.isPending && (
        <div
          className="rounded-xl border px-4 py-3 flex items-center justify-between gap-4"
          style={{
            background: "rgba(59,130,246,0.12)",
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)",
            borderColor: "rgba(59,130,246,0.30)",
          }}
        >
          <div>
            <p className="text-sm font-medium text-blue-200">⏸ Previous run saved</p>
            <p className="text-xs text-blue-300/80 mt-0.5">{checkpoint.summary}</p>
          </div>
          <Button
            onClick={() => discover.mutate(true)}
            disabled={discover.isPending}
            className="shrink-0 bg-blue-500/20 border-blue-400/30 text-blue-200 hover:bg-blue-500/35"
          >
            Continue from previous run
          </Button>
        </div>
      )}

      {/* Company source selector */}
      <CompanySourceCard
        registry={registry}
        sourceMode={sourceMode}
        setSourceMode={setSourceMode}
        selectedNames={selectedNames}
        setSelectedNames={setSelectedNames}
        registrySearch={registrySearch}
        setRegistrySearch={setRegistrySearch}
        selectedRunId={selectedRunId}
        setSelectedRunId={setSelectedRunId}
        allRuns={allRuns}
      />

      {/* Filter form */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="title-filter" className="text-white/75">Job Title</Label>
              <Input
                id="title-filter"
                placeholder="e.g. Engineering Manager"
                maxLength={100}
                value={titleFilter}
                onChange={(e) => setTitleFilter(e.target.value)}
              />
              {titleFilter.length > 80 && (
                <p className="text-xs text-white/40">{titleFilter.length}/100</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="location-filter" className="text-white/75">Location</Label>
              <Input
                id="location-filter"
                placeholder="e.g. SF, Seattle or Remote"
                value={locationFilter}
                onChange={(e) => setLocationFilter(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="posted-within" className="text-white/75">Posted Within</Label>
              <div className="flex gap-2">
                <Input
                  id="posted-within"
                  type="number"
                  min={1}
                  max={postedWithinUnit === "months" ? 3 : postedWithinUnit === "weeks" ? 13 : 90}
                  placeholder="e.g. 2"
                  className="w-20"
                  value={postedWithinValue ?? ""}
                  onChange={(e) => {
                    const v = e.target.value ? parseInt(e.target.value, 10) : undefined;
                    if (v !== undefined && v < 1) return;
                    const maxMap = { days: 90, weeks: 13, months: 3 } as const;
                    const capped = v !== undefined ? Math.min(v, maxMap[postedWithinUnit]) : undefined;
                    setPostedWithinValue(capped);
                  }}
                />
                <select
                  value={postedWithinUnit}
                  onChange={(e) => {
                    const unit = e.target.value as "days" | "weeks" | "months";
                    setPostedWithinUnit(unit);
                    const maxMap = { days: 90, weeks: 13, months: 3 } as const;
                    if (postedWithinValue && postedWithinValue > maxMap[unit]) {
                      setPostedWithinValue(maxMap[unit]);
                    }
                  }}
                  className="flex h-8 rounded-lg px-2 py-1 text-sm text-white transition-colors outline-none focus-visible:ring-3 focus-visible:ring-white/20 focus-visible:border-white/40"
                  style={{
                    background: "rgba(255,255,255,0.10)",
                    backdropFilter: "blur(4px)",
                    WebkitBackdropFilter: "blur(4px)",
                    border: "1px solid rgba(255,255,255,0.20)",
                  }}
                >
                  <option value="days">days</option>
                  <option value="weeks">weeks</option>
                  <option value="months">months</option>
                </select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="scoring" className="text-white/75">Relevance Criteria</Label>
              <Input
                id="scoring"
                placeholder="e.g. spark, data pipelines"
                value={scoringCriteria}
                onChange={(e) => setScoringCriteria(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="roles-provider" className="text-white/75">LLM Provider</Label>
              <select
                id="roles-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="flex h-8 w-36 rounded-lg px-3 py-1 text-sm text-white transition-colors outline-none focus-visible:ring-3 focus-visible:ring-white/20 focus-visible:border-white/40"
                style={{
                  background: "rgba(255,255,255,0.10)",
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                  border: "1px solid rgba(255,255,255,0.20)",
                }}
              >
                <option value="gemini" style={{ background: "#1b4332", color: "white" }}>Gemini</option>
                <option value="anthropic" style={{ background: "#1b4332", color: "white" }}>Anthropic</option>
              </select>
            </div>
          </div>
          {/* Filter strategy toggle — only shown when title or location filter is set */}
          {(titleFilter || locationFilter) && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-white/45 uppercase tracking-wider mr-1">
                Filter via
              </span>
              {(["llm", "fuzzy", "semantic", "gemini-embedding"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterStrategy(s)}
                  className={[
                    "px-3 py-1 rounded-lg text-xs font-semibold transition-all",
                    filterStrategy === s
                      ? "bg-white/20 text-white border border-white/30"
                      : "bg-transparent text-white/45 border border-transparent hover:text-white/70 hover:bg-white/08",
                  ].join(" ")}
                >
                  {s === "llm" ? "LLM" : s === "fuzzy" ? "Fuzzy" : s === "semantic" ? "Semantic" : "Gemini"}
                </button>
              ))}
              <span className="text-xs text-white/30 ml-1">
                {filterStrategy === "llm"
                  ? "most accurate, uses API credits"
                  : filterStrategy === "fuzzy"
                  ? "instant, free, no LLM call"
                  : filterStrategy === "semantic"
                  ? "instant, free — requires pip install jobfinder[semantic]"
                  : "semantic match via Gemini API — free, no local model"}
              </span>
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <Button
              onClick={() => discover.mutate(false)}
              disabled={discover.isPending || !canDiscover}
            >
              {discover.isPending ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                  Discovering…
                </>
              ) : (
                "Discover Roles"
              )}
            </Button>
            <label className="flex items-center gap-2 text-sm text-white/55 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={useCache}
                onChange={(e) => setUseCache(e.target.checked)}
                className="accent-white/70"
              />
              Use cached results <span className="text-xs text-white/35">(TTL: 2 days)</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-white/55 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={skipCareerPage}
                onChange={(e) => setSkipCareerPage(e.target.checked)}
                className="accent-white/70"
              />
              API results only <span className="text-xs text-white/35">(skip Playwright career page)</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-white/55 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={enableTheirstack}
                onChange={(e) => setEnableTheirstack(e.target.checked)}
                className="accent-white/70"
              />
              Also search TheirStack <span className="text-xs text-white/35">(for companies without ATS API)</span>
            </label>
            {sourceMode === "registry" && selectedNames.length > 0 && (
              <span className="text-xs text-white/40">
                {selectedNames.length} {selectedNames.length === 1 ? "company" : "companies"} selected
              </span>
            )}
            {sourceMode === "pick-run" && selectedRunId && (() => {
              const run = allRuns.find((r) => r.id === selectedRunId);
              return run ? (
                <span className="text-xs text-white/40">
                  Run: {run.run_name} · {run.company_count} companies
                </span>
              ) : null;
            })()}
          </div>
        </CardContent>
      </Card>

      {error && (
        <p className="text-sm text-red-300 bg-red-500/15 border border-red-400/25 rounded-lg px-4 py-2">{error}</p>
      )}

      {showResults && (
        <div className="space-y-6">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as string)}>
            <div className="flex items-center justify-between flex-wrap gap-3">
              <TabsList>
                <TabsTrigger value="all">
                  All Roles
                  {allRoles.length > 0 && (
                    <Badge className="ml-2 text-[10px] bg-white/10 text-white/60 border border-white/20">
                      {allRoles.length}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="filtered">
                  Filtered
                  {filteredRoles.length > 0 && (
                    <Badge className="ml-2 text-[10px] bg-white/10 text-white/60 border border-white/20">
                      {filteredRoles.length}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>
              <PageSizeSelector pageSize={pageSize} setPageSize={setPageSize} />
            </div>

            <TabsContent value="all" className="mt-4">
              {discover.isPending && !unfilteredData ? (
                <div className="flex flex-col items-center gap-3 py-12 text-white/55">
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/40 border-t-white/80" />
                  <p className="text-sm">Fetching roles from company career pages…</p>
                  <p className="text-xs text-white/40">This may take 30–90 seconds</p>
                </div>
              ) : allRoles.length > 0 ? (
                <>
                  {unfilteredData?.in_progress && (
                    <div className="flex items-center gap-2 mb-3 text-white/55 text-sm">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white/80 shrink-0" />
                      <span>Fetching more roles… ({allRoles.length} found so far)</span>
                    </div>
                  )}
                  <RolesTable roles={paginatedAll} />
                  <PaginationControls
                    page={allRolesPage}
                    setPage={setAllRolesPage}
                    totalItems={allRoles.length}
                    pageSize={pageSize}
                  />
                </>
              ) : (
                <p className="text-white/45 text-sm py-8 text-center">
                  No roles found. Run discovery to fetch roles.
                </p>
              )}
            </TabsContent>

            <TabsContent value="filtered" className="mt-4">
              {discover.isPending ? (
                <div className="flex flex-col items-center gap-3 py-12 text-white/55">
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/40 border-t-white/80" />
                  <p className="text-sm">{filterProgress ?? "Filtering and scoring roles…"}</p>
                  <p className="text-xs text-white/40">
                    {filterProgress
                      ? "Semantic embeddings running in batches"
                      : "LLM is evaluating each role against your criteria"}
                  </p>
                </div>
              ) : filteredRoles.length > 0 ? (
                <>
                  <div className="flex items-center gap-3 flex-wrap mb-3">
                    {result && result.total_roles !== result.roles_after_filter && (
                      <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
                        {result.roles_after_filter} of {result.total_roles} after filter
                      </Badge>
                    )}
                    <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
                      {discover.data ? "Fresh" : "Cached"}
                    </Badge>
                  </div>
                  <RolesTable roles={paginatedFiltered} />
                  <PaginationControls
                    page={filteredPage}
                    setPage={setFilteredPage}
                    totalItems={filteredRoles.length}
                    pageSize={pageSize}
                  />
                </>
              ) : result ? (
                <p className="text-white/45 text-sm py-8 text-center">
                  No roles matched your filters.
                </p>
              ) : (
                <p className="text-white/45 text-sm py-8 text-center">
                  Run discovery to see filtered results.
                </p>
              )}
            </TabsContent>
          </Tabs>

          {/* Browser Agent — visually separated section */}
          {flagged.length > 0 && (
            <div className="space-y-3">
              <div className="border-t border-white/10 pt-4">
                <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide mb-3">
                  Browser Agent Fallback
                </h3>
              </div>
              <FlaggedBox
                flagged={flagged}
                onDone={() => qc.invalidateQueries({ queryKey: ["roles"] })}
              />
            </div>
          )}
        </div>
      )}

      {/* Job Run History */}
      <div className="border-t border-white/10 pt-4">
        <JobRunHistory />
      </div>
    </div>
  );
}
