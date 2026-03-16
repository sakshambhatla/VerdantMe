/**
 * API helper function tests — pure logic, no HTTP calls.
 * Tests the browserAgentStreamUrl helper and TypeScript types.
 */
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/supabase", () => ({ supabase: null }));

import { browserAgentStreamUrl } from "@/lib/api";

describe("browserAgentStreamUrl", () => {
  it("encodes the company name", async () => {
    const url = await browserAgentStreamUrl("Stripe & Co");
    expect(url).toContain("Stripe%20%26%20Co");
  });

  it("returns a path starting with /api", async () => {
    const url = await browserAgentStreamUrl("Netflix");
    expect(url).toMatch(/^\/api\//);
  });

  it("includes the company_name query param", async () => {
    const url = await browserAgentStreamUrl("Netflix");
    expect(url).toContain("company_name=Netflix");
  });

  it("points to the stream endpoint", async () => {
    const url = await browserAgentStreamUrl("Figma");
    expect(url).toContain("/roles/fetch-browser/stream");
  });
});
