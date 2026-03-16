import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { queryClient } from "@/lib/queryClient";

export type AppMode = "local" | "managed";

interface ModeContextValue {
  mode: AppMode | null; // null = not yet chosen
  setMode: (m: AppMode) => void;
  clearMode: () => void; // resets to null, shows ModeSelectionPage again
}

const STORAGE_KEY = "verdantme-mode";

function readStoredMode(): AppMode | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === "local" || raw === "managed") return raw;
  return null;
}

const ModeContext = createContext<ModeContextValue>({
  mode: null,
  setMode: () => {},
  clearMode: () => {},
});

export function useMode() {
  return useContext(ModeContext);
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<AppMode | null>(readStoredMode);

  const setMode = useCallback((m: AppMode) => {
    localStorage.setItem(STORAGE_KEY, m);
    setModeState(m);
  }, []);

  const clearMode = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    // Flush all cached server data so local and managed data don't bleed
    queryClient.clear();
    setModeState(null);
  }, []);

  return (
    <ModeContext.Provider value={{ mode, setMode, clearMode }}>
      {children}
    </ModeContext.Provider>
  );
}
