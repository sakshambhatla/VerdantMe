import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { useMode } from "@/contexts/ModeContext";
import { storeGoogleTokens } from "@/lib/api";

interface AuthState {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<string | null>;
  signUp: (email: string, password: string) => Promise<string | null>;
  signInWithGoogle: () => Promise<string | null>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  session: null,
  loading: true,
  signIn: async () => null,
  signUp: async () => null,
  signInWithGoogle: async () => null,
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { mode } = useMode();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase || mode === "local") {
      // Dev mode or user chose Local — no auth, immediately "ready"
      setLoading(false);
      return;
    }

    // Fetch current session on mount
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setLoading(false);
    });

    // Subscribe to auth changes (login, logout, token refresh)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);

      if (_event === "SIGNED_IN") {
        // Capture Google OAuth provider tokens for Gmail/Calendar integration.
        // provider_token is always present; provider_refresh_token may be null
        // if Google skipped the consent screen (see docs/docs.md).
        const accessToken = s?.provider_token;
        const refreshToken = s?.provider_refresh_token;
        console.info(
          "[Auth] SIGNED_IN — provider_token:",
          accessToken ? "present" : "missing",
          "| provider_refresh_token:",
          refreshToken ? "present" : "missing",
        );

        if (accessToken) {
          storeGoogleTokens(accessToken, refreshToken ?? "").catch((err) => {
            console.warn("[Auth] Failed to store Google tokens:", err);
          });
        }
      }

      if (_event === "SIGNED_OUT") {
        // Redirect to landing page on sign-out
        window.location.href = "/";
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = async (email: string, password: string): Promise<string | null> => {
    if (!supabase) return null;
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return error ? error.message : null;
  };

  const signUp = async (email: string, password: string): Promise<string | null> => {
    if (!supabase) return null;
    const { error } = await supabase.auth.signUp({ email, password });
    return error ? error.message : null;
  };

  const signInWithGoogle = async (): Promise<string | null> => {
    if (!supabase) return null;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/app`,
        scopes:
          "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.events.readonly",
        queryParams: {
          access_type: "offline",
          prompt: "consent",
        },
      },
    });
    return error ? error.message : null;
  };

  const signOut = async () => {
    if (!supabase) return;
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider
      value={{
        user: session?.user ?? null,
        session,
        loading,
        signIn,
        signUp,
        signInWithGoogle,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
