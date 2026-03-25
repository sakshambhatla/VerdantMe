import { useEffect, useMemo, useState } from "react";
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
  PipelineEntry,
  SyncResult,
  JobUpdate,
} from "@/lib/api";
import { STAGE_META, BADGE_META, isStageRegression } from "./constants";

// ─── Conversion layer (swappable — today maps from PipelineSuggestion) ──────

/** Map a signal type to a default stage when no suggestion exists. */
const SIGNAL_STAGE_FALLBACK: Record<string, string> = {
  offer: "offer",
  rejection: "rejected",
  scheduling: "recruiter",
  confirmation: "recruiter",
  recruiter_outreach: "not_started",
};

function buildJobUpdates(
  suggestions: PipelineSuggestion[],
  newCompanies: PipelineSuggestion[],
  gmailSignals: GmailSignal[],
  calendarSignals: CalendarSignal[],
  entries: PipelineEntry[],
): JobUpdate[] {
  // Build entry lookup for current_stage
  const entryById = new Map<string, PipelineEntry>();
  for (const e of entries) entryById.set(e.id, e);
  const now = new Date().toISOString();

  // Index signals by company name (lowercase) for lookup
  const gmailByCompany = new Map<string, GmailSignal>();
  for (const s of gmailSignals) {
    const key = s.company_name.toLowerCase();
    // Keep highest-priority signal per company
    if (!gmailByCompany.has(key)) gmailByCompany.set(key, s);
  }

  const calByCompany = new Map<string, CalendarSignal>();
  for (const s of calendarSignals) {
    if (!s.company_name) continue;
    const key = s.company_name.toLowerCase();
    if (!calByCompany.has(key)) calByCompany.set(key, s);
  }

  const updates: JobUpdate[] = [];
  const covered = new Set<string>();

  // 1. Suggestions for existing entries → "update"
  for (const s of suggestions) {
    const key = s.company_name.toLowerCase();
    covered.add(key);
    const gmail = gmailByCompany.get(key);
    const cal = calByCompany.get(key);
    updates.push({
      id: s.id,
      source: (s.source === "calendar" ? "calendar" : "gmail") as "gmail" | "calendar",
      company_name: s.company_name,
      stage: s.suggested_stage || "not_started",
      badge: s.suggested_badge || null,
      next_action: s.suggested_next_action || null,
      note: "",
      updated_at: now,
      recommendation: "update",
      signal_type: gmail?.signal_type || cal?.event_type || s.source,
      signal_subject: gmail?.subject || cal?.title || s.reason,
      signal_date: gmail?.date || cal?.start_time || "",
      entry_id: s.entry_id,
      confidence: s.confidence,
      current_stage: s.entry_id ? (entryById.get(s.entry_id)?.stage ?? null) : null,
    });
  }

  // 2. New companies → "add"
  for (const c of newCompanies) {
    const key = c.company_name.toLowerCase();
    covered.add(key);
    const gmail = gmailByCompany.get(key);
    updates.push({
      id: c.id,
      source: (c.source === "calendar" ? "calendar" : "gmail") as "gmail" | "calendar",
      company_name: c.company_name,
      stage: c.suggested_stage || "not_started",
      badge: c.suggested_badge || "new",
      next_action: c.suggested_next_action || null,
      note: "",
      updated_at: now,
      recommendation: "add",
      signal_type: gmail?.signal_type || c.source,
      signal_subject: gmail?.subject || c.reason,
      signal_date: gmail?.date || "",
      entry_id: null,
      confidence: c.confidence,
      current_stage: null,
    });
  }

  // 3. Remaining signals not covered by suggestions → "ignore" by default
  for (const [key, gmail] of gmailByCompany) {
    if (covered.has(key)) continue;
    updates.push({
      id: `extra-gmail-${key}`,
      source: "gmail",
      company_name: gmail.company_name,
      stage: SIGNAL_STAGE_FALLBACK[gmail.signal_type] || "not_started",
      badge: gmail.signal_type === "offer" ? "new" : null,
      next_action: null,
      note: "",
      updated_at: now,
      recommendation: "ignore",
      signal_type: gmail.signal_type,
      signal_subject: gmail.subject,
      signal_date: gmail.date,
      entry_id: null,
      confidence: "low",
      current_stage: null,
    });
    covered.add(key);
  }

  for (const [key, cal] of calByCompany) {
    if (covered.has(key)) continue;
    updates.push({
      id: `extra-cal-${key}`,
      source: "calendar",
      company_name: cal.company_name!,
      stage: "recruiter",
      badge: cal.event_type === "upcoming_interview" ? "sched" : "done",
      next_action: null,
      note: "",
      updated_at: now,
      recommendation: "ignore",
      signal_type: cal.event_type,
      signal_subject: cal.title,
      signal_date: cal.start_time,
      entry_id: null,
      confidence: "low",
      current_stage: null,
    });
  }

  return updates;
}

// ─── Component ──────────────────────────────────────────────────────────────

interface PipelineSyncModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  syncResult: SyncResult | null;
  entries: PipelineEntry[];
  onApply: (
    suggestions: PipelineSuggestion[],
    newCompanies: PipelineSuggestion[],
  ) => void;
  applying: boolean;
}

type Recommendation = "add" | "update" | "ignore";

const RECOMMENDATION_COLORS: Record<Recommendation, { bg: string; text: string }> = {
  add: { bg: "bg-green-500/20", text: "text-green-400" },
  update: { bg: "bg-blue-500/20", text: "text-blue-400" },
  ignore: { bg: "bg-white/10", text: "text-white/40" },
};

const SIGNAL_TYPE_COLORS: Record<string, string> = {
  offer: "text-green-400",
  rejection: "text-red-400",
  scheduling: "text-blue-400",
  confirmation: "text-green-400",
  recruiter_outreach: "text-purple-400",
  upcoming_interview: "text-blue-400",
  completed_interview: "text-white/50",
  scheduled: "text-blue-400",
};

export default function PipelineSyncModal({
  open,
  onOpenChange,
  syncResult,
  entries,
  onApply,
  applying,
}: PipelineSyncModalProps) {
  const [overrides, setOverrides] = useState<Record<string, Recommendation>>({});

  // Build JobUpdate list from sync result
  const jobUpdates = useMemo(() => {
    if (!syncResult) return [];
    return buildJobUpdates(
      syncResult.suggestions,
      syncResult.new_companies,
      syncResult.gmail_signals,
      syncResult.calendar_signals,
      entries,
    );
  }, [syncResult, entries]);

  // Reset overrides when modal opens with new data
  useEffect(() => {
    if (open) setOverrides({});
  }, [open, syncResult]);

  if (!syncResult) return null;

  const { summary, google_connected, llm_available, gmail_signals, calendar_signals } =
    syncResult;

  const getRecommendation = (ju: JobUpdate): Recommendation =>
    overrides[ju.id] ?? ju.recommendation;

  const setRecommendation = (id: string, rec: Recommendation) =>
    setOverrides((prev) => ({ ...prev, [id]: rec }));

  const activeUpdates = jobUpdates.filter(
    (ju) => getRecommendation(ju) !== "ignore",
  );

  const handleApply = () => {
    const toApplySuggestions: PipelineSuggestion[] = [];
    const toApplyNew: PipelineSuggestion[] = [];

    for (const ju of activeUpdates) {
      const suggestion: PipelineSuggestion = {
        id: ju.id,
        entry_id: ju.entry_id,
        company_name: ju.company_name,
        suggested_stage: ju.stage,
        suggested_badge: ju.badge,
        suggested_next_action: ju.next_action,
        reason: ju.signal_subject || ju.signal_type,
        confidence: ju.confidence,
        source: ju.source,
      };
      if (getRecommendation(ju) === "update" && ju.entry_id) {
        toApplySuggestions.push(suggestion);
      } else {
        toApplyNew.push(suggestion);
      }
    }

    onApply(toApplySuggestions, toApplyNew);
  };

  const resetAll = () => setOverrides({});
  const ignoreAll = () => {
    const all: Record<string, Recommendation> = {};
    for (const ju of jobUpdates) all[ju.id] = "ignore";
    setOverrides(all);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-6xl max-h-[90vh] overflow-hidden flex flex-col bg-[#161616] border-white/10 text-white p-0">
        <DialogHeader className="px-6 pt-5 pb-3">
          <DialogTitle className="text-lg font-semibold">
            Pipeline Sync Results
          </DialogTitle>
        </DialogHeader>

        {/* Summary + badges */}
        <div className="px-6 space-y-3">
          {summary && (
            <div className="rounded-lg bg-white/5 p-3 text-sm text-white/70 border border-white/5">
              {summary}
            </div>
          )}
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
        </div>

        {jobUpdates.length === 0 ? (
          <div className="flex-1 flex items-center justify-center py-12 text-white/40 text-sm">
            {google_connected
              ? "No signals detected from Gmail or Calendar."
              : "Connect your Google account to sync emails and calendar events."}
          </div>
        ) : (
          <>
            {/* Column headers */}
            <div className="grid grid-cols-[1fr_120px_1.4fr] gap-3 px-6 pt-4 pb-2 text-[10px] font-medium text-white/40 uppercase tracking-wider border-b border-white/5">
              <div>Signal</div>
              <div className="text-center">Action</div>
              <div>Pipeline Entry Preview</div>
            </div>

            {/* Toolbar */}
            <div className="flex gap-2 px-6 py-2 text-xs">
              <button
                type="button"
                onClick={resetAll}
                className="text-[#a3a6ff] hover:underline"
              >
                Reset all
              </button>
              <span className="text-white/20">|</span>
              <button
                type="button"
                onClick={ignoreAll}
                className="text-white/40 hover:underline"
              >
                Ignore all
              </button>
              <span className="ml-auto text-white/30">
                {activeUpdates.length} of {jobUpdates.length} will be applied
              </span>
            </div>

            {/* Scrollable rows */}
            <div className="flex-1 overflow-y-auto px-6 pb-4 space-y-2">
              {jobUpdates.map((ju) => (
                <SyncRow
                  key={ju.id}
                  jobUpdate={ju}
                  recommendation={getRecommendation(ju)}
                  onRecommendationChange={(rec) =>
                    setRecommendation(ju.id, rec)
                  }
                />
              ))}
            </div>
          </>
        )}

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-white/5">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            className="text-white/50 hover:text-white/80"
          >
            Dismiss
          </Button>
          <Button
            onClick={handleApply}
            disabled={activeUpdates.length === 0 || applying}
            className="bg-[#a3a6ff] text-black hover:bg-[#8b8eff] disabled:opacity-40"
          >
            {applying ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                Applying...
              </>
            ) : activeUpdates.length > 0 ? (
              `Apply ${activeUpdates.length} change${activeUpdates.length !== 1 ? "s" : ""}`
            ) : (
              "Nothing to apply"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Row component ──────────────────────────────────────────────────────────

function SyncRow({
  jobUpdate,
  recommendation,
  onRecommendationChange,
}: {
  jobUpdate: JobUpdate;
  recommendation: Recommendation;
  onRecommendationChange: (rec: Recommendation) => void;
}) {
  const isIgnored = recommendation === "ignore";
  const stageMeta = STAGE_META[jobUpdate.stage as keyof typeof STAGE_META];
  const currentStageMeta = jobUpdate.current_stage
    ? STAGE_META[jobUpdate.current_stage as keyof typeof STAGE_META]
    : null;
  const regression = !!(
    jobUpdate.current_stage &&
    jobUpdate.stage &&
    jobUpdate.current_stage !== jobUpdate.stage &&
    isStageRegression(jobUpdate.current_stage, jobUpdate.stage)
  );
  const badgeMeta = jobUpdate.badge
    ? BADGE_META[jobUpdate.badge as keyof typeof BADGE_META]
    : null;
  const recStyle = RECOMMENDATION_COLORS[recommendation];
  const signalColor =
    SIGNAL_TYPE_COLORS[jobUpdate.signal_type] || "text-white/50";

  return (
    <div
      className={`grid grid-cols-[1fr_120px_1.4fr] gap-3 rounded-lg border p-3 transition-opacity ${
        isIgnored
          ? "border-white/5 bg-white/[0.02] opacity-50"
          : "border-white/10 bg-white/5"
      }`}
    >
      {/* Column 1: Signal */}
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-1.5 text-[10px]">
          <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-white/40 uppercase">
            {jobUpdate.source}
          </span>
          <span className={`font-medium ${signalColor}`}>
            {jobUpdate.signal_type.replace(/_/g, " ")}
          </span>
        </div>
        <p className="text-xs font-medium text-white/80 truncate">
          {jobUpdate.signal_subject}
        </p>
        {jobUpdate.signal_date && (
          <p className="text-[10px] text-white/30">
            {formatDate(jobUpdate.signal_date)}
          </p>
        )}
      </div>

      {/* Column 2: Recommendation dropdown */}
      <div className="flex items-center justify-center">
        <select
          value={recommendation}
          onChange={(e) =>
            onRecommendationChange(e.target.value as Recommendation)
          }
          className={`rounded-md px-2 py-1 text-xs font-medium border-0 cursor-pointer ${recStyle.bg} ${recStyle.text} bg-opacity-100`}
          style={{ WebkitAppearance: "none", MozAppearance: "none" }}
        >
          <option value="add">Add</option>
          <option value="update">Update</option>
          <option value="ignore">Ignore</option>
        </select>
      </div>

      {/* Column 3: JobUpdate preview (pipeline entry) */}
      <div
        className={`min-w-0 rounded-md border-l-[3px] pl-3 py-1 space-y-1 ${
          isIgnored ? "border-white/10" : ""
        }`}
        style={
          !isIgnored && stageMeta
            ? { borderLeftColor: stageMeta.color }
            : undefined
        }
      >
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-white/90 truncate">
            {jobUpdate.company_name}
          </span>
          {badgeMeta && (
            <span
              className="rounded-full px-1.5 py-0.5 text-[9px] uppercase font-medium"
              style={{
                backgroundColor: badgeMeta.color + "20",
                color: badgeMeta.color,
              }}
            >
              {badgeMeta.label}
            </span>
          )}
        </div>
        {stageMeta && (
          <div className="flex items-center gap-1 text-[10px] flex-wrap">
            <span className="text-white/40">Stage:</span>
            {currentStageMeta && currentStageMeta.label !== stageMeta.label ? (
              <>
                <span
                  className="rounded-full px-1.5 py-0.5 font-medium"
                  style={{
                    backgroundColor: currentStageMeta.color + "15",
                    color: currentStageMeta.color,
                  }}
                >
                  {currentStageMeta.label}
                </span>
                <span className="text-white/30">&rarr;</span>
                <span
                  className="rounded-full px-1.5 py-0.5 font-medium"
                  style={{
                    backgroundColor: stageMeta.color + "15",
                    color: regression ? "#f59e0b" : stageMeta.color,
                    border: regression ? "1px solid rgba(245,158,11,0.4)" : undefined,
                  }}
                >
                  {stageMeta.label}
                </span>
                {regression && (
                  <span
                    className="text-amber-400 text-[9px] font-semibold ml-0.5"
                    title="This would move the entry to an earlier stage"
                  >
                    ⚠ backward
                  </span>
                )}
              </>
            ) : (
              <span
                className="rounded-full px-1.5 py-0.5 font-medium"
                style={{
                  backgroundColor: stageMeta.color + "15",
                  color: stageMeta.color,
                }}
              >
                {stageMeta.label}
              </span>
            )}
          </div>
        )}
        {jobUpdate.next_action && (
          <p className="text-[10px] text-white/50 font-mono">
            → {jobUpdate.next_action}
          </p>
        )}
        <p className="text-[10px] text-white/25">
          {formatDate(jobUpdate.updated_at)}
        </p>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16);
  }
}
