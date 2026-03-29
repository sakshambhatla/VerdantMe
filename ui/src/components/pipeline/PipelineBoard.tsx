import type { PipelineEntry, PipelineStage } from "@/lib/api";
import { BOARD_STAGES } from "./constants";
import PipelineColumn from "./PipelineColumn";

interface Props {
  entries: PipelineEntry[];
  onEdit: (entry: PipelineEntry) => void;
  onDrop: (entryId: string, targetStage: PipelineStage, targetIndex: number) => void;
  onArchive?: (entry: PipelineEntry) => void;
  onDelete?: (entry: PipelineEntry) => void;
}

export default function PipelineBoard({ entries, onEdit, onDrop, onArchive, onDelete }: Props) {
  const byStage = (stage: PipelineStage) =>
    entries
      .filter((e) => e.stage === stage)
      .sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="flex gap-3 overflow-x-auto pb-2 -mx-2 px-2">
      {BOARD_STAGES.map((stage) => (
        <PipelineColumn
          key={stage}
          stage={stage}
          entries={byStage(stage)}
          onEdit={onEdit}
          onDrop={onDrop}
          onArchive={onArchive}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
