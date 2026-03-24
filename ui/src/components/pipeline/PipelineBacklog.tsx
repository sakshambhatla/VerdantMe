import { useState } from "react";
import type { PipelineEntry } from "@/lib/api";
import { BADGE_META } from "./constants";

interface Props {
  entries: PipelineEntry[];
  onEdit: (entry: PipelineEntry) => void;
}

export default function PipelineBacklog({ entries, onEdit }: Props) {
  const [expanded, setExpanded] = useState(true);

  if (entries.length === 0) return null;

  return (
    <div className="mt-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm text-white/50 hover:text-white/70 transition-colors mb-3"
      >
        <span className="text-[10px]">{expanded ? "▼" : "▶"}</span>
        <span className="font-medium">Backlog &mdash; Not Started</span>
        <span className="text-[11px] text-white/30">({entries.length})</span>
      </button>

      {expanded && (
        <div className="flex gap-2.5 overflow-x-auto pb-2 -mx-2 px-2">
          {entries
            .sort((a, b) => a.sort_order - b.sort_order)
            .map((entry) => {
              const badgeMeta = entry.badge ? BADGE_META[entry.badge] : null;
              return (
                <div
                  key={entry.id}
                  onClick={() => onEdit(entry)}
                  className="shrink-0 w-[170px] rounded-lg border p-2.5 cursor-pointer transition-all hover:shadow-md"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    borderColor: "rgba(255,255,255,0.08)",
                  }}
                >
                  <div className="flex items-start justify-between gap-1">
                    <div className="text-[12px] font-semibold text-white/80 leading-tight truncate">
                      {entry.company_name}
                    </div>
                    {badgeMeta && (
                      <span
                        className="shrink-0 rounded px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider"
                        style={{
                          background: `${badgeMeta.color}22`,
                          color: badgeMeta.color,
                        }}
                      >
                        {badgeMeta.label}
                      </span>
                    )}
                  </div>
                  {entry.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {entry.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded px-1 py-0.5 text-[8px] text-white/35 bg-white/5 capitalize"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {entry.note && (
                    <div className="mt-1.5 text-[10px] text-white/35 line-clamp-2 leading-snug">
                      {entry.note}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
