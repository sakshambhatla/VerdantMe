import { useState } from "react";
import type { PipelineEntry, PipelineStage } from "@/lib/api";
import { STAGE_META } from "./constants";
import PipelineCard from "./PipelineCard";

interface Props {
  stage: PipelineStage;
  entries: PipelineEntry[];
  onEdit: (entry: PipelineEntry) => void;
  onDrop: (entryId: string, targetStage: PipelineStage, targetIndex: number) => void;
}

export default function PipelineColumn({ stage, entries, onEdit, onDrop }: Props) {
  const meta = STAGE_META[stage];
  const [dragOver, setDragOver] = useState(false);

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
      className="flex flex-col min-w-[220px] max-w-[260px]"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Column header */}
      <div
        className="rounded-t-lg px-3 py-2.5 mb-2"
        style={{
          background: meta.bgColor,
          borderTop: `2px solid ${meta.color}`,
        }}
      >
        <div
          className="text-[10px] font-semibold uppercase tracking-widest font-mono"
          style={{ color: meta.color }}
        >
          {meta.label}
        </div>
        <div className="text-xl font-bold text-white/80 leading-none mt-1">
          {entries.length}
        </div>
      </div>

      {/* Cards */}
      <div
        className="flex flex-col gap-2 min-h-[60px] rounded-b-lg p-1 transition-colors"
        style={{
          background: dragOver ? `${meta.color}11` : "transparent",
          border: dragOver ? `1px dashed ${meta.color}55` : "1px dashed transparent",
          borderRadius: "0 0 8px 8px",
        }}
      >
        {entries.map((entry) => (
          <PipelineCard key={entry.id} entry={entry} onEdit={onEdit} />
        ))}
        {entries.length === 0 && !dragOver && (
          <div className="text-[11px] text-white/20 text-center py-4 italic">
            No entries
          </div>
        )}
        {dragOver && (
          <div
            className="rounded-lg border-2 border-dashed py-3 text-center text-[11px]"
            style={{ borderColor: `${meta.color}55`, color: `${meta.color}88` }}
          >
            Drop here
          </div>
        )}
      </div>
    </div>
  );
}
