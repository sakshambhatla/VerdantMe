from __future__ import annotations

SYSTEM_PROMPT = """\
You are a career advisor AI. Given a candidate's resume, suggest companies \
where this person would be a strong fit based on their skills, experience, \
and industry background.

For each company, provide:
- name: Company name
- reason: 1-2 sentence explanation of why it's a good fit
- career_page_url: URL of their careers/jobs page
- ats_type: One of "greenhouse", "lever", "ashby", "workday", "linkedin", or "unknown"
- ats_board_token: The board token/slug used in the ATS API URL (e.g. for \
Greenhouse it's the slug in boards.greenhouse.io/SLUG, for Lever it's the slug \
in jobs.lever.co/SLUG). Set to null if unknown.

Return ONLY a JSON array of objects with these exact fields. No markdown, no \
explanation, just the JSON array.

Prioritize companies that:
1. Are actively hiring in roles matching the candidate's experience
2. Use Greenhouse, Lever, or Ashby (since we can programmatically fetch their jobs)
3. Operate in industries relevant to the candidate's background
"""


def build_user_prompt(
    resumes: list[dict],
    max_companies: int,
) -> str:
    """Build the user message from parsed resume data."""
    parts: list[str] = []

    for r in resumes:
        parts.append(f"=== Resume: {r['filename']} ===\n{r['full_text']}\n")

    # Aggregate extracted fields across all resume versions
    all_skills: list[str] = []
    all_titles: list[str] = []
    all_companies: list[str] = []
    for r in resumes:
        all_skills.extend(r.get("skills", []))
        all_titles.extend(r.get("job_titles", []))
        all_companies.extend(r.get("companies_worked_at", []))

    if all_skills:
        parts.append(f"Extracted skills: {', '.join(set(all_skills))}")
    if all_titles:
        parts.append(f"Recent job titles: {', '.join(set(all_titles))}")
    if all_companies:
        parts.append(f"Previous employers: {', '.join(set(all_companies))}")

    parts.append(f"\nPlease suggest up to {max_companies} companies that would be a good fit.")

    return "\n".join(parts)
