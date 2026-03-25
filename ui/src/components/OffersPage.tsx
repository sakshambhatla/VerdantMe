import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  getOfferEntries,
  getOfferAnalyses,
  analyzeOffer,
  saveOfferContext,
  type PipelineEntry,
  type OfferAnalysis,
} from "@/lib/api";
import OfferAnalysisResult from "./pipeline/OfferAnalysisResult";

const glassCard = {
  background: "rgba(255,255,255,0.05)",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
  borderColor: "rgba(255,255,255,0.1)",
};

function OfferCompanyCard({
  entry,
  analysis,
  onAnalyze,
  onSaveContext,
  isAnalyzing,
  analyzeError,
}: {
  entry: PipelineEntry;
  analysis: OfferAnalysis | undefined;
  onAnalyze: (companyName: string, context: string) => void;
  onSaveContext: (companyName: string, context: string) => void;
  isAnalyzing: boolean;
  analyzeError: string | null;
}) {
  const [expanded, setExpanded] = useState(!!analysis?.dimensions?.length);
  const [context, setContext] = useState(analysis?.personal_context ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const debouncedSave = useCallback(
    (val: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onSaveContext(entry.company_name, val);
      }, 1000);
    },
    [entry.company_name, onSaveContext],
  );

  const handleContextChange = (val: string) => {
    setContext(val);
    debouncedSave(val);
  };

  const handleAnalyze = () => {
    // Flush any pending debounce
    if (debounceRef.current) clearTimeout(debounceRef.current);
    onAnalyze(entry.company_name, context);
    setExpanded(true);
  };

  return (
    <div className="rounded-xl border" style={glassCard}>
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left cursor-pointer"
      >
        <div className="min-w-0">
          <div className="text-base font-semibold text-white/90">
            {entry.company_name}
          </div>
          {entry.role_title && (
            <div className="text-sm text-white/40 mt-0.5">{entry.role_title}</div>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {analysis?.weighted_score != null && (
            <span
              className={`text-lg font-bold tabular-nums ${
                analysis.weighted_score >= 3.5
                  ? "text-emerald-400"
                  : analysis.weighted_score >= 2.5
                    ? "text-yellow-400"
                    : "text-rose-400"
              }`}
            >
              {analysis.weighted_score.toFixed(1)}
            </span>
          )}
          <span
            className="material-symbols-outlined text-white/30 transition-transform"
            style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)" }}
          >
            expand_more
          </span>
        </div>
      </button>

      {/* Expanded Body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          {/* Personal Context */}
          <div className="pt-4">
            <label className="block text-[11px] text-white/40 uppercase tracking-wider mb-2">
              Your situation & context
            </label>
            <textarea
              value={context}
              onChange={(e) => handleContextChange(e.target.value)}
              placeholder="Paste competing offers, career goals, personal constraints, salary expectations..."
              rows={4}
              className="w-full rounded-lg border bg-white/[0.03] border-white/10 text-sm text-white/80 placeholder:text-white/20 p-3 resize-y focus:outline-none focus:border-white/25"
            />
            <div className="mt-2">
              <Button
                onClick={handleAnalyze}
                disabled={isAnalyzing}
                className="bg-[#22c55e]/15 hover:bg-[#22c55e]/25 text-[#22c55e] border border-[#22c55e]/30 text-sm gap-2"
              >
                {isAnalyzing && (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                )}
                {analysis?.dimensions?.length ? "Refresh insights" : "Get me Offer insights"}
              </Button>
              {analyzeError && (
                <p className="text-sm text-rose-400 mt-2">{analyzeError}</p>
              )}
            </div>
          </div>

          {/* Analysis Result */}
          {analysis?.dimensions?.length ? (
            <OfferAnalysisResult analysis={analysis} />
          ) : null}
        </div>
      )}
    </div>
  );
}

export function OffersPage() {
  const qc = useQueryClient();
  const [analyzingCompany, setAnalyzingCompany] = useState<string | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const { data: entriesData, isLoading: loadingEntries } = useQuery({
    queryKey: ["offer-entries"],
    queryFn: getOfferEntries,
    retry: false,
  });

  const { data: analysesData, isLoading: loadingAnalyses } = useQuery({
    queryKey: ["offer-analyses"],
    queryFn: getOfferAnalyses,
    retry: false,
  });

  const analyzeMutation = useMutation({
    mutationFn: ({
      companyName,
      personalContext,
    }: {
      companyName: string;
      personalContext: string;
    }) => analyzeOffer(companyName, personalContext),
    onMutate: ({ companyName }) => {
      setAnalyzingCompany(companyName);
      setAnalyzeError(null);
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Analysis failed — check your API key and try again.";
      setAnalyzeError(detail);
    },
    onSettled: () => {
      setAnalyzingCompany(null);
      qc.invalidateQueries({ queryKey: ["offer-analyses"] });
    },
  });

  const handleSaveContext = useCallback(
    (companyName: string, personalContext: string) => {
      saveOfferContext(companyName, personalContext).catch(() => {
        /* silent — auto-save best-effort */
      });
    },
    [],
  );

  const entries = entriesData?.entries ?? [];
  const analyses = analysesData?.analyses ?? [];

  const getAnalysis = (companyName: string): OfferAnalysis | undefined =>
    analyses.find(
      (a) => a.company_name.toLowerCase() === companyName.toLowerCase(),
    );

  const isLoading = loadingEntries || loadingAnalyses;

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white/90">Offers</h2>
          <p className="text-sm text-white/35 mt-0.5">
            {entries.length} {entries.length === 1 ? "company" : "companies"} in
            offer stage
          </p>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <span className="h-8 w-8 animate-spin rounded-full border-3 border-[#22c55e] border-t-transparent" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && entries.length === 0 && (
        <div
          className="rounded-xl border p-12 text-center"
          style={glassCard}
        >
          <span className="material-symbols-outlined text-4xl text-white/15 mb-4 block">
            assignment_turned_in
          </span>
          <h3 className="text-lg font-semibold text-white/50 mb-2">
            No offers yet
          </h3>
          <p className="text-sm text-white/30 max-w-md mx-auto">
            When companies in your pipeline reach the Offer stage, they'll
            appear here for detailed evaluation.
          </p>
        </div>
      )}

      {/* Offer Cards */}
      {!isLoading && entries.length > 0 && (
        <div className="space-y-4">
          {entries.map((entry) => (
            <OfferCompanyCard
              key={entry.id}
              entry={entry}
              analysis={getAnalysis(entry.company_name)}
              onAnalyze={(name, ctx) =>
                analyzeMutation.mutate({
                  companyName: name,
                  personalContext: ctx,
                })
              }
              onSaveContext={handleSaveContext}
              isAnalyzing={analyzingCompany === entry.company_name}
              analyzeError={
                analyzingCompany === null &&
                analyzeError !== null &&
                /* show error on the card that was just analyzed */
                analyzeMutation.variables?.companyName === entry.company_name
                  ? analyzeError
                  : null
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
