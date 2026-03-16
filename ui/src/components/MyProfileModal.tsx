import { useState, useEffect, useRef } from "react";
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

interface MyProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: () => void;
}

export interface ProfileData {
  displayName: string;
  location: string;
  avatarDataUrl: string | null;
}

const STORAGE_KEY = "verdantme_profile";

export function loadProfile(): ProfileData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return { displayName: "", location: "", avatarDataUrl: null };
}

function saveProfile(data: ProfileData) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

/**
 * Resize an image file to 128x128 JPEG and return a base64 data URL.
 */
function resizeImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = 128;
        canvas.height = 128;
        const ctx = canvas.getContext("2d")!;
        // Draw centered/cropped square
        const size = Math.min(img.width, img.height);
        const sx = (img.width - size) / 2;
        const sy = (img.height - size) / 2;
        ctx.drawImage(img, sx, sy, size, size, 0, 0, 128, 128);
        resolve(canvas.toDataURL("image/jpeg", 0.8));
      };
      img.onerror = reject;
      img.src = reader.result as string;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function MyProfileModal({ open, onOpenChange, onSave }: MyProfileModalProps) {
  const [profile, setProfile] = useState<ProfileData>(loadProfile);
  const [hasChanges, setHasChanges] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Reload when modal opens
  useEffect(() => {
    if (open) {
      setProfile(loadProfile());
      setHasChanges(false);
    }
  }, [open]);

  const handleChange = (field: keyof ProfileData, value: string | null) => {
    setProfile((prev) => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await resizeImage(file);
      handleChange("avatarDataUrl", dataUrl);
    } catch (err) {
      console.error("Failed to process image:", err);
    }
  };

  const handleSave = () => {
    saveProfile(profile);
    setHasChanges(false);
    onSave?.();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-2xl">My Profile</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Avatar preview + upload */}
          <div className="flex flex-col items-center gap-3">
            <div
              className="h-16 w-16 rounded-full overflow-hidden flex items-center justify-center"
              style={{ background: "rgba(255,255,255,0.10)" }}
            >
              {profile.avatarDataUrl ? (
                <img
                  src={profile.avatarDataUrl}
                  alt="Profile"
                  className="h-full w-full object-cover"
                />
              ) : (
                <svg
                  className="h-8 w-8"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  viewBox="0 0 24 24"
                  style={{ color: "rgba(255,255,255,0.50)" }}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"
                  />
                </svg>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => fileRef.current?.click()}
              >
                Upload Photo
              </Button>
              {profile.avatarDataUrl && (
                <button
                  type="button"
                  onClick={() => handleChange("avatarDataUrl", null)}
                  className="text-xs underline"
                  style={{ color: "rgba(255,255,255,0.50)" }}
                >
                  Remove
                </button>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handlePhotoUpload}
              />
            </div>
          </div>

          {/* Display Name */}
          <div className="space-y-2">
            <Label htmlFor="displayName" className="text-sm font-semibold">
              Display Name
            </Label>
            <Input
              id="displayName"
              value={profile.displayName}
              onChange={(e) => handleChange("displayName", e.target.value)}
              placeholder="Your name"
              className="text-sm"
            />
          </div>

          {/* Location */}
          <div className="space-y-2">
            <Label htmlFor="location" className="text-sm font-semibold">
              Current Location
            </Label>
            <Input
              id="location"
              value={profile.location}
              onChange={(e) => handleChange("location", e.target.value)}
              placeholder="e.g., San Francisco, CA"
              className="text-sm"
            />
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
