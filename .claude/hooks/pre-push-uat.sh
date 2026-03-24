#!/usr/bin/env bash
# Intercepts "git push origin main" and reminds Claude to run the UATs
# relevant to the files being pushed.
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

if ! echo "$COMMAND" | grep -qE 'git push.*origin.*main'; then
  exit 0
fi

# Files being pushed (commits on HEAD not yet on origin/main)
CHANGED=$(git diff --name-only origin/main..HEAD 2>/dev/null || echo "")

NEEDS_LANDING=""
NEEDS_COMPANIES=""
NEEDS_ROLES=""

# Landing page: LandingPage component, favicon/public assets, index.html, main.tsx routing, AboutPage
if echo "$CHANGED" | grep -qE \
  '(^|/)LandingPage\.tsx$|(^|/)AboutPage\.tsx$|^ui/public/|^ui/index\.html$|^ui/src/main\.tsx$|^ui/src/App\.css$'; then
  NEEDS_LANDING="true"
fi

# Companies: CompaniesTab, company discovery backend, company API routes
if echo "$CHANGED" | grep -qE \
  '(^|/)CompaniesTab\.tsx$|^jobfinder/companies/|^jobfinder/api/routes/companies'; then
  NEEDS_COMPANIES="true"
fi

# Roles: RolesTab, role discovery backend, role API routes, ATS fetchers
if echo "$CHANGED" | grep -qE \
  '(^|/)RolesTab\.tsx$|^jobfinder/roles/|^jobfinder/api/routes/roles'; then
  NEEDS_ROLES="true"
fi

# Build UAT list
UAT_SKILLS=""
if [ -n "$NEEDS_LANDING" ];    then UAT_SKILLS="${UAT_SKILLS:+$UAT_SKILLS, }uat-landing-page"; fi
if [ -n "$NEEDS_COMPANIES" ];  then UAT_SKILLS="${UAT_SKILLS:+$UAT_SKILLS, }uat-companies"; fi
if [ -n "$NEEDS_ROLES" ];      then UAT_SKILLS="${UAT_SKILLS:+$UAT_SKILLS, }uat-roles"; fi

# Default: if nothing matched (e.g. no diff or unrecognised files), prompt for all
if [ -z "$UAT_SKILLS" ]; then
  UAT_SKILLS="uat-landing-page, uat-companies, and uat-roles"
  MSG="IMPORTANT: Before pushing to main, run all managed-mode UATs (${UAT_SKILLS} skills). If UATs have already passed in this session, proceed with the push."
else
  MSG="IMPORTANT: Before pushing to main, run the managed-mode UAT(s) relevant to this change: ${UAT_SKILLS}. If these UATs have already passed in this session, proceed with the push."
fi

jq -n --arg msg "$MSG" '{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "additionalContext": $msg
  }
}'
