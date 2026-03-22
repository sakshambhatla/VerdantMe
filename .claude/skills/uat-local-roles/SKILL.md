---
name: uat-local-roles
description: >
  Run a UAT of role discovery in local mode: select "Run Local", navigate to Discover Roles,
  pick an existing company run, run discovery with semantic filtering, and verify roles appear.
  Use this skill whenever the user says "run uat-local-roles", "test local role discovery",
  "test roles local mode", or any similar phrase about testing role discovery in local mode.
---

# UAT — Role Discovery (Local Mode)

Tests the role discovery flow end-to-end in local mode: no login, select an existing
company run, configure filters, and run discovery.

Runs on **port 5180** (dedicated UAT UI), shares the API server on port 8000.

## Pre-flight (Step 0)

Source `~/.env` and check that the LLM API key is set. Run this in Bash:

```bash
source ~/.env 2>/dev/null
for var in GEMINI_API_KEY; do
  if [ -z "${!var}" ]; then echo "MISSING: $var"; else echo "OK: $var"; fi
done
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

## Step 3 — Navigate to Discover Roles and pick a run

1. Click the "Discover Roles" tab: `preview_eval` →
   ```javascript
   document.querySelectorAll('[role="tab"]')[2].click()
   ```
2. Wait ~500ms, then `preview_snapshot` to confirm RolesTab
3. Switch company source to "Pick a Run":
   ```javascript
   document.querySelectorAll('button').forEach(b => { if (b.textContent.trim() === 'Pick a Run') b.click() });
   ```
4. Wait ~500ms, then `preview_snapshot` to see the run dropdown
5. Select the **second** run in the dropdown (not the latest — pick an older one):
   ```javascript
   const select = document.querySelector('#company-run-select');
   if (select && select.options.length > 1) {
     select.selectedIndex = 1;
     select.dispatchEvent(new Event('change', { bubbles: true }));
   }
   ```
6. `preview_screenshot` — **verify**: a company run is selected

## Step 4 — Configure filters and run discovery

1. Scroll to the filter section
2. Set a title filter: `preview_fill(selector="#title-filter", value="Engineer")`
3. Select "Semantic" filter strategy:
   ```javascript
   document.querySelectorAll('button').forEach(b => { if (b.textContent.trim() === 'Semantic') b.click() });
   ```
4. Check "Use cached results":
   ```javascript
   const checkboxes = [...document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')];
   const cacheCheckbox = checkboxes.find(c => {
     const parent = c.closest('div') || c.parentElement;
     return parent && parent.textContent.includes('cached');
   });
   if (cacheCheckbox) cacheCheckbox.click();
   ```
5. Click "Discover Roles":
   ```javascript
   document.querySelectorAll('button').forEach(b => { if (b.textContent.trim() === 'Discover Roles') b.click() });
   ```
6. **Poll for completion** (max 300 seconds, check every 15 seconds):
   - `preview_snapshot` — look for:
     - Success: a roles table with rows (Score, Company, Title columns)
     - Failure: an error message
     - Still running: spinner or "Discovering..." text
7. Click the "Filtered" tab to see filtered results
8. Check `preview_console_logs(level="error")` and `preview_logs(serverId=api, level="error")`
9. `preview_screenshot` as proof — capture the roles table

## Step 5 — Report

Output a final summary table:

```
## UAT-Local-Roles Results

| Step | Status | Details |
|------|--------|---------|
| Servers | .../... | api :8000, uat-ui :5180 |
| Mode | .../... | Local mode selected |
| Company run | .../... | Selected run: <run_name> |
| Roles | .../... | N total roles, M after semantic filter |

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
- **Prerequisite**: At least one local-mode company discovery run must already exist. Run `uat-local-companies` first if needed.
