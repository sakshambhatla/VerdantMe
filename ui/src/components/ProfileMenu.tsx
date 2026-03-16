import { useState, useCallback } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMode } from "@/contexts/ModeContext";
import { useAuth } from "@/components/AuthProvider";
import { loadProfile } from "@/components/MyProfileModal";
import { MyProfileModal } from "@/components/MyProfileModal";
import { PreferencesModal } from "@/components/PreferencesModal";
import { JobSearchPreferencesModal } from "@/components/JobSearchPreferencesModal";

export function ProfileMenu() {
  const { mode, clearMode } = useMode();
  const { user, signOut } = useAuth();

  const [showProfile, setShowProfile] = useState(false);
  const [showLLMPrefs, setShowLLMPrefs] = useState(false);
  const [showJobPrefs, setShowJobPrefs] = useState(false);

  // Force re-render when profile is saved (avatar may change)
  const [, setTick] = useState(0);
  const handleProfileSave = useCallback(() => setTick((t) => t + 1), []);

  const profile = loadProfile();

  // Determine what to show in the avatar
  const avatarContent = (() => {
    if (profile.avatarDataUrl) {
      return (
        <img
          src={profile.avatarDataUrl}
          alt="Profile"
          className="h-full w-full object-cover"
        />
      );
    }
    const initial = profile.displayName?.[0] || user?.email?.[0] || null;
    if (initial) {
      return (
        <span className="text-sm font-bold text-white uppercase">{initial}</span>
      );
    }
    return (
      <svg
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        viewBox="0 0 24 24"
        style={{ color: "rgba(255,255,255,0.70)" }}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"
        />
      </svg>
    );
  })();

  // Label for the dropdown
  const menuLabel =
    profile.displayName ||
    user?.email ||
    (mode === "local" ? "Local Mode" : "Profile");

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Profile menu"
          className="h-9 w-9 rounded-full overflow-hidden flex items-center justify-center transition-all hover:ring-2 hover:ring-white/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 cursor-pointer"
          style={{ background: "rgba(255,255,255,0.12)" }}
        >
          {avatarContent}
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="end"
          className="w-56"
          style={{
            background: "rgba(15, 20, 30, 0.85)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            borderColor: "var(--glass-border)",
          }}
        >
          {/* GroupLabel must be inside a Group in base-ui */}
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-xs truncate" style={{ color: "rgba(255,255,255,0.60)" }}>
              {menuLabel}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />

          {/* base-ui Menu.Item uses onClick, not onSelect */}
          <DropdownMenuItem onClick={() => setShowProfile(true)}>
            My Profile
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setShowLLMPrefs(true)}>
            LLM Preferences
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setShowJobPrefs(true)}>
            Job Search Preferences
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuItem onClick={clearMode}>
            Switch Mode
          </DropdownMenuItem>

          {mode === "managed" && user && (
            <DropdownMenuItem onClick={() => signOut()}>
              Sign Out
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Modals rendered outside the dropdown */}
      <MyProfileModal
        open={showProfile}
        onOpenChange={setShowProfile}
        onSave={handleProfileSave}
      />
      <PreferencesModal open={showLLMPrefs} onOpenChange={setShowLLMPrefs} />
      <JobSearchPreferencesModal open={showJobPrefs} onOpenChange={setShowJobPrefs} />
    </>
  );
}
