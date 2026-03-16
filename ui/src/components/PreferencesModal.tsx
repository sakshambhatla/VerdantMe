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
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface PreferencesModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface PreferencesData {
  modelProvider: "anthropic" | "gemini";
  modelName: string;
  apiKey: string;
  rpmLimit: number;
  careerFocus: string;
}

const ANTHROPIC_MODELS = [
  "claude-3-5-sonnet-20241022",
  "claude-3-opus-20250219",
  "claude-3-haiku-20240307",
];

const GEMINI_MODELS = [
  "gemini-2.0-flash",
  "gemini-1.5-pro",
  "gemini-1.5-flash",
];

const STORAGE_KEY = "verdantme_preferences";

export function PreferencesModal({ open, onOpenChange }: PreferencesModalProps) {
  const [preferences, setPreferences] = useState<PreferencesData>({
    modelProvider: "anthropic",
    modelName: "claude-3-5-sonnet-20241022",
    apiKey: "",
    rpmLimit: 4,
    careerFocus: "",
  });

  const [showApiKey, setShowApiKey] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Load preferences from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const data = JSON.parse(stored);
        setPreferences(data);
      } catch (e) {
        console.error("Failed to parse stored preferences:", e);
      }
    }
  }, [open]); // Reload when modal opens

  const handlePreferenceChange = (field: keyof PreferencesData, value: any) => {
    setPreferences((prev) => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handleProviderChange = (provider: "anthropic" | "gemini") => {
    const defaultModel = provider === "anthropic" ? ANTHROPIC_MODELS[0] : GEMINI_MODELS[0];
    setPreferences((prev) => ({
      ...prev,
      modelProvider: provider,
      modelName: defaultModel,
    }));
    setHasChanges(true);
  };

  const handleSave = () => {
    // Read-modify-write so we don't clobber fields owned by other modals (e.g. careerFocus)
    let existing: Record<string, unknown> = {};
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) existing = JSON.parse(stored);
    } catch {
      // ignore
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...existing, ...preferences }));
    setHasChanges(false);
    onOpenChange(false);
  };

  const availableModels =
    preferences.modelProvider === "anthropic" ? ANTHROPIC_MODELS : GEMINI_MODELS;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-2xl">⚙️ LLM Preferences</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-6 py-4">
          {/* Left Column: Form Inputs */}
          <div className="space-y-6 border-r pr-6" style={{ borderColor: "rgba(255,255,255,0.10)" }}>
            {/* Model Provider */}
            <div className="space-y-3">
              <Label className="text-sm font-semibold">Model Provider</Label>
              <RadioGroup
                value={preferences.modelProvider}
                onValueChange={(v) => handleProviderChange(v as "anthropic" | "gemini")}
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="anthropic" id="anthropic" />
                  <Label htmlFor="anthropic" className="font-normal cursor-pointer text-sm">
                    Anthropic (Claude)
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="gemini" id="gemini" />
                  <Label htmlFor="gemini" className="font-normal cursor-pointer text-sm">
                    Google (Gemini)
                  </Label>
                </div>
              </RadioGroup>
            </div>

            {/* Model Selection */}
            <div className="space-y-2">
              <Label htmlFor="model" className="text-sm font-semibold">
                Model
              </Label>
              <Select
                value={preferences.modelName}
                onValueChange={(v) => handlePreferenceChange("modelName", v)}
              >
                <SelectTrigger id="model" className="text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model) => (
                    <SelectItem key={model} value={model} className="text-xs">
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* API Key */}
            <div className="space-y-2">
              <Label htmlFor="apiKey" className="text-sm font-semibold">
                API Key
              </Label>
              <div className="flex gap-2">
                <Input
                  id="apiKey"
                  type={showApiKey ? "text" : "password"}
                  value={preferences.apiKey}
                  onChange={(e) => handlePreferenceChange("apiKey", e.target.value)}
                  placeholder="sk-... or sk_..."
                  className="text-xs"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="px-2"
                >
                  {showApiKey ? "Hide" : "Show"}
                </Button>
              </div>
              <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.60)" }}>
                Your API key is stored locally only, never sent to our servers.
              </p>
            </div>

            {/* RPM Limit */}
            <div className="space-y-2">
              <Label htmlFor="rpm" className="text-sm font-semibold">
                Rate Limit (requests/minute)
              </Label>
              <Input
                id="rpm"
                type="number"
                min="0"
                max="100"
                value={preferences.rpmLimit}
                onChange={(e) => handlePreferenceChange("rpmLimit", parseInt(e.target.value) || 0)}
                className="text-xs"
              />
              <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.60)" }}>
                Set to 0 to disable rate limiting
              </p>
            </div>

          </div>

          {/* Right Column: Help Text */}
          <div className="pl-6 space-y-4 text-xs" style={{ color: "rgba(255,255,255,0.70)" }}>
            <div>
              <p className="font-semibold mb-1">🔐 API Key</p>
              <p>
                Required to use AI-powered discovery. Get a free key from{" "}
                <a
                  href="https://console.anthropic.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                  style={{ color: "rgba(147, 210, 255, 0.9)" }}
                >
                  Anthropic
                </a>
                {" "}or{" "}
                <a
                  href="https://ai.google.dev"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                  style={{ color: "rgba(147, 210, 255, 0.9)" }}
                >
                  Google AI
                </a>
              </p>
            </div>

            <div>
              <p className="font-semibold mb-1">🤖 Model Selection</p>
              <p>
                Choose which AI model to use. Sonnet and Pro offer the best balance of speed and
                accuracy. Haiku and Flash are faster but less accurate.
              </p>
            </div>

            <div>
              <p className="font-semibold mb-1">🚦 Rate Limiting</p>
              <p>
                Controls how many API calls per minute. Lower values prevent hitting rate limits.
                Default is 4 RPM.
              </p>
            </div>

            <div
              className="p-2 rounded"
              style={{ background: "rgba(255, 255, 255, 0.05)" }}
            >
              <p className="font-semibold mb-1">💾 Storage</p>
              <p>
                All preferences are saved locally in your browser. They don't sync across devices.
              </p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!hasChanges}
          >
            Save Preferences
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
