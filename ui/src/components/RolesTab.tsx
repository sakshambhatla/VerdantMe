import { useState } from "react";
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
  discoverRoles,
  getRoles,
  getRolesCheckpoint,
  getCompanyRegistry,
  type DiscoveredRole,
  type FlaggedCompany,
  type CompanyRegistryEntry,
} from "@/lib/api";
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

function FlaggedBox({ flagged }: { flagged: FlaggedCompany[] }) {
  if (flagged.length === 0) return null;
  return (
    <div
      className="rounded-xl border p-4 space-y-2"
      style={{
        background: "rgba(234,179,8,0.10)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        borderColor: "rgba(234,179,8,0.30)",
      }}
    >
      <p className="text-sm font-medium text-yellow-200">
        ⚠️ {flagged.length} {flagged.length === 1 ? "company" : "companies"} need manual check
      </p>
      <div className="space-y-1">
        {flagged.map((f) => (
          <div key={f.name} className="text-xs text-yellow-300 flex items-center gap-2">
            <span className="font-medium">{f.name}</span>
            <span className="text-yellow-400/70">({f.ats_type})</span>
            <a href={f.career_page_url} target="_blank" rel="noopener noreferrer"
              className="underline underline-offset-2 text-yellow-300/80 hover:text-yellow-200">
              Open ↗
            </a>
          </div>
        ))}
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
}: {
  registry: CompanyRegistryEntry[];
  sourceMode: "last-run" | "registry";
  setSourceMode: (m: "last-run" | "registry") => void;
  selectedNames: string[];
  setSelectedNames: (n: string[]) => void;
  registrySearch: string;
  setRegistrySearch: (s: string) => void;
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
        <div className="flex items-center gap-1">
          <span className="text-xs font-semibold text-white/45 uppercase tracking-wider mr-2">
            Company Source
          </span>
          <button className={modeBtn(sourceMode === "last-run")} onClick={() => setSourceMode("last-run")}>
            Last Discovery Run
          </button>
          <button className={modeBtn(sourceMode === "registry")} onClick={() => setSourceMode("registry")}>
            Select from Registry
          </button>
        </div>

        {sourceMode === "last-run" ? (
          <p className="text-xs text-white/40">
            Uses all companies from the previous Discover Companies run.
          </p>
        ) : (
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

// ─── Main tab ─────────────────────────────────────────────────────────────────

export function RolesTab() {
  const qc = useQueryClient();

  // Source selection state
  const [sourceMode, setSourceMode] = useState<"last-run" | "registry">("last-run");
  const [selectedNames, setSelectedNames] = useState<string[]>([]);
  const [registrySearch, setRegistrySearch] = useState("");

  // Filter / scoring / provider state
  const [provider, setProvider] = useState<string>("gemini");
  const [titleFilter, setTitleFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [postedAfter, setPostedAfter] = useState("");
  const [scoringCriteria, setScoringCriteria] = useState("");
  const [useCache, setUseCache] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const canDiscover =
    sourceMode === "last-run" || (sourceMode === "registry" && selectedNames.length > 0);

  const discover = useMutation({
    mutationFn: (resume: boolean) => {
      const hasFilters = titleFilter || locationFilter || postedAfter;
      return discoverRoles({
        resume,
        refresh: true,
        use_cache: useCache,
        company_names: sourceMode === "registry" ? selectedNames : undefined,
        role_filters: hasFilters
          ? {
              title: titleFilter || undefined,
              location: locationFilter || undefined,
              posted_after: postedAfter || undefined,
              confidence: "high",
            }
          : undefined,
        relevance_score_criteria: scoringCriteria || undefined,
        model_provider: provider || undefined,
      });
    },
    onSuccess: (data) => {
      qc.setQueryData(["roles"], data);
      qc.setQueryData(["roles-checkpoint"], null);
      setError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      const detail = err.response?.data?.detail ?? err.message;
      setError(detail);
      // Refresh checkpoint status so "Continue" banner appears
      qc.invalidateQueries({ queryKey: ["roles-checkpoint"] });
    },
  });

  const result = discover.data ?? cached;
  const roles = result?.roles ?? [];
  const flagged = result?.flagged_companies ?? [];

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
                value={titleFilter}
                onChange={(e) => setTitleFilter(e.target.value)}
              />
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
              <Label htmlFor="posted-after" className="text-white/75">Posted After</Label>
              <Input
                id="posted-after"
                placeholder="e.g. Jan 1, 2026"
                value={postedAfter}
                onChange={(e) => setPostedAfter(e.target.value)}
              />
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
            {sourceMode === "registry" && selectedNames.length > 0 && (
              <span className="text-xs text-white/40">
                {selectedNames.length} {selectedNames.length === 1 ? "company" : "companies"} selected
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {discover.isPending && (
        <div className="flex flex-col items-center gap-3 py-12 text-white/55">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/40 border-t-white/80" />
          <p className="text-sm">Fetching roles from company career pages…</p>
          <p className="text-xs text-white/40">This may take 30–90 seconds</p>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-300 bg-red-500/15 border border-red-400/25 rounded-lg px-4 py-2">{error}</p>
      )}

      {!discover.isPending && result && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide">
              {roles.length} Roles
            </h3>
            {result.total_roles !== result.roles_after_filter && (
              <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
                {result.roles_after_filter} of {result.total_roles} after filter
              </Badge>
            )}
            <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
              {discover.data ? "Fresh" : "Cached"}
            </Badge>
          </div>
          {roles.length > 0 ? <RolesTable roles={roles} /> : (
            <p className="text-white/45 text-sm py-8 text-center">
              No roles matched your filters.
            </p>
          )}
          <FlaggedBox flagged={flagged} />
        </div>
      )}
    </div>
  );
}
