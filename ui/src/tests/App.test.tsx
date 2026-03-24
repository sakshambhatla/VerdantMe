/**
 * App navigation, header, and content functional tests.
 * Covers: top nav rendering, tab switching, content rendering, profile menu.
 * Uses vi.mock to stub all API calls so no real HTTP requests are made.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
  getApiKeyStatus: vi.fn().mockResolvedValue({ anthropic: false, gemini: false }),
  storeApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  getMotivation: vi.fn().mockResolvedValue(null),
  sendMotivationChat: vi.fn(),
  deleteMotivation: vi.fn(),
  // Pipeline
  getPipelineEntries: vi.fn().mockResolvedValue({ entries: [], total: 0 }),
  getPipelineStats: vi.fn().mockResolvedValue({ stage_counts: {}, total: 0 }),
  getPipelineUpdates: vi.fn().mockResolvedValue({ updates: [], total: 0 }),
  createPipelineEntry: vi.fn(),
  updatePipelineEntry: vi.fn(),
  deletePipelineEntry: vi.fn(),
  reorderPipelineEntries: vi.fn(),
  // Pipeline sync
  getGoogleTokenStatus: vi.fn().mockResolvedValue({ connected: false }),
  storeGoogleTokens: vi.fn().mockResolvedValue(undefined),
  deleteGoogleTokens: vi.fn(),
  syncPipeline: vi.fn(),
  applySyncSuggestions: vi.fn(),
}));

// ── Seed local mode so ModeSelectionPage is bypassed in all tests ─────────────

beforeEach(() => {
  localStorage.setItem("verdantme-mode", "local");
});

afterEach(() => {
  localStorage.clear();
});

// ── Render helper ─────────────────────────────────────────────────────────────

function renderApp(initialRoute = "/app") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ModeProvider>
      <AuthProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[initialRoute]}>
            <App />
          </MemoryRouter>
        </QueryClientProvider>
      </AuthProvider>
    </ModeProvider>
  );
}

// ── Top navigation ──────────────────────────────────────────────────────────

describe("App top navigation", () => {
  it("renders the Verdant AI logo", () => {
    renderApp();
    expect(screen.getAllByText("Verdant AI").length).toBeGreaterThanOrEqual(1);
  });

  it("renders all four top nav buttons", () => {
    renderApp();
    // Top nav buttons (hidden on mobile via md:flex, but still in DOM)
    expect(screen.getByRole("button", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Craft Resume" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discover Roles" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pipeline" })).toBeInTheDocument();
  });

  it("Craft Resume is active by default (resume tab)", () => {
    renderApp();
    const btn = screen.getByRole("button", { name: /Craft Resume/i });
    expect(btn.className).toContain("text-[#a3a6ff]");
  });
});

// ── Content rendering ────────────────────────────────────────────────────────

describe("App content", () => {
  it("shows Craft Resume hero heading on initial load", () => {
    renderApp();
    // The h1 contains "Craft " text node + <span>Resume</span>
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Craft Resume");
  });

  it("shows upload drop zone text", async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByText(/Drop your dossier here/i)).toBeVisible();
    });
  });

  it("clicking Discover Roles switches content", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("button", { name: /Discover Roles/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Drop your dossier here/i)).not.toBeInTheDocument();
    });
  });

  it("clicking Craft Resume shows upload area again", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("button", { name: /Discover Roles/i }));
    fireEvent.click(screen.getByRole("button", { name: /Craft Resume/i }));
    await waitFor(() => {
      expect(screen.getByText(/Drop your dossier here/i)).toBeVisible();
    });
  });
});

// ── Profile Menu ───────────────────────────────────────────────────────────

describe("App profile menu", () => {
  it("renders the profile menu button", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /Profile menu/i })).toBeInTheDocument();
  });
});

// ── Job Pipeline page ─────────────────────────────────────────────────────

describe("Job Pipeline page", () => {
  it("renders pipeline page at /app/pipeline", () => {
    renderApp("/app/pipeline");
    // The page shows a loading spinner while fetching pipeline data
    expect(screen.getByText(/Loading pipeline/i)).toBeInTheDocument();
  });

  it("renders the Pipeline nav button", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /^Pipeline$/i })).toBeInTheDocument();
  });

  it("does not show upload content on /app/pipeline", () => {
    renderApp("/app/pipeline");
    expect(screen.queryByText(/Drop your dossier here/i)).not.toBeInTheDocument();
  });
});
