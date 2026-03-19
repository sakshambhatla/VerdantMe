---
name: run-all-checks
description: >
  Run all pre-commit checks: CLI tests (pytest), UI tests (vitest), and security
  review — in sequence. Use this skill whenever the user says "run all checks",
  "run all tests", "full check", "pre-commit checks", or any similar phrase about
  running the complete test/review suite. Also use this proactively before any
  commit that touches both backend and frontend code.
---

# Run All Checks

Run the full pre-commit check suite: backend tests, frontend tests, and security review.

## Steps

### 1. Run CLI / backend tests

```bash
cd /Users/sakshambhatla/workplace/JobFinder
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Parse output: total collected, passed/failed/skipped. If any fail, report and continue.

### 2. Run UI / frontend tests

```bash
/Users/sakshambhatla/.nvm/versions/node/v20.20.1/bin/pnpm --dir /Users/sakshambhatla/workplace/JobFinder/ui test
```

Parse output: test files, passed/failed. If any fail, report and continue.

### 3. Run security review

Review recent code changes (`git diff HEAD`) for:
- 🔴 Hardcoded secrets, PII, auth bypasses, injection vulnerabilities
- 🟡 CORS changes, missing validation, new env vars not in .env.example
- 🟢 Future auth/rate-limit needs

Append findings to `security-concerns.md` (gitignored).

### 4. Report summary

Output a single summary:
```
## Pre-Commit Check Results

### Backend Tests
✅ 64/64 passed  OR  ❌ N failed (list failures)

### Frontend Tests
✅ 12/12 passed  OR  ❌ N failed (list failures)

### Security Review
✅ Clean  OR  ⚠️ N issue(s) (list findings)

### Verdict
✅ Ready to commit  OR  ❌ Fix N issue(s) before committing
```
