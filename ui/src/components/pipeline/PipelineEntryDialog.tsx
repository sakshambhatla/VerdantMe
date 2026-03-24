import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { PipelineEntry, PipelineStage, PipelineBadge } from "@/lib/api";
import { ALL_STAGES, STAGE_META, BADGE_META } from "./constants";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entry: PipelineEntry | null; // null = create mode
  onSave: (data: {
    company_name: string;
    role_title: string | null;
    stage: PipelineStage;
    note: string;
    next_action: string | null;
    badge: PipelineBadge | null;
    tags: string[];
  }) => void;
  onDelete?: () => void;
  saving?: boolean;
}

export default function PipelineEntryDialog({
  open,
  onOpenChange,
  entry,
  onSave,
  onDelete,
  saving,
}: Props) {
  const [companyName, setCompanyName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [stage, setStage] = useState<PipelineStage>("not_started");
  const [note, setNote] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [badge, setBadge] = useState<PipelineBadge | "none">("none");
  const [tagsStr, setTagsStr] = useState("");

  useEffect(() => {
    if (entry) {
      setCompanyName(entry.company_name);
      setRoleTitle(entry.role_title || "");
      setStage(entry.stage);
      setNote(entry.note);
      setNextAction(entry.next_action || "");
      setBadge(entry.badge || "none");
      setTagsStr(entry.tags.join(", "));
    } else {
      setCompanyName("");
      setRoleTitle("");
      setStage("not_started");
      setNote("");
      setNextAction("");
      setBadge("none");
      setTagsStr("");
    }
  }, [entry, open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) return;
    onSave({
      company_name: companyName.trim(),
      role_title: roleTitle.trim() || null,
      stage,
      note: note.trim(),
      next_action: nextAction.trim() || null,
      badge: badge === "none" ? null : badge,
      tags: tagsStr
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-lg border"
        style={{
          background: "rgba(15,15,20,0.95)",
          backdropFilter: "blur(20px)",
          borderColor: "rgba(255,255,255,0.1)",
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-white/90">
            {entry ? "Edit Pipeline Entry" : "Add to Pipeline"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          {/* Company Name */}
          <div className="space-y-1.5">
            <Label className="text-white/50 text-xs">Company Name *</Label>
            <Input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g., Stripe"
              required
              className="bg-white/5 border-white/10 text-white/90 placeholder:text-white/20"
            />
          </div>

          {/* Role Title */}
          <div className="space-y-1.5">
            <Label className="text-white/50 text-xs">Role Title</Label>
            <Input
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              placeholder="e.g., Senior Engineering Manager"
              className="bg-white/5 border-white/10 text-white/90 placeholder:text-white/20"
            />
          </div>

          {/* Stage + Badge row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-white/50 text-xs">Stage</Label>
              <Select value={stage} onValueChange={(v) => setStage(v as PipelineStage)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white/90">
                  <SelectValue>{STAGE_META[stage].label}</SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#1a1a2e] border-white/10">
                  {ALL_STAGES.map((s) => (
                    <SelectItem key={s} value={s} className="text-white/80">
                      {STAGE_META[s].label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-white/50 text-xs">Badge</Label>
              <Select value={badge} onValueChange={(v) => setBadge(v as PipelineBadge | "none")}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white/90">
                  <SelectValue>
                    {badge === "none" ? "None" : BADGE_META[badge].label}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#1a1a2e] border-white/10">
                  <SelectItem value="none" className="text-white/50">
                    None
                  </SelectItem>
                  {(Object.keys(BADGE_META) as PipelineBadge[]).map((b) => (
                    <SelectItem key={b} value={b} className="text-white/80">
                      <span style={{ color: BADGE_META[b].color }}>
                        {BADGE_META[b].label}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Tags */}
          <div className="space-y-1.5">
            <Label className="text-white/50 text-xs">Tags (comma-separated)</Label>
            <Input
              value={tagsStr}
              onChange={(e) => setTagsStr(e.target.value)}
              placeholder="e.g., freeze, positive, action needed"
              className="bg-white/5 border-white/10 text-white/90 placeholder:text-white/20"
            />
          </div>

          {/* Next Action */}
          <div className="space-y-1.5">
            <Label className="text-white/50 text-xs">Next Action</Label>
            <Input
              value={nextAction}
              onChange={(e) => setNextAction(e.target.value)}
              placeholder="e.g., Awaiting recruiter outreach"
              className="bg-white/5 border-white/10 text-white/90 placeholder:text-white/20"
            />
          </div>

          {/* Note */}
          <div className="space-y-1.5">
            <Label className="text-white/50 text-xs">Notes</Label>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Interview history, contacts, timeline..."
              rows={4}
              className="bg-white/5 border-white/10 text-white/90 placeholder:text-white/20 resize-y"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-2">
            <div>
              {entry && onDelete && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={onDelete}
                  className="text-red-400/70 hover:text-red-400 hover:bg-red-400/10 text-xs"
                >
                  Delete
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
                className="text-white/40 hover:text-white/60 text-xs"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!companyName.trim() || saving}
                className="bg-white/10 hover:bg-white/15 text-white/90 border border-white/10 text-xs"
              >
                {saving ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent mr-1.5" />
                ) : null}
                {entry ? "Update" : "Add"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
