import { useState } from "react";
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

  const selectAll = () => {
    setSelectedSuggestions(new Set(suggestions.map((s) => s.id)));
    setSelectedNewCompanies(new Set(new_companies.map((c) => c.id)));
  };

  const handleApply = () => {
    const acceptedSuggestions = suggestions.filter((s) =>
      selectedSuggestions.has(s.id),
    );
    const acceptedNewCompanies = new_companies.filter((c) =>
      selectedNewCompanies.has(c.id),
    );
    onApply(acceptedSuggestions, acceptedNewCompanies);
  };

  const totalSelected = selectedSuggestions.size + selectedNewCompanies.size;
  const hasSignals = gmail_signals.length > 0 || calendar_signals.length > 0;
  const hasSuggestions = suggestions.length > 0 || new_companies.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto bg-[#161616] border-white/10 text-white">
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

        {!hasSignals && !hasSuggestions && (
          <div className="text-center py-8 text-white/40 text-sm">
            {google_connected
              ? "No new signals detected from Gmail or Calendar."
              : "Connect your Google account to sync emails and calendar events."}
          </div>
        )}

        {/* Gmail Signals */}
        {gmail_signals.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-white/60 uppercase tracking-wider">
              Email Signals
            </h3>
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {gmail_signals.map((signal, i) => (
                <GmailSignalRow key={i} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {/* Calendar Signals */}
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

        {/* Suggestions */}
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

        {/* New Companies */}
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

        {/* Actions */}
        {hasSuggestions && (
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
              ) : (
                `Apply ${totalSelected} change${totalSelected !== 1 ? "s" : ""}`
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function GmailSignalRow({ signal }: { signal: GmailSignal }) {
  const typeColors: Record<string, string> = {
    scheduling: "text-blue-400",
    confirmation: "text-green-400",
    rejection: "text-red-400",
    offer: "text-green-400",
    recruiter_outreach: "text-purple-400",
  };

  return (
    <div className="flex items-start gap-2 rounded bg-white/5 px-3 py-2 text-xs">
      <span className={`font-medium shrink-0 ${typeColors[signal.signal_type] || "text-white/60"}`}>
        {signal.signal_type.replace("_", " ")}
      </span>
      <div className="min-w-0">
        <span className="font-medium text-white/80">{signal.company_name}</span>
        <p className="text-white/40 truncate">{signal.subject}</p>
      </div>
      {signal.is_new_company && (
        <span className="ml-auto shrink-0 rounded-full bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">
          NEW
        </span>
      )}
    </div>
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
