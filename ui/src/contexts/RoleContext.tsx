import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMe, type UserRole } from "@/lib/api";
import { useMode } from "@/contexts/ModeContext";
import { useAuth } from "@/components/AuthProvider";

const ROLE_HIERARCHY: Record<UserRole, number> = {
  superuser: 3,
  devtest: 2,
  customer: 1,
  guest: 0,
};

interface RoleContextValue {
  role: UserRole;
  /** Returns true if the current user's role is at or above `minRole`. */
  isAtLeast: (minRole: UserRole) => boolean;
  loading: boolean;
}

const RoleContext = createContext<RoleContextValue>({
  role: "customer",
  isAtLeast: () => false,
  loading: true,
});

export function RoleProvider({ children }: { children: ReactNode }) {
  const { mode } = useMode();
  const { user } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: mode === "managed" && !!user,
    staleTime: 2 * 60 * 1000, // 2 minutes — matches backend cache TTL
    retry: false,
  });

  const role: UserRole = mode === "local" ? "superuser" : (data?.role ?? "customer");
  const loading = mode === "managed" && !!user && isLoading;

  const value = useMemo<RoleContextValue>(
    () => ({
      role,
      isAtLeast: (minRole: UserRole) =>
        ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[minRole],
      loading,
    }),
    [role, loading],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole() {
  return useContext(RoleContext);
}
