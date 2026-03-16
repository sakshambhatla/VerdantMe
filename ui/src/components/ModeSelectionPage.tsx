import { useMode } from "@/contexts/ModeContext";
import { supabase } from "@/lib/supabase";

export function ModeSelectionPage() {
  const { setMode } = useMode();

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "var(--app-gradient)" }}
    >
      {/* Aurora background orbs (shared with App) */}
      <div className="pointer-events-none" aria-hidden="true">
        <div className="glass-orb glass-orb-1" />
        <div className="glass-orb glass-orb-2" />
        <div className="glass-orb glass-orb-3" />
      </div>
      {/* eslint-disable-next-line jsx-a11y/alt-text */}
      <img src="/vine.png" alt="" aria-hidden="true" className="vine-overlay" />

      <div className="relative z-10 w-full max-w-2xl px-6">
        {/* Header */}
        <div className="text-center mb-12">
          <h1
            className="text-6xl font-black tracking-tight text-white leading-none mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            VerdantMe
          </h1>
          <p className="text-sm" style={{ color: "rgba(255,255,255,0.50)" }}>
            Discover companies and roles matched to your resume
          </p>
        </div>

        {/* Mode cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Local card */}
          <button
            onClick={() => setMode("local")}
            className="group text-left rounded-2xl border p-7 transition-all duration-200 hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
            style={{
              background: "var(--glass-bg)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              borderColor: "var(--glass-border)",
              boxShadow: "var(--glass-shadow)",
            }}
          >
            <div className="text-4xl mb-4">🖥️</div>
            <h2 className="text-xl font-bold text-white mb-2">Run Local</h2>
            <p className="text-sm mb-5" style={{ color: "rgba(255,255,255,0.55)" }}>
              Everything stays on your machine. No account needed.
            </p>
            <ul className="space-y-1 text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>
              <li>✓ No sign-up required</li>
              <li>✓ Data stored on disk</li>
              <li>✓ Works offline</li>
            </ul>
            <div
              className="mt-6 w-full py-2 rounded-lg text-center text-sm font-semibold text-white transition-all duration-150 group-hover:opacity-90"
              style={{ background: "rgba(255,255,255,0.15)" }}
            >
              Run Local
            </div>
          </button>

          {/* Managed card */}
          <button
            onClick={() => setMode("managed")}
            disabled={!supabase}
            title={!supabase ? "Supabase not configured in this build" : undefined}
            className="group text-left rounded-2xl border p-7 transition-all duration-200 hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            style={{
              background: "var(--glass-bg)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              borderColor: "var(--glass-border)",
              boxShadow: "var(--glass-shadow)",
            }}
          >
            <div className="text-4xl mb-4">☁️</div>
            <div className="flex items-center gap-2 mb-2">
              <h2 className="text-xl font-bold text-white">Run Managed</h2>
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                style={{ background: "rgba(100,200,255,0.2)", color: "rgba(150,220,255,0.9)" }}
              >
                BETA
              </span>
            </div>
            <p className="text-sm mb-5" style={{ color: "rgba(255,255,255,0.55)" }}>
              Data syncs to the cloud. Sign in to continue.
            </p>
            <ul className="space-y-1 text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>
              <li>✓ Cloud sync</li>
              <li>✓ Access from anywhere</li>
              <li>✓ Managed infrastructure</li>
            </ul>
            <div
              className="mt-6 w-full py-2 rounded-lg text-center text-sm font-semibold text-white transition-all duration-150 group-hover:opacity-90"
              style={{
                background: supabase
                  ? "linear-gradient(135deg, rgba(56,189,248,0.35), rgba(99,102,241,0.35))"
                  : "rgba(255,255,255,0.10)",
              }}
            >
              Sign In
            </div>
          </button>
        </div>

        <p className="mt-8 text-center text-xs" style={{ color: "rgba(255,255,255,0.28)" }}>
          You can switch modes any time from the footer.
        </p>
      </div>
    </div>
  );
}
