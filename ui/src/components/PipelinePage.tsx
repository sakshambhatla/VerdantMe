import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { PipelineEntry, PipelineStage, PipelineBadge } from "@/lib/api";
import {
  getPipelineEntries,
  getPipelineStats,
  getPipelineUpdates,
  createPipelineEntry,
  updatePipelineEntry,
  deletePipelineEntry,
  reorderPipelineEntries,
} from "@/lib/api";
import PipelineBoard from "./pipeline/PipelineBoard";
import PipelineBacklog from "./pipeline/PipelineBacklog";
import PipelineFunnel from "./pipeline/PipelineFunnel";
import PipelineUpdates from "./pipeline/PipelineUpdates";
import PipelineEntryDialog from "./pipeline/PipelineEntryDialog";

export function PipelinePage() {
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<PipelineEntry | null>(null);

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

  const entries = entriesData?.entries ?? [];
  const backlogEntries = entries.filter((e) => e.stage === "not_started");
  const activeEntries = entries.filter((e) => e.stage !== "not_started");

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
            Job Pipeline
          </h2>
          <p className="text-sm text-white/35 mt-0.5">
            {entries.length} companies tracked
            {activeEntries.length > 0 &&
              ` \u00b7 ${activeEntries.length} active`}
          </p>
        </div>
        <Button
          onClick={handleAdd}
          className="bg-white/10 hover:bg-white/15 text-white/80 border border-white/10 text-sm"
        >
          + Add Entry
        </Button>
      </div>

      {/* Funnel */}
      {statsData && <PipelineFunnel stats={statsData} />}

      {/* Kanban Board */}
      <PipelineBoard
        entries={activeEntries}
        onEdit={handleEdit}
        onDrop={handleDrop}
      />

      {/* Backlog */}
      <PipelineBacklog entries={backlogEntries} onEdit={handleEdit} />

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
    </div>
  );
}
