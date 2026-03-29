import type { PipelineEntry } from "@/lib/api";
import { BADGE_META, STAGE_META } from "./constants";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Props {
  entry: PipelineEntry;
  onEdit: (entry: PipelineEntry) => void;
  onArchive?: (entry: PipelineEntry) => void;
  onDelete?: (entry: PipelineEntry) => void;
  isDragging?: boolean;
}

export default function PipelineCard({ entry, onEdit, onArchive, onDelete, isDragging }: Props) {
  const stageMeta = STAGE_META[entry.stage];
  const badgeMeta = entry.badge ? BADGE_META[entry.badge] : null;
  const showMenu =
    (onArchive && entry.stage !== "archived") ||
    (onDelete && entry.stage !== "deleted");

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("application/pipeline-entry-id", entry.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => onEdit(entry)}
      className="group cursor-pointer rounded-lg border p-3 transition-all hover:shadow-md"
      style={{
        background: isDragging ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.05)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        borderColor: isDragging ? stageMeta.color : "rgba(255,255,255,0.08)",
        borderLeftWidth: "3px",
        borderLeftColor: stageMeta.color,
        opacity: isDragging ? 0.6 : 1,
      }}
    >
      {/* Header: company name + menu/badge */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1">
            <div className="text-[13px] font-semibold text-white/90 leading-tight truncate">
              {entry.company_name}
            </div>
            {entry.source === "linkedin" && (
              <span title="Sourced via LinkedIn" className="shrink-0 self-center">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="#0A66C2" xmlns="http://www.w3.org/2000/svg">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
              </span>
            )}
          </div>
          {entry.tags.length > 0 && (
            <div className="flex flex-nowrap gap-1 mt-1 overflow-hidden">
              {entry.tags.map((tag) => (
                <span
                  key={tag}
                  className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium text-white/40 bg-white/5 border border-white/10 capitalize"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          {entry.role_title && (
            <div className="text-[11px] text-white/40 mt-0.5 truncate">
              {entry.role_title}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {badgeMeta && (
            <span
              className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider"
              style={{
                background: `${badgeMeta.color}22`,
                color: badgeMeta.color,
                border: `1px solid ${badgeMeta.color}44`,
              }}
            >
              {badgeMeta.label}
            </span>
          )}
          {showMenu && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  draggable={false}
                  onDragStart={(e) => e.stopPropagation()}
                  onClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="opacity-30 hover:opacity-80 transition-opacity rounded p-0.5 hover:bg-white/10"
                >
                  <span className="material-symbols-outlined text-[16px] text-white/50">more_vert</span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="min-w-[120px] bg-[#1a1a2e] border-white/10"
                onClick={(e) => e.stopPropagation()}
              >
                {onArchive && entry.stage !== "archived" && (
                  <DropdownMenuItem
                    className="text-white/70 text-xs gap-2 cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      onArchive(entry);
                    }}
                  >
                    <span className="material-symbols-outlined text-[14px]">archive</span>
                    Archive
                  </DropdownMenuItem>
                )}
                {onDelete && entry.stage !== "deleted" && (
                  <DropdownMenuItem
                    className="text-red-400/80 text-xs gap-2 cursor-pointer focus:text-red-400"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(entry);
                    }}
                  >
                    <span className="material-symbols-outlined text-[14px]">delete</span>
                    Delete
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {/* Next action */}
      {entry.next_action && (
        <div className="mt-2 text-[10px] text-white/50 font-mono leading-snug truncate">
          <span className="text-white/30 mr-1">&rarr;</span>
          {entry.next_action}
        </div>
      )}
    </div>
  );
}
