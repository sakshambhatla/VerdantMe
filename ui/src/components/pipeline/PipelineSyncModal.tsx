import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  GmailSignal,
  CalendarSignal,
  PipelineSuggestion,
  SyncResult,
} from "@/lib/api";
import { STAGE_META } from "./constants";

interface PipelineSyncModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  syncResult: SyncResult | null;
  onApply: (
    suggestions: PipelineSuggestion[],
    newCompanies: PipelineSuggestion[],
  ) => void;
  applying: boolean;
}

/** Map a raw signal type to a default stage for pipeline entry creation. */
const SIGNAL_TO_STAGE: Record<string, string> = {
  offer: "offer",
  rejection: "rejected",
  scheduling: "recruiter",
  confirmation: "recruiter",
  recruiter_outreach: "not_started",
};

/** Convert a GmailSignal into a PipelineSuggestion so it can be selected. */
function signalToSuggestion(signal: GmailSignal, index: number): PipelineSuggestion {
  return {
    id: `signal-${index}`,
    entry_id: null,
    company_name: signal.company_name,
    suggested_stage: SIGNAL_TO_STAGE[signal.signal_type] || "not_started",
    suggested_badge: signal.signal_type === "offer" ? "new" : null,
    suggested_next_action: null,
    reason: signal.subject || `${signal.signal_type} signal`,
    confidence: signal.signal_type === "offer" || signal.signal_type === "rejection" ? "high" : "low",
    source: "gmail",
  };
}

export default function PipelineSyncModal({
  open,
  onOpenChange,
  syncResult,
  onApply,
  applying,
}: PipelineSyncModalProps) {
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<string>>(
    new Set(),
  );
  const [selectedNewCompanies, setSelectedNewCompanies] = useState<Set<string>>(
    new Set(),
  );
  const [selectedSignals, setSelectedSignals] = useState<Set<string>>(
    new Set(),
  );

  // Auto-select suggestions + new companies on open, deselect signals (older stuff)
  useEffect(() => {
    if (open && syncResult) {
      setSelectedSuggestions(new Set(syncResult.suggestions.map((s) => s.id)));
      setSelectedNewCompanies(new Set(syncResult.new_companies.map((c) => c.id)));
      setSelectedSignals(new Set()); // Signals unchecked by default
    }
  }, [open, syncResult]);

  if (!syncResult) return null;

  const {
    gmail_signals,
    calendar_signals,
    suggestions,
    new_companies,
    summary,
    google_connected,
    llm_available,
  } = syncResult;

  // Build the set of company names already covered by suggestions/new_companies
  const coveredCompanies = new Set([
    ...suggestions.map((s) => s.company_name.toLowerCase()),
    ...new_companies.map((c) => c.company_name.toLowerCase()),
  ]);

  // Extra signals = those NOT already covered by a suggestion
  const extraSignals = gmail_signals
    .map((s, i) => ({ signal: s, asSuggestion: signalToSuggestion(s, i) }))
    .filter(({ signal }) => !coveredCompanies.has(signal.company_name.toLowerCase()));

  const toggleSuggestion = (id: string) => {
    setSelectedSuggestions((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleNewCompany = (id: string) => {
    setSelectedNewCompanies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSignal = (id: string) => {
    setSelectedSignals((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedSuggestions(new Set(suggestions.map((s) => s.id)));
    setSelectedNewCompanies(new Set(new_companies.map((c) => c.id)));
    setSelectedSignals(new Set(extraSignals.map(({ asSuggestion }) => asSuggestion.id)));
  };

  const handleApply = () => {
    const acceptedSuggestions = suggestions.filter((s) =>
      selectedSuggestions.has(s.id),
    );
    const acceptedNewCompanies = [
      ...new_companies.filter((c) => selectedNewCompanies.has(c.id)),
      ...extraSignals
        .filter(({ asSuggestion }) => selectedSignals.has(asSuggestion.id))
        .map(({ asSuggestion }) => asSuggestion),
    ];
    onApply(acceptedSuggestions, acceptedNewCompanies);
  };

  const totalSelected =
    selectedSuggestions.size + selectedNewCompanies.size + selectedSignals.size;
  const hasSignals = gmail_signals.length > 0 || calendar_signals.length > 0;
  const hasSuggestions = suggestions.length > 0 || new_companies.length > 0;
  const hasAnything = hasSignals || hasSuggestions;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto bg-[#161616] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold">
            Pipeline Sync Results
          </DialogTitle>
        </DialogHeader>

        {/* Summary */}
        {summary && (
          <div className="rounded-lg bg-white/5 p-3 text-sm text-white/70 border border-white/5">
            {summary}
          </div>
        )}

        {/* Status badges */}
        <div className="flex gap-2 flex-wrap text-xs">
          <span
            className={`px-2 py-0.5 rounded-full ${google_connected ? "bg-green-500/20 text-green-400" : "bg-white/10 text-white/40"}`}
          >
            {google_connected ? "Google Connected" : "Google Not Connected"}
          </span>
          {google_connected && (
            <>
              <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/50">
                {gmail_signals.length} email signals
              </span>
              <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/50">
                {calendar_signals.length} calendar events
              </span>
            </>
          )}
          {llm_available && (
            <span className="px-2 py-0.5 rounded-full bg-[#a3a6ff]/20 text-[#a3a6ff]">
              LLM Analysis
            </span>
          )}
        </div>

        {!hasAnything && (
          <div className="text-center py-8 text-white/40 text-sm">
            {google_connected
              ? "No new signals detected from Gmail or Calendar."
              : "Connect your Google account to sync emails and calendar events."}
          </div>
        )}

        {/* Suggestions (checked by default) */}
        {suggestions.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-white/60 uppercase tracking-wider">
                Suggested Updates
              </h3>
              <button
                type="button"
                className="text-xs text-[#a3a6ff] hover:underline"
                onClick={selectAll}
              >
                Select all
              </button>
            </div>
            <div className="space-y-1.5">
              {suggestions.map((suggestion) => (
                <SuggestionRow
                  key={suggestion.id}
                  suggestion={suggestion}
                  selected={selectedSuggestions.has(suggestion.id)}
                  onToggle={() => toggleSuggestion(suggestion.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* New Companies (checked by default) */}
        {new_companies.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-white/60 uppercase tracking-wider">
              New Companies Detected
            </h3>
            <div className="space-y-1.5">
              {new_companies.map((company) => (
                <SuggestionRow
                  key={company.id}
                  suggestion={company}
                  selected={selectedNewCompanies.has(company.id)}
                  onToggle={() => toggleNewCompany(company.id)}
                  isNew
                />
              ))}
            </div>
          </div>
        )}

        {/* Extra Email Signals (unchecked by default) */}
        {extraSignals.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-white/60 uppercase tracking-wider">
              Other Email Signals
              <span className="ml-2 text-[10px] font-normal normal-case text-white/30">
                unchecked by default — check to add to pipeline
              </span>
            </h3>
            <div className="space-y-1.5 max-h-60 overflow-y-auto">
              {extraSignals.map(({ signal, asSuggestion }) => (
                <SignalSelectableRow
                  key={asSuggestion.id}
                  signal={signal}
                  suggestion={asSuggestion}
                  selected={selectedSignals.has(asSuggestion.id)}
                  onToggle={() => toggleSignal(asSuggestion.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Calendar Signals (read-only info) */}
        {calendar_signals.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-white/60 uppercase tracking-wider">
              Calendar Events
            </h3>
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {calendar_signals.map((signal, i) => (
                <CalendarSignalRow key={i} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        {hasAnything && (
          <div className="flex justify-end gap-2 pt-2 border-t border-white/5">
            <Button
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-white/50 hover:text-white/80"
            >
              Dismiss
            </Button>
            <Button
              onClick={handleApply}
              disabled={totalSelected === 0 || applying}
              className="bg-[#a3a6ff] text-black hover:bg-[#8b8eff] disabled:opacity-40"
            >
              {applying ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                  Applying...
                </>
              ) : totalSelected > 0 ? (
                `Apply ${totalSelected} change${totalSelected !== 1 ? "s" : ""}`
              ) : (
                "Select items to apply"
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

const typeColors: Record<string, string> = {
  scheduling: "text-blue-400",
  confirmation: "text-green-400",
  rejection: "text-red-400",
  offer: "text-green-400",
  recruiter_outreach: "text-purple-400",
};

function SignalSelectableRow({
  signal,
  suggestion,
  selected,
  onToggle,
}: {
  signal: GmailSignal;
  suggestion: PipelineSuggestion;
  selected: boolean;
  onToggle: () => void;
}) {
  const stageMeta =
    STAGE_META[suggestion.suggested_stage as keyof typeof STAGE_META];

  return (
    <label className="flex items-start gap-2 rounded bg-white/5 px-3 py-2 text-xs cursor-pointer hover:bg-white/8">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-0.5 accent-[#a3a6ff]"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`font-medium shrink-0 ${typeColors[signal.signal_type] || "text-white/60"}`}>
            {signal.signal_type.replace("_", " ")}
          </span>
          <span className="font-medium text-white/80">
            {signal.company_name}
          </span>
          {signal.is_new_company && (
            <span className="rounded-full bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">
              NEW
            </span>
          )}
          {stageMeta && (
            <span
              className="rounded-full px-1.5 py-0.5 text-[10px]"
              style={{
                backgroundColor: stageMeta.color + "20",
                color: stageMeta.color,
              }}
            >
              → {stageMeta.label}
            </span>
          )}
        </div>
        <p className="text-white/40 mt-0.5 truncate">{signal.subject}</p>
      </div>
      <span className="ml-auto shrink-0 text-white/30 text-[10px]">
        {signal.date?.slice(0, 10)}
      </span>
    </label>
  );
}

function CalendarSignalRow({ signal }: { signal: CalendarSignal }) {
  const isUpcoming = signal.event_type === "upcoming_interview";

  return (
    <div className="flex items-start gap-2 rounded bg-white/5 px-3 py-2 text-xs">
      <span className={`shrink-0 ${isUpcoming ? "text-blue-400" : "text-white/50"}`}>
        {isUpcoming ? "upcoming" : "completed"}
      </span>
      <div className="min-w-0">
        <span className="font-medium text-white/80">
          {signal.company_name || "Unknown"}
        </span>
        <p className="text-white/40 truncate">{signal.title}</p>
      </div>
      <span className="ml-auto shrink-0 text-white/30">
        {signal.start_time?.slice(0, 10)}
      </span>
    </div>
  );
}

function SuggestionRow({
  suggestion,
  selected,
  onToggle,
  isNew = false,
}: {
  suggestion: PipelineSuggestion;
  selected: boolean;
  onToggle: () => void;
  isNew?: boolean;
}) {
  const stageMeta =
    STAGE_META[suggestion.suggested_stage as keyof typeof STAGE_META];

  return (
    <label className="flex items-start gap-2 rounded bg-white/5 px-3 py-2 text-xs cursor-pointer hover:bg-white/8">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-0.5 accent-[#a3a6ff]"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-white/80">
            {suggestion.company_name}
          </span>
          {isNew && (
            <span className="rounded-full bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">
              NEW
            </span>
          )}
          {suggestion.suggested_stage && stageMeta && (
            <span
              className="rounded-full px-1.5 py-0.5 text-[10px]"
              style={{
                backgroundColor: stageMeta.color + "20",
                color: stageMeta.color,
              }}
            >
              {stageMeta.label}
            </span>
          )}
          <span
            className={`ml-auto text-[10px] ${
              suggestion.confidence === "high"
                ? "text-green-400"
                : suggestion.confidence === "medium"
                  ? "text-yellow-400"
                  : "text-white/40"
            }`}
          >
            {suggestion.confidence}
          </span>
        </div>
        <p className="text-white/40 mt-0.5">{suggestion.reason}</p>
      </div>
    </label>
  );
}
