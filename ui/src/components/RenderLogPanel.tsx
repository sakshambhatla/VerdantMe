import { useCallback, useEffect, useRef, useState } from "react";
import { useMode } from "@/contexts/ModeContext";
import { supabase } from "@/lib/supabase";

interface RenderLogEntry {
  id: string;
  timestamp: string;
  level: string;
  type: string;
  instance: string;
  message: string;
}

const MAX_LOG_LINES = 500;

const LEVEL_COLORS: Record<string, string> = {
  info: "text-white/70",
  success: "text-emerald-400",
  warning: "text-yellow-400",
  warn: "text-yellow-400",
  error: "text-red-400",
};

const TYPE_COLORS: Record<string, string> = {
  app: "text-sky-400/70",
  request: "text-violet-400/70",
  build: "text-amber-400/70",
};

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return iso.slice(11, 19);
  }
}

export function RenderLogPanel() {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<RenderLogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const esRef = useRef<EventSource | null>(null);
  const { mode } = useMode();

  useEffect(() => {
    if (!expanded) {
      esRef.current?.close();
      esRef.current = null;
      setConnected(false);
      return;
    }

    let cancelled = false;

    async function connect() {
      const _base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
        /\/$/,
        "",
      );
      let url = `${_base}/render-logs/stream`;

      if (supabase && mode === "managed") {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session?.access_token) {
          url += `?token=${encodeURIComponent(session.access_token)}`;
        }
      }

      if (cancelled) return;

      const es = new EventSource(url);
      esRef.current = es;

      const seenIds = new Set<string>();

      es.addEventListener("render-log", (e) => {
        const entry: RenderLogEntry = JSON.parse((e as MessageEvent).data);
        if (seenIds.has(entry.id)) return;
        seenIds.add(entry.id);
        // Cap seen set
        if (seenIds.size > 2000) seenIds.clear();

        setLogs((prev) => {
          const next = [...prev, entry];
          return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
        });
      });

      es.onopen = () => {
        setConnected(true);
        setUnavailable(false);
      };

      es.onerror = () => {
        setConnected(false);
        // If we never successfully connected, the endpoint is likely 503
        if (es.readyState === EventSource.CLOSED) {
          setUnavailable(true);
          es.close();
          esRef.current = null;
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [expanded, mode]);

  useEffect(() => {
    if (!userScrolledUp.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    userScrolledUp.current = !atBottom;
  }, []);

  return (
    <div className="mt-6">
      {/* Toggle bar */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium transition-colors"
        style={{
          background: "rgba(0, 0, 0, 0.40)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          color: "rgba(255, 255, 255, 0.55)",
          cursor: "pointer",
          borderRadius: expanded ? "12px 12px 0 0" : "12px",
        }}
      >
        <span className="flex items-center gap-2">
          <span className="text-white/40 text-xs">
            {expanded ? "\u25BC" : "\u25B6"}
          </span>
          Platform Logs (Render)
        </span>
        <span className="flex items-center gap-3 text-xs">
          {connected && (
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
              <span className="text-sky-400/80">Live</span>
            </span>
          )}
          {unavailable && (
            <span className="text-white/30">Not configured</span>
          )}
          {logs.length > 0 && (
            <span className="text-white/35">{logs.length} entries</span>
          )}
        </span>
      </button>

      {/* Terminal window */}
      {expanded && (
        <div
          className="rounded-b-xl overflow-hidden"
          style={{
            background: "rgba(0, 0, 0, 0.70)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderTop: "none",
          }}
        >
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="overflow-y-auto p-3 space-y-0.5"
            style={{
              maxHeight: "300px",
              fontFamily:
                "ui-monospace, 'Geist Mono', 'SF Mono', Menlo, monospace",
            }}
          >
            {unavailable ? (
              <p className="text-white/25 text-xs italic py-4 text-center">
                Platform log streaming is not configured on this deployment.
              </p>
            ) : logs.length === 0 ? (
              <p className="text-white/25 text-xs italic py-4 text-center">
                Connecting to Render log stream...
              </p>
            ) : (
              logs.map((entry) => (
                <div key={entry.id} className="text-xs leading-relaxed">
                  <span className="text-white/30 select-none">
                    [{formatTimestamp(entry.timestamp)}]
                  </span>{" "}
                  <span
                    className={`select-none ${TYPE_COLORS[entry.type] ?? "text-white/40"}`}
                  >
                    [{entry.type}]
                  </span>{" "}
                  <span className={LEVEL_COLORS[entry.level] ?? "text-white/70"}>
                    {entry.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
