import type { PipelineStage, PipelineBadge } from "@/lib/api";

export interface StageMeta {
  label: string;
  color: string;
  bgColor: string;
}

export const STAGE_META: Record<PipelineStage, StageMeta> = {
  not_started: { label: "Not Started", color: "#6b7280", bgColor: "rgba(107,114,128,0.15)" },
  outreach:    { label: "Outreach",    color: "#0A66C2", bgColor: "rgba(10,102,194,0.15)" },
  recruiter: { label: "Recruiter Call", color: "#a3a6ff", bgColor: "rgba(163,166,255,0.15)" },
  hm_screen: { label: "HM Screen", color: "#53ddfc", bgColor: "rgba(83,221,252,0.15)" },
  onsite: { label: "Onsite / Deep", color: "#f59e0b", bgColor: "rgba(245,158,11,0.15)" },
  offer: { label: "Offer", color: "#22c55e", bgColor: "rgba(34,197,94,0.15)" },
  blocked: { label: "Blocked", color: "#6b7280", bgColor: "rgba(107,114,128,0.12)" },
  rejected: { label: "Rejected", color: "#f43f5e", bgColor: "rgba(244,63,94,0.15)" },
};

/** Stages shown as Kanban columns (active pipeline only). */
export const BOARD_STAGES: PipelineStage[] = [
  "outreach",
  "recruiter",
  "hm_screen",
  "onsite",
  "offer",
];

/** Stages shown as collapsible side sections below the board. */
export const SIDE_STAGES: PipelineStage[] = [
  "not_started",
  "blocked",
  "rejected",
];

export const ALL_STAGES: PipelineStage[] = [
  "not_started",
  ...BOARD_STAGES,
  "blocked",
  "rejected",
];

/** Numeric ordering for stage progression (higher = further along). */
export const STAGE_ORDER: Record<string, number> = {
  not_started: 0,
  recruiter: 1,
  hm_screen: 2,
  onsite: 3,
  offer: 4,
  blocked: -1,
  rejected: -1,
};

/** Returns true when moving from `from` to `to` is a backward stage change. */
export function isStageRegression(from: string, to: string): boolean {
  const fromOrder = STAGE_ORDER[from] ?? -1;
  const toOrder = STAGE_ORDER[to] ?? -1;
  // Terminal stages (blocked/rejected) are not comparable
  if (fromOrder < 0 || toOrder < 0) return false;
  return toOrder < fromOrder;
}

export const BADGE_META: Record<PipelineBadge, { label: string; color: string }> = {
  done: { label: "Done", color: "#22c55e" },
  new: { label: "New", color: "#53ddfc" },
  panel: { label: "Panel", color: "#a3a6ff" },
  await: { label: "Awaiting", color: "#f59e0b" },
  sched: { label: "Scheduled", color: "#8b5cf6" },
};
