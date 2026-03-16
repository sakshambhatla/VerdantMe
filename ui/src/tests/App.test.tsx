/**
 * App navigation, header, and footer functional tests.
 * Covers: header rendering, scroll-aware compact mode, tab switching, footer links/modals.
 * Uses vi.mock to stub all API calls so no real HTTP requests are made.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModeProvider } from "@/contexts/ModeContext";
import { AuthProvider } from "@/components/AuthProvider";
import App from "@/App";

// ── Mock EventSource (not available in jsdom) ────────────────────────────────

class MockEventSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  addEventListener = vi.fn();
  close = vi.fn();
}
vi.stubGlobal("EventSource", vi.fn(() => new MockEventSource()));

// ── Mock supabase as null (dev mode — no auth) ──────────────────────────────

vi.mock("@/lib/supabase", () => ({ supabase: null }));

// ── Mock the entire API module ────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  uploadResume: vi.fn(),
  getResume: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  deleteResume: vi.fn(),
  discoverCompanies: vi.fn(),
  getCompanies: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  getCompanyRegistry: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  discoverRoles: vi.fn(),
  getRoles: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  getUnfilteredRoles: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  getRolesCheckpoint: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  fetchBrowserRoles: vi.fn(),
  browserAgentStreamUrl: vi.fn().mockResolvedValue("/api/roles/fetch-browser/stream"),
  killBrowserAgent: vi.fn(),
}));

// ── Seed local mode so ModeSelectionPage is bypassed in all tests ─────────────

beforeEach(() => {
  localStorage.setItem("verdantme-mode", "local");
});

afterEach(() => {
  localStorage.clear();
});

// ── Render helper ─────────────────────────────────────────────────────────────

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ModeProvider>
      <AuthProvider>
        <QueryClientProvider client={client}>
          <App />
        </QueryClientProvider>
      </AuthProvider>
    </ModeProvider>
  );
}

// ── Header rendering ──────────────────────────────────────────────────────────

describe("App header", () => {
  it("renders the VerdantMe heading", () => {
    renderApp();
    expect(screen.getByRole("heading", { name: /VerdantMe/i })).toBeInTheDocument();
  });

  it("renders the tagline", () => {
    renderApp();
    expect(
      screen.getByText(/Discover companies and roles matched to your resume/i)
    ).toBeInTheDocument();
  });

  it("header does not have compact class on initial render", () => {
    renderApp();
    expect(document.querySelector("header")).not.toHaveClass("compact");
  });

  it("header gains compact class after scrolling past collapse threshold", async () => {
    renderApp();
    Object.defineProperty(window, "scrollY", { configurable: true, value: 210 });
    fireEvent.scroll(window);
    await waitFor(() => {
      expect(document.querySelector("header")).toHaveClass("compact");
    });
  });

  it("header loses compact class when scrolled back above expand threshold", async () => {
    renderApp();
    // Collapse
    Object.defineProperty(window, "scrollY", { configurable: true, value: 210 });
    fireEvent.scroll(window);
    await waitFor(() => expect(document.querySelector("header")).toHaveClass("compact"));

    // Scroll back near the top (below EXPAND_SCROLL = 40)
    Object.defineProperty(window, "scrollY", { configurable: true, value: 20 });
    fireEvent.scroll(window);
    await waitFor(() => {
      expect(document.querySelector("header")).not.toHaveClass("compact");
    });
  });

  it("compact logo is present in the tab band (hidden until scrolled)", () => {
    renderApp();
    // Both the h1 and the compact span render "VerdantMe" — at least two occurrences
    expect(screen.getAllByText("VerdantMe").length).toBeGreaterThanOrEqual(2);
  });
});

// ── Tab navigation ────────────────────────────────────────────────────────────

describe("App tab navigation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders all three tab triggers", () => {
    renderApp();
    expect(screen.getByRole("tab", { name: /Upload Resume/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Discover Companies/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Discover Roles/i })).toBeInTheDocument();
  });

  it("Upload Resume tab is selected by default", () => {
    renderApp();
    expect(screen.getByRole("tab", { name: /Upload Resume/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("resume drop zone is visible on initial load", async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByText(/Drop your resume here/i)).toBeVisible();
    });
  });

  it("clicking Discover Companies marks that tab as selected", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Companies/i }));
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Discover Companies/i })).toHaveAttribute(
        "aria-selected",
        "true"
      );
    });
  });

  it("clicking Discover Companies hides the resume panel", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Companies/i }));
    // base-ui unmounts inactive panels, so the element is removed from the DOM
    await waitFor(() => {
      expect(screen.queryByText(/Drop your resume here/i)).not.toBeInTheDocument();
    });
  });

  it("clicking Discover Roles marks that tab as selected", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Roles/i }));
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Discover Roles/i })).toHaveAttribute(
        "aria-selected",
        "true"
      );
    });
  });

  it("clicking Discover Roles hides the resume panel", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Roles/i }));
    // base-ui unmounts inactive panels, so the element is removed from the DOM
    await waitFor(() => {
      expect(screen.queryByText(/Drop your resume here/i)).not.toBeInTheDocument();
    });
  });

  it("switching back to Upload Resume reselects that tab", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Companies/i }));
    fireEvent.click(screen.getByRole("tab", { name: /Upload Resume/i }));
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Upload Resume/i })).toHaveAttribute(
        "aria-selected",
        "true"
      );
    });
  });

  it("resume drop zone is visible again after switching back", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: /Discover Companies/i }));
    fireEvent.click(screen.getByRole("tab", { name: /Upload Resume/i }));
    await waitFor(() => {
      expect(screen.getByText(/Drop your resume here/i)).toBeVisible();
    });
  });
});

// ── Footer ────────────────────────────────────────────────────────────────────

describe("App footer", () => {
  it("renders a footer element", () => {
    renderApp();
    expect(document.querySelector("footer")).toBeInTheDocument();
  });

  it("footer contains VerdantMe branding", () => {
    renderApp();
    expect(document.querySelector("footer")?.textContent).toContain("VerdantMe");
  });

  it("renders the About button", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /^About$/i })).toBeInTheDocument();
  });

  it("renders the GitHub link", () => {
    renderApp();
    expect(screen.getByRole("link", { name: /GitHub/i })).toBeInTheDocument();
  });

  it("renders the Feedback link", () => {
    renderApp();
    expect(screen.getByRole("link", { name: /Feedback/i })).toBeInTheDocument();
  });

  it("clicking About opens the About modal", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("button", { name: /^About$/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("About VerdantMe")).toBeInTheDocument();
    });
  });

});

// ── Profile Menu ───────────────────────────────────────────────────────────

describe("App profile menu", () => {
  it("renders the profile menu button in the header", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /Profile menu/i })).toBeInTheDocument();
  });
});
