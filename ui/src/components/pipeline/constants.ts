import type { PipelineStage, PipelineBadge } from "@/lib/api";

export interface StageMeta {
  label: string;
  color: string;
  bgColor: string;
}

export const STAGE_META: Record<PipelineStage, StageMeta> = {
  not_started: { label: "Not Started", color: "#6b7280", bgColor: "rgba(107,114,128,0.15)" },
  recruiter: { label: "Recruiter Call", color: "#a3a6ff", bgColor: "rgba(163,166,255,0.15)" },
  hm_screen: { label: "HM Screen", color: "#53ddfc", bgColor: "rgba(83,221,252,0.15)" },
  onsite: { label: "Onsite / Deep", color: "#f59e0b", bgColor: "rgba(245,158,11,0.15)" },
  offer: { label: "Offer", color: "#22c55e", bgColor: "rgba(34,197,94,0.15)" },
  blocked: { label: "Blocked", color: "#6b7280", bgColor: "rgba(107,114,128,0.12)" },
  rejected: { label: "Rejected", color: "#f43f5e", bgColor: "rgba(244,63,94,0.15)" },
};

/** Stages shown as Kanban columns (excludes backlog). */
export const BOARD_STAGES: PipelineStage[] = [
  "recruiter",
  "hm_screen",
  "onsite",
  "offer",
  "blocked",
  "rejected",
];

export const ALL_STAGES: PipelineStage[] = [
  "not_started",
  ...BOARD_STAGES,
];

export const BADGE_META: Record<PipelineBadge, { label: string; color: string }> = {
  done: { label: "Done", color: "#22c55e" },
  new: { label: "New", color: "#53ddfc" },
  panel: { label: "Panel", color: "#a3a6ff" },
  await: { label: "Awaiting", color: "#f59e0b" },
  sched: { label: "Scheduled", color: "#8b5cf6" },
};
