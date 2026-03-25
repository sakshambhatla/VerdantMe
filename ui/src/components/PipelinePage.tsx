import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type {
  PipelineEntry,
  PipelineStage,
  PipelineBadge,
  PipelineSuggestion,
  SyncResult,
} from "@/lib/api";
import {
  getPipelineEntries,
  getPipelineStats,
  getPipelineUpdates,
  createPipelineEntry,
  updatePipelineEntry,
  deletePipelineEntry,
  reorderPipelineEntries,
  syncPipeline,
  applySyncSuggestions,
  getGoogleTokenStatus,
} from "@/lib/api";
import { useMode } from "@/contexts/ModeContext";
import PipelineBoard from "./pipeline/PipelineBoard";
import PipelineSideSection from "./pipeline/PipelineSideSection";
import PipelineFunnel from "./pipeline/PipelineFunnel";
import { BOARD_STAGES } from "./pipeline/constants";
import PipelineUpdates from "./pipeline/PipelineUpdates";
import PipelineEntryDialog from "./pipeline/PipelineEntryDialog";
import PipelineSyncModal from "./pipeline/PipelineSyncModal";
import SyncSettingsDialog from "./pipeline/SyncSettingsDialog";

export function PipelinePage() {
  const qc = useQueryClient();
  const { mode } = useMode();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<PipelineEntry | null>(null);
  const [syncSettingsOpen, setSyncSettingsOpen] = useState(false);
  const [syncModalOpen, setSyncModalOpen] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [showLocalModeNotice, setShowLocalModeNotice] = useState(false);

  // ── Data queries ──────────────────────────────────────────────────────────

  const { data: entriesData, isLoading } = useQuery({
    queryKey: ["pipeline-entries"],
    queryFn: () => getPipelineEntries(),
    retry: false,
  });

  const { data: statsData } = useQuery({
    queryKey: ["pipeline-stats"],
    queryFn: () => getPipelineStats(),
    retry: false,
  });

  const { data: updatesData } = useQuery({
    queryKey: ["pipeline-updates"],
    queryFn: () => getPipelineUpdates(undefined, 30),
    retry: false,
  });

  const { data: googleStatus } = useQuery({
    queryKey: ["google-token-status"],
    queryFn: getGoogleTokenStatus,
    retry: false,
    enabled: mode === "managed",
  });

  const entries = entriesData?.entries ?? [];
  const boardEntries = entries.filter((e) =>
    (BOARD_STAGES as string[]).includes(e.stage),
  );
  const backlogEntries = entries.filter((e) => e.stage === "not_started");
  const blockedEntries = entries.filter((e) => e.stage === "blocked");
  const rejectedEntries = entries.filter((e) => e.stage === "rejected");

  // ── Mutations ─────────────────────────────────────────────────────────────

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["pipeline-entries"] });
    qc.invalidateQueries({ queryKey: ["pipeline-stats"] });
    qc.invalidateQueries({ queryKey: ["pipeline-updates"] });
  };

  const createMutation = useMutation({
    mutationFn: (data: {
      company_name: string;
      role_title: string | null;
      stage: PipelineStage;
      note: string;
      next_action: string | null;
      badge: PipelineBadge | null;
      tags: string[];
    }) => createPipelineEntry(data),
    onSuccess: () => {
      invalidateAll();
      setDialogOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: string;
      company_name: string;
      role_title: string | null;
      stage: PipelineStage;
      note: string;
      next_action: string | null;
      badge: PipelineBadge | null;
      tags: string[];
    }) => updatePipelineEntry(id, data),
    onSuccess: () => {
      invalidateAll();
      setDialogOpen(false);
      setEditingEntry(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePipelineEntry(id),
    onSuccess: () => {
      invalidateAll();
      setDialogOpen(false);
      setEditingEntry(null);
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (moves: Array<{ id: string; stage: string; sort_order: number }>) =>
      reorderPipelineEntries(moves),
    onSuccess: invalidateAll,
  });

  const syncMutation = useMutation({
    mutationFn: (params?: { lookback_days: number; custom_phrases: string[] }) =>
      syncPipeline(params),
    onSuccess: (result) => {
      setSyncSettingsOpen(false);
      setSyncResult(result);
      setSyncModalOpen(true);
    },
  });

  const applyMutation = useMutation({
    mutationFn: ({
      suggestions: sugs,
      newCompanies,
    }: {
      suggestions: PipelineSuggestion[];
      newCompanies: PipelineSuggestion[];
    }) => applySyncSuggestions(sugs, newCompanies),
    onSuccess: () => {
      invalidateAll();
      setSyncModalOpen(false);
      setSyncResult(null);
    },
  });

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleEdit = (entry: PipelineEntry) => {
    setEditingEntry(entry);
    setDialogOpen(true);
  };

  const handleAdd = () => {
    setEditingEntry(null);
    setDialogOpen(true);
  };

  const handleSave = (data: {
    company_name: string;
    role_title: string | null;
    stage: PipelineStage;
    note: string;
    next_action: string | null;
    badge: PipelineBadge | null;
    tags: string[];
  }) => {
    if (editingEntry) {
      updateMutation.mutate({ id: editingEntry.id, ...data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleDelete = () => {
    if (editingEntry) {
      deleteMutation.mutate(editingEntry.id);
    }
  };

  const handleSync = () => {
    if (mode === "local") {
      console.info(
        "[Pipeline Sync] Not supported in local mode. Switch to managed mode (Supabase) to use Gmail + Calendar sync.",
      );
      setShowLocalModeNotice(true);
      return;
    }
    setSyncSettingsOpen(true);
  };

  const handleSyncWithSettings = (params: {
    lookback_days: number;
    custom_phrases: string[];
  }) => {
    syncMutation.mutate(params);
  };

  const handleApplySuggestions = (
    suggestions: PipelineSuggestion[],
    newCompanies: PipelineSuggestion[],
  ) => {
    applyMutation.mutate({ suggestions, newCompanies });
  };

  const handleDrop = (
    entryId: string,
    targetStage: PipelineStage,
    targetIndex: number,
  ) => {
    // Compute new sort orders for the target stage
    const targetEntries = entries
      .filter((e) => e.stage === targetStage && e.id !== entryId)
      .sort((a, b) => a.sort_order - b.sort_order);

    const moves: Array<{ id: string; stage: string; sort_order: number }> = [];

    // Insert the dragged entry at the target position
    targetEntries.splice(targetIndex, 0, { id: entryId } as PipelineEntry);

    targetEntries.forEach((e, i) => {
      moves.push({ id: e.id, stage: targetStage, sort_order: i });
    });

    reorderMutation.mutate(moves);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-white/30 border-t-transparent" />
        <p className="text-white/40 text-sm mt-3">Loading pipeline...</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-white/90">
            Tracking
          </h2>
          <p className="text-sm text-white/35 mt-0.5">
            {entries.length} companies tracked
            {boardEntries.length > 0 &&
              ` \u00b7 ${boardEntries.length} active`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={handleSync}
            disabled={syncMutation.isPending}
            title={mode === "local" ? "Sync requires managed mode (Supabase)" : undefined}
            className="bg-white/5 hover:bg-white/10 text-white/70 border border-white/10 text-sm gap-2"
          >
            {syncMutation.isPending ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Syncing...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-base">sync</span>
                Refresh
                {googleStatus?.connected && (
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500 ml-0.5" />
                )}
              </>
            )}
          </Button>
          <Button
            onClick={handleAdd}
            className="bg-white/10 hover:bg-white/15 text-white/80 border border-white/10 text-sm"
          >
            + Add Entry
          </Button>
        </div>
      </div>

      {/* Funnel */}
      {statsData && <PipelineFunnel stats={statsData} />}

      {/* Kanban Board */}
      <PipelineBoard
        entries={boardEntries}
        onEdit={handleEdit}
        onDrop={handleDrop}
      />

      {/* Side sections: Backlog, Blocked, Rejected */}
      <PipelineSideSection
        stage="not_started"
        label="Backlog — Not Started"
        entries={backlogEntries}
        onEdit={handleEdit}
        onDrop={handleDrop}
      />
      <PipelineSideSection
        stage="blocked"
        label="Blocked"
        entries={blockedEntries}
        onEdit={handleEdit}
        onDrop={handleDrop}
      />
      <PipelineSideSection
        stage="rejected"
        label="Rejected"
        entries={rejectedEntries}
        onEdit={handleEdit}
        onDrop={handleDrop}
      />

      {/* Updates */}
      {updatesData && <PipelineUpdates updates={updatesData.updates} />}

      {/* Entry Dialog */}
      <PipelineEntryDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setEditingEntry(null);
        }}
        entry={editingEntry}
        onSave={handleSave}
        onDelete={editingEntry ? handleDelete : undefined}
        saving={createMutation.isPending || updateMutation.isPending}
      />

      {/* Sync Settings Dialog */}
      <SyncSettingsDialog
        open={syncSettingsOpen}
        onOpenChange={setSyncSettingsOpen}
        onSync={handleSyncWithSettings}
        syncing={syncMutation.isPending}
      />

      {/* Sync Results Modal */}
      <PipelineSyncModal
        open={syncModalOpen}
        onOpenChange={(open) => {
          setSyncModalOpen(open);
          if (!open) setSyncResult(null);
        }}
        syncResult={syncResult}
        entries={entries}
        onApply={handleApplySuggestions}
        applying={applyMutation.isPending}
      />

      {/* Local mode notice */}
      {showLocalModeNotice && (
        <div className="fixed bottom-4 right-4 bg-blue-500/10 border border-blue-500/20 rounded-lg px-4 py-3 text-sm text-blue-300/80 max-w-sm flex items-start gap-3">
          <span className="material-symbols-outlined text-base mt-0.5 shrink-0">info</span>
          <div>
            <p className="font-medium">Sync not available in local mode</p>
            <p className="text-blue-300/60 mt-0.5">
              Gmail and Calendar sync requires managed mode (Supabase). This is expected — switch to Run Managed to enable it.
            </p>
          </div>
          <button
            onClick={() => setShowLocalModeNotice(false)}
            className="ml-auto shrink-0 text-blue-300/40 hover:text-blue-300/70"
            aria-label="Dismiss"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        </div>
      )}

      {/* Sync error toast */}
      {syncMutation.isError && (
        <div className="fixed bottom-4 right-4 bg-red-500/20 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400 max-w-sm">
          Sync failed: {(syncMutation.error as Error)?.message || "Unknown error"}
        </div>
      )}
    </div>
  );
}
