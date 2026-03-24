import type { PipelineStats } from "@/lib/api";
import { ALL_STAGES, STAGE_META } from "./constants";

interface Props {
  stats: PipelineStats;
}

export default function PipelineFunnel({ stats }: Props) {
  const { stage_counts, total } = stats;
  if (total === 0) return null;

  return (
    <div className="mb-6">
      <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-2">
        Funnel Distribution
      </div>

      {/* Bar */}
      <div className="flex h-2 rounded-full overflow-hidden gap-0.5">
        {ALL_STAGES.map((stage) => {
          const count = stage_counts[stage] || 0;
          if (count === 0) return null;
          const pct = (count / total) * 100;
          const meta = STAGE_META[stage];
          return (
            <div
              key={stage}
              className="rounded-full transition-all"
              style={{
                width: `${pct}%`,
                background: meta.color,
                minWidth: count > 0 ? "4px" : 0,
              }}
              title={`${meta.label}: ${count} (${pct.toFixed(0)}%)`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {ALL_STAGES.map((stage) => {
          const count = stage_counts[stage] || 0;
          if (count === 0) return null;
          const meta = STAGE_META[stage];
          return (
            <div key={stage} className="flex items-center gap-1.5 text-[11px] text-white/40">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: meta.color }}
              />
              <span>
                {meta.label}{" "}
                <strong className="text-white/60">{count}</strong>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
