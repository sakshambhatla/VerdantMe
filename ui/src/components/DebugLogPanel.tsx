import { useCallback, useEffect, useRef, useState } from "react";
import { useMode } from "@/contexts/ModeContext";
import { supabase } from "@/lib/supabase";

interface LogEntry {
  seq: number;
  timestamp: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
}

const MAX_LOG_LINES = 500;

const LEVEL_COLORS: Record<string, string> = {
  info: "text-white/70",
  success: "text-emerald-400",
  warning: "text-yellow-400",
  error: "text-red-400",
};

export function DebugLogPanel() {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const esRef = useRef<EventSource | null>(null);
  const { mode } = useMode();

  // Connect/disconnect EventSource based on expanded state
  useEffect(() => {
    if (!expanded) {
      esRef.current?.close();
      esRef.current = null;
      setConnected(false);
      return;
    }

    let cancelled = false;

    async function connect() {
      const _base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
      let url = `${_base}/logs/stream`;

      // Append JWT as query param in managed mode (EventSource can't send headers)
      if (supabase && mode === "managed") {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token) {
          url += `?token=${encodeURIComponent(session.access_token)}`;
        }
      }

      if (cancelled) return;

      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("log", (e) => {
        const entry: LogEntry = JSON.parse((e as MessageEvent).data);
        setLogs((prev) => {
          const next = [...prev, entry];
          return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
        });
      });

      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
      };
    }

    connect();

    return () => {
      cancelled = true;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [expanded, mode]);

  // Auto-scroll to bottom unless user has scrolled up
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
          <span className="text-white/40 text-xs">{expanded ? "▼" : "▶"}</span>
          Debug Logs
        </span>
        <span className="flex items-center gap-3 text-xs">
          {connected && (
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-400/80">Live</span>
            </span>
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
              fontFamily: "ui-monospace, 'Geist Mono', 'SF Mono', Menlo, monospace",
            }}
          >
            {logs.length === 0 ? (
              <p className="text-white/25 text-xs italic py-4 text-center">
                Waiting for log output… Start a discovery operation.
              </p>
            ) : (
              logs.map((entry) => (
                <div key={entry.seq} className="text-xs leading-relaxed">
                  <span className="text-white/30 select-none">
                    [{entry.timestamp}]
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
