import { useState } from "react";
import type { PipelineEntry, PipelineStage } from "@/lib/api";
import { STAGE_META } from "./constants";
import PipelineCard from "./PipelineCard";

interface Props {
  stage: PipelineStage;
  label: string;
  entries: PipelineEntry[];
  onEdit: (entry: PipelineEntry) => void;
  onDrop: (entryId: string, targetStage: PipelineStage, targetIndex: number) => void;
  onArchive?: (entry: PipelineEntry) => void;
  onDelete?: (entry: PipelineEntry) => void;
}

export default function PipelineSideSection({
  stage,
  label,
  entries,
  onEdit,
  onDrop,
  onArchive,
  onDelete,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const meta = STAGE_META[stage];

  if (entries.length === 0 && !dragOver) return null;

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
      onDrop(entryId, stage, entries.length);
    }
  };

  return (
    <div
      className="mt-4"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm hover:text-white/70 transition-colors mb-3"
        style={{ color: `${meta.color}88` }}
      >
        <span className="text-[10px]">{expanded ? "▼" : "▶"}</span>
        <span className="font-medium">{label}</span>
        <span className="text-[11px] opacity-50">({entries.length})</span>
      </button>

      {expanded && (
        <div
          className="flex gap-2.5 overflow-x-auto pb-2 -mx-2 px-2 min-h-[40px] rounded-lg transition-colors"
          style={{
            background: dragOver ? `${meta.color}11` : "transparent",
            border: dragOver ? `1px dashed ${meta.color}55` : "1px dashed transparent",
          }}
        >
          {entries
            .sort((a, b) => a.sort_order - b.sort_order)
            .map((entry) => (
              <div key={entry.id} className="shrink-0 w-[200px]">
                <PipelineCard entry={entry} onEdit={onEdit} onArchive={onArchive} onDelete={onDelete} />
              </div>
            ))}
          {dragOver && (
            <div
              className="shrink-0 w-[200px] rounded-lg border-2 border-dashed py-6 text-center text-[11px] flex items-center justify-center"
              style={{ borderColor: `${meta.color}55`, color: `${meta.color}88` }}
            >
              Drop here
            </div>
          )}
        </div>
      )}

      {!expanded && dragOver && (
        <div
          className="rounded-lg border-2 border-dashed py-4 text-center text-[11px] mb-2"
          style={{ borderColor: `${meta.color}55`, color: `${meta.color}88` }}
        >
          Drop here to move to {label}
        </div>
      )}
    </div>
  );
}
