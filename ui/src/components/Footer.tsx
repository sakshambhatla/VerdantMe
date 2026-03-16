import { Button } from "@/components/ui/button";

interface FooterProps {
  showAbout?: boolean;
  onAboutChange: (open: boolean) => void;
}

export function Footer({
  onAboutChange,
}: FooterProps) {
  const currentYear = new Date().getFullYear();
  const appVersion = "1.0.0"; // Could pull from package.json

  return (
    <footer
      className="fixed bottom-0 left-0 right-0 z-15 border-t"
      style={{
        background: "var(--glass-header-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderColor: "var(--glass-border)",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
        {/* Left: Branding */}
        <div className="flex items-center gap-2 text-sm" style={{ color: "rgba(255,255,255,0.60)" }}>
          <span className="font-semibold">VerdantMe</span>
          <span>v{appVersion}</span>
        </div>

        {/* Center: Links */}
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onAboutChange(true)}
            className="text-xs"
          >
            About
          </Button>
          <a
            href="https://github.com/sakshambhatla/VerdantMe"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center text-xs px-2 py-1 rounded hover:bg-white/10 transition-colors"
            style={{ color: "rgba(200, 235, 255, 0.7)" }}
          >
            GitHub
          </a>
          <a
            href="mailto:feedback@example.com"
            className="inline-flex items-center justify-center text-xs px-2 py-1 rounded hover:bg-white/10 transition-colors"
            style={{ color: "rgba(200, 235, 255, 0.7)" }}
          >
            Feedback
          </a>
        </div>

        {/* Right: Copyright */}
        <div className="text-xs" style={{ color: "rgba(255,255,255,0.40)" }}>
          © {currentYear}
        </div>
      </div>
    </footer>
  );
}
