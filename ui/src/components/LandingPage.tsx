import { useState, useEffect, useRef, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function LandingPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [waitlistStatus, setWaitlistStatus] = useState<
    "idle" | "loading" | "success" | "duplicate" | "error"
  >("idle");
  const [waitlistMsg, setWaitlistMsg] = useState("");

  // Typewriter animation
  const typewriterText = "Show me remote lead design roles with series A startups.";
  const [displayedText, setDisplayedText] = useState("");
  const [showCursor, setShowCursor] = useState(true);
  const typewriterRef = useRef<HTMLDivElement>(null);
  const hasStartedTyping = useRef(false);

  // Upcoming event slide-in animation
  const upcomingRef = useRef<HTMLDivElement>(null);
  const [upcomingVisible, setUpcomingVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasStartedTyping.current) {
          hasStartedTyping.current = true;
          let index = 0;
          const interval = setInterval(() => {
            index++;
            setDisplayedText(typewriterText.slice(0, index));
            if (index >= typewriterText.length) {
              clearInterval(interval);
            }
          }, 60);
        }
      },
      { threshold: 0.5 }
    );

    if (typewriterRef.current) {
      observer.observe(typewriterRef.current);
    }

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const cursorInterval = setInterval(() => {
      setShowCursor((prev) => !prev);
    }, 530);
    return () => clearInterval(cursorInterval);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setUpcomingVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 }
    );
    if (upcomingRef.current) {
      observer.observe(upcomingRef.current);
    }
    return () => observer.disconnect();
  }, []);

  async function handleWaitlist(e: FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setWaitlistStatus("loading");
    try {
      const { data } = await axios.post(`${API_BASE}/waitlist`, { email: email.trim() });
      if (data.status === "duplicate") {
        setWaitlistStatus("duplicate");
        setWaitlistMsg("You're already on the waitlist!");
      } else {
        setWaitlistStatus("success");
        setWaitlistMsg("You're on the list! We'll be in touch.");
      }
    } catch {
      setWaitlistStatus("error");
      setWaitlistMsg("Something went wrong. Please try again.");
    }
  }

  return (
    <div className="landing-page min-h-screen">
      {/* ── Nav ── */}
      <nav className="fixed top-0 w-full z-50 backdrop-blur-md" style={{ background: "rgba(19,19,19,0.5)" }}>
        <div className="flex justify-between items-center max-w-7xl mx-auto px-6 py-4 w-full">
          <Link to="/" className="text-xl font-bold tracking-tighter text-slate-100 font-headline no-underline">
            Verdant AI
          </Link>
          <div className="hidden md:flex items-center gap-8 font-medium tracking-tight text-sm" style={{ fontFamily: "Inter" }}>
            <a href="#features" className="text-white font-semibold border-b border-indigo-500 no-underline">Features</a>
            <a href="#waitlist" className="text-slate-400 hover:text-white transition-colors no-underline">Pricing</a>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/app")}
              className="text-slate-400 hover:text-white transition-colors font-medium text-sm bg-transparent border-none cursor-pointer"
            >
              Log In
            </button>
            <a
              href="#waitlist"
              className="pulse-gradient px-6 py-2 rounded-[0.75rem] font-bold text-sm scale-95 active:scale-90 transition-transform no-underline"
              style={{ color: "#0f00a4" }}
            >
              Join Waitlist
            </a>
          </div>
        </div>
      </nav>

      <main>
        {/* ── Hero ── */}
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-20">
          {/* Ambient glows */}
          <div className="absolute" style={{ top: "-10%", left: "-10%", width: "50%", height: "50%", background: "rgba(163,166,255,0.1)", filter: "blur(120px)", borderRadius: "50%" }} />
          <div className="absolute" style={{ bottom: "-10%", right: "-10%", width: "40%", height: "40%", background: "rgba(83,221,252,0.1)", filter: "blur(100px)", borderRadius: "50%" }} />

          <div className="max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center relative z-10">
            <div className="lg:col-span-7">
              {/* Beta chip */}
              <div
                className="inline-flex items-center gap-2 px-3 py-1 rounded-sm mb-8"
                style={{ background: "rgba(245,242,255,0.1)", border: "1px solid rgba(245,242,255,0.2)" }}
              >
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#53ddfc" }} />
                <span className="font-label text-xs uppercase tracking-widest" style={{ color: "#40ceed" }}>
                  Now in Private Beta
                </span>
              </div>

              <h1 className="font-headline text-5xl md:text-7xl lg:text-8xl font-black tracking-tighter leading-[0.9] mb-8">
                Your AI-powered <br />
                <span className="pulse-gradient bg-clip-text" style={{ color: "transparent", WebkitBackgroundClip: "text" }}>
                  career co-pilot.
                </span>
              </h1>

              <p className="text-lg md:text-xl max-w-xl leading-relaxed mb-10" style={{ color: "#adaaaa" }}>
                Stop hunting, start choosing. Verdant AI is your personal assistant that you naturally communicate with to accelerate every step of building your career.
              </p>

              <div className="flex flex-col sm:flex-row gap-4">
                <a
                  href="#waitlist"
                  className="pulse-gradient px-8 py-4 rounded-[0.75rem] font-bold text-lg hover:shadow-[0_0_30px_rgba(163,166,255,0.4)] transition-all text-center no-underline"
                  style={{ color: "#0f00a4" }}
                >
                  Secure Early Access
                </a>
                <button
                  onClick={() => navigate("/app")}
                  className="lp-glass-panel px-8 py-4 rounded-[0.75rem] font-bold text-lg hover:bg-white/5 transition-all text-white cursor-pointer"
                >
                  View Demo
                </button>
              </div>
            </div>

            {/* Hero visual — Personalized Matches card */}
            <div className="lg:col-span-5 relative">
              <div className="relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-[#a3a6ff] to-[#53ddfc] rounded-xl blur opacity-25 group-hover:opacity-50 transition duration-1000" />
                <div className="relative rounded-xl overflow-hidden" style={{ background: "#1a1a1a", border: "1px solid rgba(255,255,255,0.07)" }}>
                  {/* Card header */}
                  <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#10b981", boxShadow: "0 0 8px rgba(16,185,129,0.6)" }} />
                      <span className="font-label text-xs uppercase tracking-widest font-bold" style={{ color: "#e2e2e2" }}>Personalized Matches</span>
                    </div>
                    <span className="font-label text-xs uppercase tracking-widest" style={{ color: "rgba(173,170,170,0.45)" }}>Updated 2m ago</span>
                  </div>

                  {/* Job rows */}
                  {[
                    { title: "Staff Software Engineer, Platform", company: "Figma", companyColor: "#a3a6ff", salary: "$200K – $270K", location: "Remote, US", posted: "Jan 5, 2026", pct: "95%", label: "High Intent" },
                    { title: "Senior Software Engineer, Infrastructure", company: "Linear", companyColor: "#53ddfc", salary: "$190K – $255K", location: "Remote", posted: "Jan 8, 2026", pct: "92%", label: "Strong Match" },
                    { title: "Staff Engineer, Developer Tools", company: "Vercel", companyColor: "#d7d4f0", salary: "$195K – $260K", location: "Remote, US", posted: "Jan 10, 2026", pct: "90%", label: "Ideal Growth" },
                  ].map((job, i) => (
                    <div
                      key={i}
                      className="flex items-start justify-between gap-4 px-6 py-5"
                      style={{ borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.05)" : undefined }}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-bold text-sm text-white leading-snug mb-1">{job.title}</div>
                        <div className="text-xs font-semibold mb-2" style={{ color: job.companyColor }}>{job.company}</div>
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5 font-label text-xs uppercase tracking-wider" style={{ color: "rgba(173,170,170,0.6)" }}>
                          <span>{job.salary}</span>
                          <span style={{ color: "rgba(173,170,170,0.3)" }}>|</span>
                          <span>{job.location}</span>
                          <span style={{ color: "rgba(173,170,170,0.3)" }}>|</span>
                          <span>Posted {job.posted}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end shrink-0">
                        <div className="text-xl font-black font-headline" style={{ color: "#a3a6ff" }}>{job.pct}</div>
                        <div className="font-label text-xs uppercase tracking-widest" style={{ color: "rgba(173,170,170,0.5)" }}>{job.label}</div>
                      </div>
                    </div>
                  ))}

                  {/* Footer CTA */}
                  <div className="px-6 py-4">
                    <button
                      onClick={() => navigate("/app")}
                      className="w-full py-3 rounded-lg font-label text-xs uppercase tracking-widest font-bold transition-colors cursor-pointer"
                      style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(173,170,170,0.7)" }}
                    >
                      View All Open Matches
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Features Bento Grid ── */}
        <section id="features" className="py-32" style={{ background: "#131313" }}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="flex flex-col md:flex-row justify-between items-end mb-20 gap-8">
              <div className="max-w-2xl">
                <h2 className="text-4xl md:text-6xl font-black font-headline tracking-tighter mb-6">
                  Built for the <br />
                  <span style={{ color: "#adaaaa" }}>Top 1% of Talent.</span>
                </h2>
                <p className="text-lg" style={{ color: "#adaaaa" }}>
                  Verdant isn't a job board. It's an autonomous agent that handles the friction of career progression.
                </p>
              </div>
              <div
                className="font-label border-b pb-2 cursor-pointer hover:text-[#53ddfc] transition-colors"
                style={{ color: "#40ceed", borderColor: "rgba(83,221,252,0.3)" }}
              >
                Explore all capabilities
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
              {/* Feature 1: Autonomous Matching */}
              <div className="md:col-span-8 rounded-xl p-10 relative overflow-hidden group" style={{ background: "#20201f" }}>
                <div className="relative z-10 h-full flex flex-col justify-between">
                  <div>
                    <div className="text-4xl mb-6" style={{ color: "#a3a6ff" }}>&#x1F680;</div>
                    <h3 className="text-3xl font-bold mb-4">Autonomous Job Matching</h3>
                    <p className="max-w-sm leading-relaxed" style={{ color: "#adaaaa" }}>
                      Our neural engine analyzes thousands of roles per minute, identifying matches based on your implicit preferences and long-term career trajectory.
                    </p>
                  </div>
                </div>
              </div>

              {/* Feature 2: Natural Language Interaction */}
              <div className="md:col-span-4 lp-glass-panel rounded-xl p-10">
                <div className="text-4xl mb-6" style={{ color: "#53ddfc" }}>&#x1F4AC;</div>
                <h3 className="text-2xl font-bold mb-4">Natural Language Interaction</h3>
                <p className="leading-relaxed mb-8" style={{ color: "#adaaaa" }}>
                  Talk to your career portal like a human. Just say: "Find me senior dev roles in San Francisco that pay over $200k."
                </p>
                <div
                  ref={typewriterRef}
                  className="p-4 rounded-lg font-label text-xs italic"
                  style={{ background: "rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.05)", color: "#40ceed", minHeight: "2.5rem" }}
                >
                  &ldquo;{displayedText}
                  <span
                    className="inline-block w-[1px] h-[1em] align-middle ml-[1px]"
                    style={{
                      background: "#40ceed",
                      opacity: showCursor ? 1 : 0,
                      transition: "opacity 0.1s",
                    }}
                  />
                  &rdquo;
                </div>
              </div>

              {/* Feature 3: Offer Evaluation */}
              <div
                className="md:col-span-4 rounded-xl p-10 border hover:border-[rgba(163,166,255,0.3)] transition-all"
                style={{ background: "#1a1a1a", borderColor: "rgba(72,72,71,0.1)" }}
              >
                <div className="text-4xl mb-6" style={{ color: "#a3a6ff" }}>&#x1F4CA;</div>
                <h3 className="text-2xl font-bold mb-4">Offer Evaluation & Assistance</h3>
                <p className="leading-relaxed mb-6" style={{ color: "#adaaaa" }}>
                  Personalized offer analysis across culture, growth, and compensation. We weigh the pros and cons of every detail so you can join the right team with total confidence.
                </p>
                {/* Mini scorecard mockup */}
                <div className="rounded-lg p-4 flex flex-col gap-3" style={{ background: "#0d0d0d", border: "1px solid rgba(255,255,255,0.05)" }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-label uppercase tracking-widest" style={{ fontSize: "9px", color: "rgba(173,170,170,0.5)" }}>Offer Analysis</span>
                    <span className="font-label uppercase tracking-widest rounded px-2 py-0.5" style={{ fontSize: "9px", background: "#a3a6ff", color: "#0d0d0d" }}>AI Insight</span>
                  </div>
                  {[
                    { label: "Business Trajectory", score: 3, color: "#a3a6ff" },
                    { label: "Management Quality",  score: 2, color: "#f87171" },
                    { label: "Engineering Culture", score: 4, color: "#53ddfc" },
                  ].map(({ label, score, color }) => (
                    <div key={label}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-label uppercase tracking-widest" style={{ fontSize: "8px", color: "rgba(173,170,170,0.5)" }}>{label}</span>
                        <span className="font-label font-bold" style={{ fontSize: "9px", color }}>{score}/5</span>
                      </div>
                      <div className="flex gap-1">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <div key={i} className="h-1 flex-1 rounded-full" style={{ background: i < score ? color : "rgba(255,255,255,0.08)" }} />
                        ))}
                      </div>
                    </div>
                  ))}
                  <div className="mt-1 rounded p-2" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid rgba(255,255,255,0.04)" }}>
                    <span className="font-label font-bold uppercase tracking-widest mr-1" style={{ fontSize: "8px", color: "#adaaaa" }}>Verdict:</span>
                    <span style={{ fontSize: "9px", color: "#adaaaa" }}>Strong growth trajectory; check vesting acceleration clauses.</span>
                  </div>
                </div>
              </div>

              {/* Feature 4: Application Pipeline Tracking */}
              <div className="md:col-span-8 rounded-xl p-10 flex flex-col md:flex-row gap-10 items-center" style={{ background: "#262626" }}>
                <div className="flex-1">
                  <div className="text-4xl mb-6" style={{ color: "#a3a6ff" }}>&#x1F4CA;</div>
                  <h3 className="text-3xl font-bold mb-4">Application Pipeline Tracking</h3>
                  <p className="leading-relaxed" style={{ color: "#adaaaa" }}>
                    Seamlessly sync with your email, calendar, and notes. We manage the entire interview process from initial ping to final offer letter.
                  </p>
                </div>
                <div
                  className="flex-1 w-full rounded-xl p-6 flex flex-col gap-3"
                  style={{ background: "#131313", border: "1px solid rgba(255,255,255,0.05)" }}
                >
                  {/* Connected services mock */}
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-4">
                      {["#a3a6ff", "#53ddfc", "#d7d4f0"].map((color, i) => (
                        <div key={i} className="flex items-center gap-1.5">
                          <div className="w-2 h-2 rounded-full" style={{ background: "#10b981", boxShadow: "0 0 8px rgba(16,185,129,0.5)" }} />
                          <span className="text-xl" style={{ color }}>{["✉️", "📅", "📝"][i]}</span>
                        </div>
                      ))}
                    </div>
                    <div className="font-label uppercase tracking-widest" style={{ fontSize: "10px", color: "rgba(173,170,170,0.4)" }}>
                      Connected to <span style={{ color: "#22c55e" }}>3</span> services
                    </div>
                  </div>
                  <div
                    ref={upcomingRef}
                    style={{
                      borderTop: "1px solid rgba(255,255,255,0.05)",
                      paddingTop: "1rem",
                      transform: upcomingVisible ? "translateY(0)" : "translateY(24px)",
                      opacity: upcomingVisible ? 1 : 0,
                      transition: "transform 0.55s cubic-bezier(0.22,1,0.36,1), opacity 0.55s ease",
                    }}
                  >
                    <div className="font-label uppercase tracking-widest mb-2" style={{ fontSize: "10px", color: "#40ceed" }}>
                      Upcoming
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="text-sm font-bold font-headline text-white">2:30 pm</div>
                      <div className="text-xs leading-tight" style={{ color: "#adaaaa" }}>
                        Recruiter screen with <span className="text-white font-medium">Robinhood</span>: Growth EM Role
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── CTA / Waitlist ── */}
        <section id="waitlist" className="py-40 relative" style={{ background: "#0e0e0e" }}>
          <div className="absolute inset-0" style={{ background: "rgba(163,166,255,0.05)" }} />
          <div className="max-w-4xl mx-auto px-6 text-center relative z-10">
            <h2 className="text-5xl md:text-7xl font-black font-headline tracking-tighter mb-8 leading-tight">
              The future of career <br />
              <span className="italic" style={{ color: "#a3a6ff" }}>velocity</span> is here.
            </h2>
            <p className="text-xl mb-12 max-w-2xl mx-auto" style={{ color: "#adaaaa" }}>
              Secure your spot to accelerate your career search.
            </p>

            {waitlistStatus === "success" || waitlistStatus === "duplicate" ? (
              <div className="flex justify-center">
                <div
                  className="inline-flex items-center gap-3 px-8 py-4 rounded-[0.75rem] font-label text-lg"
                  style={{
                    background: waitlistStatus === "success" ? "rgba(16,185,129,0.15)" : "rgba(83,221,252,0.15)",
                    border: `1px solid ${waitlistStatus === "success" ? "rgba(16,185,129,0.3)" : "rgba(83,221,252,0.3)"}`,
                    color: waitlistStatus === "success" ? "#10b981" : "#53ddfc",
                  }}
                >
                  {waitlistStatus === "success" ? "✓" : "ℹ"} {waitlistMsg}
                </div>
              </div>
            ) : (
              <form onSubmit={handleWaitlist} className="flex flex-col sm:flex-row justify-center items-center gap-6">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full sm:w-80 px-6 py-4 rounded-[0.75rem] font-label text-white focus:outline-none transition-all"
                  style={{
                    background: "#131313",
                    border: "1px solid rgba(72,72,71,0.2)",
                  }}
                  placeholder="Enter your email"
                  disabled={waitlistStatus === "loading"}
                />
                <button
                  type="submit"
                  disabled={waitlistStatus === "loading"}
                  className="pulse-gradient px-10 py-4 rounded-[0.75rem] font-black text-lg hover:scale-105 transition-transform w-full sm:w-auto disabled:opacity-60 cursor-pointer"
                  style={{ color: "#0f00a4" }}
                >
                  {waitlistStatus === "loading" ? "Joining..." : "JOIN THE WAITLIST"}
                </button>
              </form>
            )}

            <div className="mt-8 flex justify-center items-center gap-2 font-label text-xs uppercase tracking-widest" style={{ color: "rgba(173,170,170,0.6)" }}>
              <span>&#x1F6E1;</span> Encrypted &amp; GDPR Compliant
            </div>
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="w-full py-20 px-8" style={{ background: "#000", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
        <div className="flex flex-col md:flex-row justify-between items-center gap-8 max-w-7xl mx-auto w-full">
          <div className="flex flex-col gap-4">
            <div className="text-lg font-black text-slate-200">Verdant AI</div>
            <p className="text-xs uppercase tracking-widest text-slate-500 max-w-xs text-center md:text-left" style={{ fontFamily: "Inter" }}>
              &copy; 2026 Lithodora Labs. The Intelligent Ether for Careers.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-8 text-xs uppercase tracking-widest" style={{ fontFamily: "Inter" }}>
            <Link to="/privacy" className="text-slate-500 hover:text-white transition-colors no-underline">Privacy Policy</Link>
            <a href="#" className="text-slate-500 hover:text-white transition-colors no-underline">Terms of Service</a>
            <Link to="/about" className="text-slate-500 hover:text-white transition-colors no-underline">About</Link>
            <a href="https://www.linkedin.com" target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-white transition-colors no-underline">LinkedIn</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
