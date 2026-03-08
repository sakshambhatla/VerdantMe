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
import { discoverRoles, getRoles, type DiscoveredRole, type FlaggedCompany } from "@/lib/api";
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

export function RolesTab() {
  const qc = useQueryClient();
  const [titleFilter, setTitleFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [postedAfter, setPostedAfter] = useState("");
  const [scoringCriteria, setScoringCriteria] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: cached } = useQuery({
    queryKey: ["roles"],
    queryFn: getRoles,
    retry: false,
  });

  const discover = useMutation({
    mutationFn: () => {
      const hasFilters = titleFilter || locationFilter || postedAfter;
      return discoverRoles({
        refresh: true,
        role_filters: hasFilters
          ? {
              title: titleFilter || undefined,
              location: locationFilter || undefined,
              posted_after: postedAfter || undefined,
              confidence: "high",
            }
          : undefined,
        relevance_score_criteria: scoringCriteria || undefined,
      });
    },
    onSuccess: (data) => {
      qc.setQueryData(["roles"], data);
      setError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      setError(err.response?.data?.detail ?? err.message);
    },
  });

  const result = discover.data ?? cached;
  const roles = result?.roles ?? [];
  const flagged = result?.flagged_companies ?? [];

  return (
    <div className="space-y-6">
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
          </div>
          <div className="mt-4">
            <Button
              onClick={() => discover.mutate()}
              disabled={discover.isPending}
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
