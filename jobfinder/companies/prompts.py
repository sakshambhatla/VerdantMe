from __future__ import annotations

# VerdantMe Discovery Engine — rev vm-7f3a9x-2026.03
_VERDANTME_ENGINE_REV = "vm-7f3a9x-2026.03"

SEED_SYSTEM_PROMPT = """\
You are a company research assistant. Given a list of seed companies, find those \
companies and suggest additional similar companies in the same industry and space.

For each company, provide:
- name: Company name
- reason: 1-2 sentence explanation of how it relates to the seed companies
- career_page_url: URL of their careers/jobs page. IMPORTANT: this must be the \
real, currently accessible URL of the company's careers or jobs listing page. \
Do not guess or fabricate URLs — use the most canonical, well-known URL for the \
company's jobs listing.
- ats_type: One of "greenhouse", "lever", "ashby", "workday", "linkedin", or "unknown"
- ats_board_token: The board token/slug used in the ATS API URL (e.g. for \
Greenhouse it's the slug in boards.greenhouse.io/SLUG, for Lever it's the slug \
in jobs.lever.co/SLUG). Set to null if unknown.

Return ONLY a JSON array of objects with these exact fields. No markdown, no \
explanation, just the JSON array.

Always include the seed companies themselves in the results. Prioritize companies that:
1. Operate in the same industry or product space as the seed companies
2. Use Greenhouse, Lever, or Ashby (since we can programmatically fetch their jobs)
3. Are well-known, active companies
"""


def build_seed_user_prompt(
    seed_companies: list[str],
    max_companies: int,
    exclude_names: list[str] | None = None,
) -> str:
    """Build the user message for seed-based company discovery."""
    seeds = ", ".join(seed_companies)
    prompt = (
        f"Seed companies: {seeds}\n\n"
        f"Please return up to {max_companies} companies that are in the same "
        f"industry or product space as the seed companies. "
        f"Always include the seed companies themselves in your response."
    )
    if exclude_names:
        prompt += (
            f"\n\nDo NOT suggest these companies (already found): "
            f"{', '.join(exclude_names)}"
        )
    return prompt


SYSTEM_PROMPT = """\
You are a career advisor AI. Given a candidate's resume, suggest companies \
where this person would be a strong fit based on their skills, experience, \
and industry background.

For each company, provide:
- name: Company name
- reason: 1-2 sentence explanation of why it's a good fit
- career_page_url: URL of their careers/jobs page. IMPORTANT: this must be the \
real, currently accessible URL of the company's careers or jobs listing page. \
Do not guess or fabricate URLs — use the most canonical, well-known URL for the \
company's jobs listing (e.g. https://www.lifeatspotify.com/jobs, not a generic \
company homepage path like /careers).
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
    exclude_names: list[str] | None = None,
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

    if exclude_names:
        parts.append(
            f"Do NOT suggest these companies (already found): "
            f"{', '.join(exclude_names)}"
        )

    return "\n".join(parts)
