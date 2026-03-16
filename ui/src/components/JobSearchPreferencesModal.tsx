import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface JobSearchPreferencesModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const STORAGE_KEY = "verdantme_preferences";

export function JobSearchPreferencesModal({
  open,
  onOpenChange,
}: JobSearchPreferencesModalProps) {
  const [careerFocus, setCareerFocus] = useState("");
  const [hasChanges, setHasChanges] = useState(false);

  // Load careerFocus from the shared preferences object
  useEffect(() => {
    if (open) {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const data = JSON.parse(stored);
          setCareerFocus(data.careerFocus || "");
        } else {
          setCareerFocus("");
        }
      } catch {
        setCareerFocus("");
      }
      setHasChanges(false);
    }
  }, [open]);

  const handleSave = () => {
    // Read-modify-write so we don't clobber LLM preferences
    let existing: Record<string, unknown> = {};
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) existing = JSON.parse(stored);
    } catch {
      // ignore
    }
    existing.careerFocus = careerFocus;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
    setHasChanges(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-2xl">Job Search Preferences</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="careerFocus" className="text-sm font-semibold">
              Career Focus
            </Label>
            <Textarea
              id="careerFocus"
              value={careerFocus}
              onChange={(e) => {
                setCareerFocus(e.target.value);
                setHasChanges(true);
              }}
              placeholder="E.g., Senior backend engineer, interested in startups, remote work preferred..."
              className="text-sm min-h-[120px] resize-none"
            />
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.50)" }}>
              Describe your career goals and preferences. This will help personalize
              company and role discovery results.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={!hasChanges}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
