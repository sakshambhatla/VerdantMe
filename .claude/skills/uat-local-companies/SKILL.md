---
name: uat-local-companies
description: >
  Run a UAT of company discovery in local mode: select "Run Local", upload startup resume,
  discover 5 companies with "Startups" focus, and verify the startups badge appears on the run.
  Use this skill whenever the user says "run uat-local-companies", "test local company discovery",
  "test companies local mode", or any similar phrase about testing company discovery in local mode.
---

# UAT — Company Discovery (Local Mode)

Tests the company discovery flow end-to-end in local mode: no login, resume upload,
and company discovery with the "Startups" focus toggle.

Runs on **port 5180** (dedicated UAT UI), shares the API server on port 8000.

## Pre-flight (Step 0)

Source `~/.env` and check that the LLM API key is set. Run this in Bash:

```bash
source ~/.env 2>/dev/null
for var in GEMINI_API_KEY; do
  if [ -z "${!var}" ]; then echo "MISSING: $var"; else echo "OK: $var"; fi
done
```

Also verify the startup resume exists:

```bash
test -f /Users/sakshambhatla/workplace/JobFinder/resumes/startup_resume.txt && echo "OK: startup_resume.txt" || echo "MISSING: startup_resume.txt"
```

If anything is missing, report and abort. Do NOT proceed.

## Step 1 — Start servers

Check that the API server is running on port 8000:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/resume
```

- If the API returns 200 or 404, it's running — proceed.
- If the curl fails (connection refused), tell the user:
  "The API server on :8000 is not running. Please start it with `jobfinder serve --host 0.0.0.0 --port 8000 --reload` or let me start it."
  If the user agrees, use `preview_start(name="api-dev")` and check `preview_logs` for "Application startup complete".

Start the UAT UI server:
- `preview_start(name="uat-ui-dev")` — port 5180

Check `preview_logs` on the UI server for startup confirmation ("ready" or "Local:").

## Step 2 — Navigate & select "Run Local"

1. Clear stale mode: `preview_eval` → `localStorage.removeItem('verdantme-mode'); window.location.reload()`
2. Wait for page to settle, then `preview_screenshot` to confirm the mode selection page
3. Click "Run Local": `preview_eval` → `document.querySelectorAll('button')[0].click()`

## Step 3 — Upload startup resume

1. `preview_snapshot` to confirm the ResumeTab is visible (tabs: "Upload Resume", "Discover Companies", "Discover Roles")
2. Delete any existing resumes:
   ```javascript
   const btns = [...document.querySelectorAll('button')];
   const removeBtns = btns.filter(b => b.textContent.trim() === '' && b.closest('[role="tabpanel"]'));
   removeBtns.forEach(b => b.click());
   ```
3. Read the resume file content via Bash:
   ```bash
   cat /Users/sakshambhatla/workplace/JobFinder/resumes/startup_resume.txt
   ```
4. Upload via `preview_eval` — inject the file content into the hidden input:
   ```javascript
   (function() {
     const content = `<PASTE RESUME CONTENT HERE>`;
     const file = new File([content], 'startup_resume.txt', { type: 'text/plain' });
     const input = document.querySelector('input[type="file"]');
     const dt = new DataTransfer();
     dt.items.add(file);
     input.files = dt.files;
     input.dispatchEvent(new Event('change', { bubbles: true }));
   })()
   ```
5. Wait ~3 seconds, then `preview_snapshot`
6. **Verify**: parsed resume card showing "startup_resume.txt" with titles and skills
7. `preview_screenshot` as proof

## Step 4 — Discover 5 companies with "Startups" focus

1. Click the "Discover Companies" tab: `preview_eval` →
   ```javascript
   document.querySelectorAll('[role="tab"]')[1].click()
   ```
2. Wait ~500ms, then `preview_snapshot` to confirm CompaniesTab
3. Set max_companies to 5: use `preview_eval` to set the value:
   ```javascript
   const el = document.querySelector('#max-companies');
   const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
   setter.call(el, '5');
   el.dispatchEvent(new Event('input', { bubbles: true }));
   el.dispatchEvent(new Event('change', { bubbles: true }));
   ```
4. **Click "Startups" toggle**: Find the button with text "Startups" and click it:
   ```javascript
   document.querySelectorAll('button').forEach(b => { if (b.textContent.trim() === 'Startups') b.click() });
   ```
5. `preview_screenshot` — **verify**: "Startups" button is highlighted, helper text "Includes YC Jobs API results during role discovery" appears
6. Confirm provider is "gemini" (it's the default)
7. Click "Discover Companies" button
8. **Poll for completion** (max 120 seconds, check every 10 seconds):
   - `preview_snapshot` — look for:
     - Success: a company table appears
     - Failure: an error message
     - Still running: spinner or "Discovering..." text
9. Scroll down to PREVIOUS RUNS section
10. `preview_snapshot` — **verify**: the new run has an orange "startups" badge next to the "resume" badge
11. Check `preview_console_logs(level="error")` and `preview_logs(serverId=api, level="error")`
12. `preview_screenshot` as proof — capture the company table and the run with startups badge

## Step 5 — Report

Output a final summary table:

```
## UAT-Local-Companies Results

| Step | Status | Details |
|------|--------|---------|
| Servers | .../... | api :8000, uat-ui :5180 |
| Mode | .../... | Local mode selected |
| Resume upload | .../... | startup_resume.txt — N titles, M skills |
| Companies | .../... | N companies discovered, Startups focus |
| Startups badge | .../... | Visible / Not visible on run |

Verdict: All steps passed / Step X failed: <details>
```

## Important notes

- **No login required**: local mode has no authentication.
- **API keys from env vars**: the server reads `GEMINI_API_KEY` directly — no Vault storage needed.
- **Parallel-safe**: UAT runs on port 5180, never conflicts with dev instance on 5173.
- **Shared API**: Reuses the user's API server on port 8000.
- **CORS**: `~/.env` has `CORS_ORIGINS=http://localhost:5173,http://localhost:5180`.
- **Fail-fast**: if any step fails, capture screenshot + logs and STOP.
- **Polling, not sleeping**: check `preview_snapshot` for success/failure indicators.
- **Credentials from env vars only**: never hardcode API keys.
