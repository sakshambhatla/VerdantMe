import { useState, useEffect, useLayoutEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResumeTab } from "@/components/ResumeTab";
import { CompaniesTab } from "@/components/CompaniesTab";
import { RolesTab } from "@/components/RolesTab";
import { DebugLogPanel } from "@/components/DebugLogPanel";
import { Footer } from "@/components/Footer";
import { AboutModal } from "@/components/AboutModal";
import { ProfileMenu } from "@/components/ProfileMenu";
import { useAuth } from "@/components/AuthProvider";
import { LoginPage } from "@/components/LoginPage";
import { ModeSelectionPage } from "@/components/ModeSelectionPage";
import { useMode } from "@/contexts/ModeContext";
import { supabase } from "@/lib/supabase";

// Scroll thresholds with hysteresis.
//
// WHY: the title block is ~130px tall. When it collapses, scroll-anchoring
// adjusts window.scrollY downward by roughly that amount. A threshold smaller
// than the title height causes the adjusted scrollY to fall back below the
// threshold → header expands → scrollY jumps back up → rapid oscillation.
//
// With hysteresis the collapse threshold is set well above
// (EXPAND_THRESHOLD + title_height), so the post-collapse scrollY can never
// drop below the expand threshold.
const COLLAPSE_SCROLL = 200; // px — collapse only after scrolling this far
const EXPAND_SCROLL   =  40; // px — expand only when back within 40px of top

function App() {
  // ── All hooks must come first — no conditional returns before this line ──────
  const { mode } = useMode();
  const { user, loading: authLoading } = useAuth();
  const [showAbout, setShowAbout] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // Header ref for ResizeObserver; spacer ref for direct DOM height sync.
  // We bypass React state for the spacer height so 60fps animation frames
  // don't trigger re-renders.
  const headerRef = useRef<HTMLElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);

  // Keep the spacer in sync with the header's live height throughout the CSS
  // transition. Uses ResizeObserver so pixel values never need hard-coding.
  //
  // NOTE: deps include `mode`, `authLoading`, and `user` because the header is
  // only rendered once the app is past all conditional gates:
  //   • mode === null           → ModeSelectionPage (no header)
  //   • managed + authLoading   → spinner (no header)
  //   • managed + !user         → LoginPage (no header)
  // Any of these transitions can reveal the header without `mode` changing, so
  // we must re-run whenever any of them flip.
  useLayoutEffect(() => {
    const header = headerRef.current;
    const spacer = spacerRef.current;
    if (!header || !spacer) return;

    spacer.style.height = header.offsetHeight + "px";
    const ro = new ResizeObserver(() => {
      spacer.style.height = header.offsetHeight + "px";
    });
    ro.observe(header);
    return () => ro.disconnect();
  }, [mode, authLoading, user]);

  // Scroll detection with hysteresis (see constants above).
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled((prev) => {
        if (prev) return y > EXPAND_SCROLL;   // compact → stay compact unless near top
        return y > COLLAPSE_SCROLL;           // expanded → collapse only past threshold
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // ── Conditional renders (all hooks above are always called) ─────────────────

  // Step 1: no mode chosen yet → show landing page
  if (mode === null) {
    return <ModeSelectionPage />;
  }

  // Step 2: managed mode auth gate
  if (mode === "managed" && supabase && authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--app-gradient)" }}>
        <span className="h-10 w-10 animate-spin rounded-full border-4 border-white border-t-transparent" />
      </div>
    );
  }
  if (mode === "managed" && supabase && !user) {
    return <LoginPage />;
  }

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: "var(--app-gradient)" }}>
      {/* Aurora background orbs */}
      <div className="pointer-events-none" aria-hidden="true">
        <div className="glass-orb glass-orb-1" />
        <div className="glass-orb glass-orb-2" />
        <div className="glass-orb glass-orb-3" />
      </div>

      {/* Decorative vine — climbs up the right edge on load */}
      {/* eslint-disable-next-line jsx-a11y/alt-text */}
      <img src="/vine.png" alt="" aria-hidden="true" className="vine-overlay" />

      <Tabs defaultValue="resume">
        {/*
          Fixed header — position:fixed removes it from document flow entirely.
          This is intentional: sticky inside overflow:hidden scrolls away;
          fixed always stays at the top regardless of scroll or overflow on
          any ancestor.
        */}
        <header
          ref={headerRef}
          className={`fixed top-0 left-0 right-0 z-50${scrolled ? " compact" : ""}`}
          style={{
            background: "var(--glass-header-bg)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
          }}
        >
          {/* Title block — collapses when scrolled */}
          <div
            className="overflow-hidden"
            style={{
              borderBottom: scrolled ? "none" : `1px solid var(--glass-border)`,
              maxHeight: scrolled ? "0px" : "160px",
              opacity: scrolled ? 0 : 1,
              transition: "max-height 0.3s ease-in-out, opacity 0.25s ease-in-out",
            }}
          >
            <div className="py-7 text-center">
              <Link to="/" className="no-underline">
                <h1
                  className="text-5xl font-black tracking-tight text-white leading-none hover:opacity-80 transition-opacity"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  Verdant AI
                </h1>
              </Link>
              <p className="mt-2 text-sm" style={{ color: "rgba(255,255,255,0.50)" }}>
                Discover companies and roles matched to your resume
              </p>
            </div>
          </div>

          {/* Tab band — always visible; three-column layout keeps tabs centered */}
          <div
            className="border-b"
            style={{ borderColor: "var(--glass-border)" }}
          >
            <div className="flex items-center px-6">
              {/* Left: compact logo — slides in when scrolled */}
              <div className="flex items-center" style={{ minWidth: "36px" }}>
                <Link
                  to="/"
                  className="no-underline font-black text-white hover:opacity-80 transition-opacity"
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "1.25rem",
                    opacity: scrolled ? 1 : 0,
                    maxWidth: scrolled ? "200px" : "0px",
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    marginRight: scrolled ? "1rem" : "0",
                    transition: "opacity 0.3s ease-in-out, max-width 0.3s ease-in-out, margin-right 0.3s ease-in-out",
                  }}
                >
                  Verdant AI
                </Link>
              </div>

              {/* Center: tabs — always visually centered */}
              <div className="flex-1 flex justify-center">
                <TabsList>
                  <TabsTrigger value="resume">📄 Upload Resume</TabsTrigger>
                  <TabsTrigger value="companies">🏢 Discover Companies</TabsTrigger>
                  <TabsTrigger value="roles">💼 Discover Roles</TabsTrigger>
                </TabsList>
              </div>

              {/* Right: profile avatar */}
              <div style={{ minWidth: "36px" }} className="flex justify-end">
                <ProfileMenu />
              </div>
            </div>
          </div>
        </header>

        {/*
          Spacer — mirrors the fixed header's live height so page content is
          never hidden behind the header. Height is updated directly via the
          ResizeObserver above (no React re-renders needed).
        */}
        <div ref={spacerRef} aria-hidden="true" />

        {/* Page content — bottom padding for fixed footer */}
        <main className="relative z-10 max-w-6xl mx-auto px-6 py-8 pb-20">
          <TabsContent value="resume">
            <ResumeTab />
          </TabsContent>
          <TabsContent value="companies">
            <CompaniesTab />
          </TabsContent>
          <TabsContent value="roles">
            <RolesTab />
          </TabsContent>
          {mode === "local" && <DebugLogPanel />}
        </main>
      </Tabs>

      {/* Footer with About modal */}
      <Footer onAboutChange={setShowAbout} />
      <AboutModal open={showAbout} onOpenChange={setShowAbout} />
    </div>
  );
}

export default App;
