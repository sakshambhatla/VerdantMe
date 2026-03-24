import type { PipelineUpdate } from "@/lib/api";
import { STAGE_META } from "./constants";
import type { PipelineStage } from "@/lib/api";

interface Props {
  updates: PipelineUpdate[];
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    " " +
    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function StageLabel({ stage }: { stage: string | null }) {
  if (!stage) return null;
  const meta = STAGE_META[stage as PipelineStage];
  if (!meta) return <span className="text-white/50">{stage}</span>;
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider"
      style={{ background: `${meta.color}22`, color: meta.color }}
    >
      {meta.label}
    </span>
  );
}

export default function PipelineUpdates({ updates }: Props) {
  if (updates.length === 0) return null;

  return (
    <div className="mt-8">
      <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-3">
        Recent Updates
      </div>

      <div
        className="rounded-lg border p-4 space-y-3 max-h-[300px] overflow-y-auto"
        style={{
          background: "rgba(255,255,255,0.03)",
          borderColor: "rgba(255,255,255,0.06)",
        }}
      >
        {updates.map((u) => (
          <div key={u.id} className="flex gap-3 items-start">
            {/* Timestamp */}
            <div className="shrink-0 w-[90px] text-[10px] font-mono text-white/25 pt-0.5">
              {formatTime(u.created_at)}
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              {u.update_type === "stage_change" ? (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <StageLabel stage={u.from_stage} />
                  <span className="text-white/20 text-[10px]">&rarr;</span>
                  <StageLabel stage={u.to_stage} />
                </div>
              ) : u.update_type === "created" ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-emerald-400/70 font-mono uppercase tracking-wider">
                    Added
                  </span>
                </div>
              ) : null}
              <div className="text-[12px] text-white/50 mt-0.5 leading-snug">
                {u.message}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
