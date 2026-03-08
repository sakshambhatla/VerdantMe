import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { discoverCompanies, getCompanies, type DiscoveredCompany } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

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

export function CompaniesTab() {
  const qc = useQueryClient();
  const [maxCompanies, setMaxCompanies] = useState<string>("20");
  const [provider, setProvider] = useState<string>("gemini");
  const [error, setError] = useState<string | null>(null);

  const { data: cached } = useQuery({
    queryKey: ["companies"],
    queryFn: getCompanies,
    retry: false,
  });

  const discover = useMutation({
    mutationFn: () =>
      discoverCompanies({
        max_companies: maxCompanies ? parseInt(maxCompanies, 10) : undefined,
        model_provider: provider || undefined,
      }),
    onSuccess: (data) => {
      qc.setQueryData(["companies"], data);
      setError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      setError(err.response?.data?.detail ?? err.message);
    },
  });

  const companies = discover.data?.companies ?? cached?.companies ?? [];

  return (
    <div className="space-y-6">
      {/* Config form */}
      <Card>
        <CardContent className="pt-6">
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
            <Button
              onClick={() => discover.mutate()}
              disabled={discover.isPending}
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
          <p className="text-sm">Analyzing your resume and discovering companies…</p>
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
            </h3>
            <Badge className="text-xs bg-white/10 text-white/60 border border-white/20">
              {discover.data ? "Fresh" : "Cached"}
            </Badge>
          </div>
          <CompanyTable companies={companies} />
        </div>
      )}
    </div>
  );
}
