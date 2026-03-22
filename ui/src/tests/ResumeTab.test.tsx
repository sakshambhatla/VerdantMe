/**
 * ResumeTab component tests.
 * Uses vi.mock to stub @/lib/api so no real HTTP calls are made.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ResumeTab } from "@/components/ResumeTab";
import type { ParsedResume } from "@/lib/api";

// ── Mock the API module ────────────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  getResume: vi.fn(),
  uploadResume: vi.fn(),
  deleteResume: vi.fn(),
}));

import { getResume } from "@/lib/api";
const mockGetResume = getResume as ReturnType<typeof vi.fn>;

// ── Test helpers ───────────────────────────────────────────────────────────────

function makeResume(overrides: Partial<ParsedResume> = {}): ParsedResume {
  return {
    id: crypto.randomUUID(),
    filename: "resume.txt",
    skills: ["Python", "SQL", "Spark"],
    job_titles: ["Staff Data Engineer"],
    years_of_experience: 7,
    companies_worked_at: ["Google", "Amazon"],
    education: ["MS CS, Stanford, 2018"],
    parsed_at: new Date().toISOString(),
    ...overrides,
  };
}

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ResumeTab />
    </QueryClientProvider>
  );
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("ResumeTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the drop zone text", async () => {
    mockGetResume.mockRejectedValue({ response: { status: 404 } });
    renderTab();
    expect(screen.getByText(/Drop your resume here/i)).toBeInTheDocument();
  });

  it("shows .txt only hint", async () => {
    mockGetResume.mockRejectedValue({ response: { status: 404 } });
    renderTab();
    expect(screen.getByText(/\.txt files only/i)).toBeInTheDocument();
  });

  it("shows parsed skills when resume exists", async () => {
    mockGetResume.mockResolvedValue({ resumes: [makeResume()] });
    renderTab();
    await waitFor(() => {
      expect(screen.getByText("Python")).toBeInTheDocument();
    });
  });

  it("shows all returned skill badges", async () => {
    mockGetResume.mockResolvedValue({
      resumes: [makeResume({ skills: ["Python", "SQL", "Spark"] })],
    });
    renderTab();
    await waitFor(() => {
      expect(screen.getByText("SQL")).toBeInTheDocument();
      expect(screen.getByText("Spark")).toBeInTheDocument();
    });
  });

  it("shows job title badges when resume exists", async () => {
    mockGetResume.mockResolvedValue({
      resumes: [makeResume({ job_titles: ["Staff Data Engineer"] })],
    });
    renderTab();
    await waitFor(() => {
      expect(screen.getByText("Staff Data Engineer")).toBeInTheDocument();
    });
  });

  it("shows filename in the card header", async () => {
    mockGetResume.mockResolvedValue({
      resumes: [makeResume({ filename: "my_resume.txt" })],
    });
    renderTab();
    await waitFor(() => {
      expect(screen.getByText("my_resume.txt")).toBeInTheDocument();
    });
  });

  it("shows '+N more' badge when skills exceed 20", async () => {
    const manySkills = Array.from({ length: 25 }, (_, i) => `Skill${i}`);
    mockGetResume.mockResolvedValue({
      resumes: [makeResume({ skills: manySkills })],
    });
    renderTab();
    await waitFor(() => {
      expect(screen.getByText(/\+5 more/i)).toBeInTheDocument();
    });
  });

  it("does not show skills section when no skills", async () => {
    mockGetResume.mockResolvedValue({
      resumes: [makeResume({ skills: [] })],
    });
    renderTab();
    await waitFor(() => {
      expect(screen.queryByText("Skills")).not.toBeInTheDocument();
    });
  });
});
