import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

function getOrCreateSessionId(): string {
  const KEY = "verdantme-session-id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(KEY, id);
  }
  return id;
}

/**
 * Fire-and-forget page view tracking on route changes.
 * Must be rendered inside `<BrowserRouter>`.
 */
export function usePageView() {
  const location = useLocation();
  const lastPath = useRef<string | null>(null);

  useEffect(() => {
    if (location.pathname === lastPath.current) return;
    lastPath.current = location.pathname;

    fetch(`${API_BASE}/analytics/pageview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: getOrCreateSessionId(),
        page_path: location.pathname,
        referrer: document.referrer || null,
        user_agent: navigator.userAgent,
        screen_width: window.screen.width,
        screen_height: window.screen.height,
      }),
    }).catch(() => {});
  }, [location.pathname]);
}
