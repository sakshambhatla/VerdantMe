---
name: uat-landing-page
description: >
  Run a UAT of the Verdant AI landing page: verify nav, hero, features bento grid,
  typewriter animation, waitlist form submission, and footer render correctly.
  Use this skill whenever the user says "run uat-landing-page", "test landing page",
  "test the marketing page", or any similar phrase about testing the landing page.
---

# UAT — Landing Page

Tests the Verdant AI landing page (`/`) end-to-end: nav, hero section, features grid,
typewriter animation, waitlist form, and footer — no login or API server required
(except for the waitlist submission step).

Runs on **port 5180** (dedicated UAT UI server).

## Pre-flight (Step 0)

No env vars required for most steps. For the waitlist submission step, read the test
email from env:

```bash
source ~/.env 2>/dev/null
if [ -z "$VERDANTME_TEST_EMAIL" ]; then echo "MISSING: VERDANTME_TEST_EMAIL (waitlist step will be skipped)"; else echo "OK: $VERDANTME_TEST_EMAIL"; fi
```

## Step 1 — Start UI server

Start the UAT UI server if not already running:
- `preview_start(name="uat-ui-dev")` — port 5180

Check `preview_logs` on the UI server for startup confirmation ("ready" or "Local:").

## Step 2 — Navigate to landing page

1. Navigate to root: `preview_eval` → `window.location.href = 'http://localhost:5180/'`
2. Wait for page to settle, then `preview_snapshot`
3. **Verify**: page title contains "VerdantMe" or "Verdant"

## Step 3 — Verify Nav

1. `preview_snapshot` — confirm the following elements are present:
   - "Verdant AI" brand text in the top-left
   - "Features" nav link
   - "Join Waitlist" button (top-right, pulse-gradient styled)
   - "Log In" button (top-right, hidden on mobile)
2. `preview_screenshot` as proof of nav

## Step 4 — Verify Hero section

1. Scroll to top: `preview_eval` → `window.scrollTo(0, 0)`
2. `preview_snapshot` — confirm:
   - "NOW IN PRIVATE BETA" chip with animated dot
   - Heading text "Your AI-powered" and "career co-pilot."
   - "Secure Early Access" CTA link
   - "View Demo" button
   - Hero visual with "Match probability" glass card showing "98.4%"
3. `preview_screenshot` as proof of hero

## Step 5 — Verify Features section

1. Click "Features" nav link: `preview_eval` → `window.location.hash = '#features'`
2. Wait ~500ms, then `preview_snapshot` — confirm:
   - Section heading: "Built for the Top 1% of Talent."
   - Feature card: "Autonomous Job Matching"
   - Feature card: "Natural Language Interaction" with typewriter area
   - Feature card: "Ghostwriter CRM"
   - Feature card: "Application Pipeline Tracking" with mock connected services
3. `preview_screenshot` as proof of features section

## Step 6 — Verify Typewriter animation

1. Scroll the "Natural Language Interaction" card into view:
   ```javascript
   document.querySelector('[ref]') || document.querySelectorAll('.lp-glass-panel')[0]?.scrollIntoView({ behavior: 'smooth' })
   ```
2. Wait ~3 seconds for typewriter to animate
3. `preview_eval` to check the typewriter text:
   ```javascript
   // Find italic text element inside the glass panel
   const panels = document.querySelectorAll('[style*="rgba(0,0,0,0.5)"]');
   panels[0]?.textContent
   ```
4. **Verify**: text contains at least partial characters from "Show me remote lead design roles with series A startups."
5. `preview_screenshot` as proof of typewriter

## Step 7 — Verify Waitlist form

1. Navigate to waitlist section: `preview_eval` → `window.location.hash = '#waitlist'`
2. Wait ~500ms, then `preview_snapshot` — confirm:
   - Section heading contains "velocity"
   - Email input visible (`input[type="email"]`)
   - "JOIN THE WAITLIST" submit button
3. Read test email: `source ~/.env && echo $VERDANTME_TEST_EMAIL`
4. If `VERDANTME_TEST_EMAIL` is set:
   - `preview_fill(selector='input[type="email"]', value=<test_email>)`
   - Click submit: `preview_eval` → `document.querySelector('form button[type="submit"]').click()`
   - Wait ~3 seconds, then `preview_snapshot`
   - **Verify**: either "You're on the list! We'll be in touch." (success) OR "You're already on the waitlist!" (duplicate) — both are passing states
5. `preview_screenshot` as proof of waitlist

## Step 8 — Verify Footer

1. Scroll to bottom: `preview_eval` → `window.scrollTo(0, document.body.scrollHeight)`
2. `preview_snapshot` — confirm:
   - "Verdant AI" brand in footer
   - "© 2026 Lithodora Labs. The Intelligent Ether for Careers." copyright
   - Links: "Privacy Policy", "Terms of Service", "About", "LinkedIn"
3. `preview_screenshot` as proof of footer

## Step 9 — Verify "About" link navigates correctly

1. Click the "About" link in the footer:
   ```javascript
   document.querySelectorAll('footer a').forEach(a => { if (a.textContent.trim() === 'About') a.click() });
   ```
2. Wait ~1 second, then `preview_snapshot`
3. **Verify**: URL contains "/about" and about page content is visible
4. Navigate back: `preview_eval` → `window.history.back()`

## Step 10 — Check console errors

1. `preview_console_logs(level="error")` — check for any JS errors
2. Any critical errors (not network/CORS warnings) → fail

## Step 11 — Report

Output a final summary table:

```
## UAT-Landing-Page Results

| Step | Status | Details |
|------|--------|---------|
| Server | .../... | uat-ui :5180 |
| Nav | .../... | Brand, Waitlist CTA, Log In present |
| Hero | .../... | Headline, CTA buttons, match probability card |
| Features | .../... | All 4 feature cards visible |
| Typewriter | .../... | Animated text visible |
| Waitlist form | .../... | Submitted — success/duplicate/skipped |
| Footer | .../... | Branding, links present |
| About nav | .../... | /about route reachable |
| Console errors | .../... | None / N errors |

Verdict: All steps passed / Step X failed: <details>
```

## Important notes

- **No API server required** for most steps — only the waitlist submission calls `/api/waitlist`.
- **No auth required** — the landing page is public.
- **Parallel-safe**: UAT runs on port 5180, never conflicts with dev instance on 5173.
- **Fail-fast**: if any step fails, capture screenshot + logs and STOP.
- **Polling, not sleeping**: check `preview_snapshot` for success/failure indicators.
- **Credentials from env vars only**: never hardcode emails.
