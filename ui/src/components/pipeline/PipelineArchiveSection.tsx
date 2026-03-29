import { useState } from "react";
import type { PipelineEntry, PipelineStage } from "@/lib/api";
import { STAGE_META } from "./constants";
import PipelineCard from "./PipelineCard";

interface Props {
  archivedEntries: PipelineEntry[];
  deletedEntries: PipelineEntry[];
  onEdit: (entry: PipelineEntry) => void;
  onDrop: (entryId: string, targetStage: PipelineStage, targetIndex: number) => void;
}

export default function PipelineArchiveSection({
  archivedEntries,
  deletedEntries,
  onEdit,
  onDrop,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const total = archivedEntries.length + deletedEntries.length;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const entryId = e.dataTransfer.getData("application/pipeline-entry-id");
    if (entryId) {
      onDrop(entryId, "archived", archivedEntries.length);
    }
  };

  return (
    <div
      className="mt-6 pt-4 border-t border-white/5"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm hover:text-white/50 transition-colors mb-3"
        style={{ color: "rgba(255,255,255,0.25)" }}
      >
        <span className="text-[10px]">{expanded ? "\u25BC" : "\u25B6"}</span>
        <span className="font-medium">Archive & Deleted</span>
        {total > 0 && (
          <span className="text-[11px] opacity-50">({total})</span>
        )}
      </button>

      {expanded && (
        <div
          className="rounded-lg p-3 transition-colors"
          style={{
            background: dragOver ? "rgba(107,114,128,0.08)" : "rgba(255,255,255,0.02)",
            border: dragOver ? "1px dashed rgba(107,114,128,0.4)" : "1px dashed transparent",
          }}
        >
          {total === 0 && !dragOver ? (
            <div className="text-[11px] text-white/15 text-center py-3 italic">
              No archived or deleted items
            </div>
          ) : (
            <div className="space-y-4">
              {/* Archived group */}
              {archivedEntries.length > 0 && (
                <div>
                  <div
                    className="text-[10px] font-medium uppercase tracking-wider mb-2"
                    style={{ color: `${STAGE_META.archived.color}88` }}
                  >
                    Archived ({archivedEntries.length})
                  </div>
                  <div className="flex gap-2.5 overflow-x-auto pb-1">
                    {archivedEntries
                      .sort((a, b) => a.sort_order - b.sort_order)
                      .map((entry) => (
                        <div key={entry.id} className="shrink-0 w-[200px]">
                          <PipelineCard entry={entry} onEdit={onEdit} />
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Deleted group */}
              {deletedEntries.length > 0 && (
                <div>
                  <div
                    className="text-[10px] font-medium uppercase tracking-wider mb-2"
                    style={{ color: `${STAGE_META.deleted.color}88` }}
                  >
                    Deleted ({deletedEntries.length})
                  </div>
                  <div className="flex gap-2.5 overflow-x-auto pb-1">
                    {deletedEntries
                      .sort((a, b) => a.sort_order - b.sort_order)
                      .map((entry) => (
                        <div key={entry.id} className="shrink-0 w-[200px]">
                          <PipelineCard entry={entry} onEdit={onEdit} />
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {dragOver && (
            <div
              className="mt-2 rounded-lg border-2 border-dashed py-3 text-center text-[11px]"
              style={{ borderColor: "rgba(107,114,128,0.4)", color: "rgba(107,114,128,0.6)" }}
            >
              Drop here to archive
            </div>
          )}
        </div>
      )}

      {!expanded && dragOver && (
        <div
          className="rounded-lg border-2 border-dashed py-4 text-center text-[11px] mb-2"
          style={{ borderColor: "rgba(107,114,128,0.4)", color: "rgba(107,114,128,0.6)" }}
        >
          Drop here to archive
        </div>
      )}
    </div>
  );
}
