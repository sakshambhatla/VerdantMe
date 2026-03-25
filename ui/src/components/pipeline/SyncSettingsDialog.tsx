import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface SyncSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSync: (params: { lookback_days: number; custom_phrases: string[] }) => void;
  syncing: boolean;
}

export default function SyncSettingsDialog({
  open,
  onOpenChange,
  onSync,
  syncing,
}: SyncSettingsDialogProps) {
  const [lookbackDays, setLookbackDays] = useState(3);
  const [phrases, setPhrases] = useState<string[]>([]);
  const [phraseInput, setPhraseInput] = useState("");

  const addPhrase = () => {
    const trimmed = phraseInput.trim();
    if (trimmed && !phrases.includes(trimmed)) {
      setPhrases((prev) => [...prev, trimmed]);
      setPhraseInput("");
    }
  };

  const removePhrase = (index: number) => {
    setPhrases((prev) => prev.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addPhrase();
    }
  };

  const handleSync = () => {
    onSync({ lookback_days: lookbackDays, custom_phrases: phrases });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md border"
        style={{
          background: "rgba(15,15,20,0.95)",
          backdropFilter: "blur(20px)",
          borderColor: "rgba(255,255,255,0.1)",
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-white/90">Sync Settings</DialogTitle>
        </DialogHeader>

        <div className="space-y-5 mt-2">
          {/* Lookback days */}
          <div className="space-y-2">
            <Label className="text-white/70 text-sm">
              Lookback window (days)
            </Label>
            <div className="flex items-center gap-3">
              <Input
                type="number"
                min={1}
                max={14}
                value={lookbackDays}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v)) setLookbackDays(Math.min(14, Math.max(1, v)));
                }}
                className="w-20 bg-white/5 border-white/10 text-white/90"
              />
              <span className="text-white/40 text-xs">
                Scan Gmail &amp; Calendar from the last {lookbackDays} day
                {lookbackDays !== 1 ? "s" : ""}
              </span>
            </div>
          </div>

          {/* Custom phrases */}
          <div className="space-y-2">
            <Label className="text-white/70 text-sm">
              Custom search phrases
            </Label>
            <p className="text-white/30 text-xs">
              Add company names or keywords to search for in your email
            </p>
            <div className="flex gap-2">
              <Input
                value={phraseInput}
                onChange={(e) => setPhraseInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder='e.g. "Roblox"'
                className="flex-1 bg-white/5 border-white/10 text-white/90 placeholder:text-white/25"
              />
              <Button
                type="button"
                onClick={addPhrase}
                disabled={!phraseInput.trim()}
                className="bg-white/10 hover:bg-white/15 text-white/70 border border-white/10 text-sm px-3"
              >
                Add
              </Button>
            </div>
            {phrases.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {phrases.map((phrase, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white/8 text-white/70 text-xs border border-white/10"
                  >
                    {phrase}
                    <button
                      type="button"
                      onClick={() => removePhrase(i)}
                      className="text-white/30 hover:text-white/60 ml-0.5"
                    >
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              onClick={() => onOpenChange(false)}
              className="bg-white/5 hover:bg-white/10 text-white/60 border border-white/10 text-sm"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSync}
              disabled={syncing}
              className="bg-emerald-600/80 hover:bg-emerald-600 text-white text-sm"
            >
              {syncing ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                  Syncing...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-base mr-1">
                    sync
                  </span>
                  Sync
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
