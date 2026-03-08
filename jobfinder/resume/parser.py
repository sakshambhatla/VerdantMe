from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from jobfinder.storage.schemas import ParsedResume

SECTION_PATTERNS = [
    (re.compile(r"(?i)^(?:professional\s+)?summary|^(?:objective|profile)"), "summary"),
    (re.compile(r"(?i)^(?:work\s+)?experience|^employment"), "experience"),
    (re.compile(r"(?i)^education"), "education"),
    (re.compile(r"(?i)^(?:technical\s+)?skills|^(?:core\s+)?competencies"), "skills"),
    (re.compile(r"(?i)^projects?"), "projects"),
    (re.compile(r"(?i)^certifications?|^licenses?"), "certifications"),
    (re.compile(r"(?i)^awards?|^honors?"), "awards"),
    (re.compile(r"(?i)^publications?"), "publications"),
    (re.compile(r"(?i)^volunteer"), "volunteer"),
]

# Common delimiters in skill lists
SKILL_DELIMITERS = re.compile(r"[,;|•·\t]+")

# Pattern for "Title at Company" or "Title - Company" or "Title, Company"
TITLE_COMPANY_PATTERN = re.compile(
    r"^(.+?)\s+(?:at|@)\s+(.+?)$"
    r"|^(.+?)\s*[-–—]\s*(.+?)$",
    re.MULTILINE,
)

# Date range pattern like "Jan 2020 - Present" or "2020 - 2023"
DATE_RANGE_PATTERN = re.compile(
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
    r"(\d{4})\s*[-–—to]+\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
    r"(\d{4}|[Pp]resent|[Cc]urrent)",
    re.IGNORECASE,
)

# Known job title keywords to help identify titles
TITLE_KEYWORDS = [
    "engineer", "developer", "manager", "director", "lead", "architect",
    "analyst", "designer", "scientist", "consultant", "coordinator",
    "specialist", "administrator", "intern", "associate", "senior",
    "principal", "staff", "head", "vp", "vice president", "cto", "ceo",
    "cfo", "coo", "founder", "co-founder",
]


def parse_resumes(resume_dir: Path) -> list[ParsedResume]:
    """Parse all .txt files in the given directory."""
    txt_files = sorted(resume_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"No .txt resume files found in {resume_dir}"
        )

    resumes = []
    for txt_file in txt_files:
        text = txt_file.read_text(encoding="utf-8", errors="replace")
        resumes.append(_parse_single(txt_file.name, text))
    return resumes


def _parse_single(filename: str, text: str) -> ParsedResume:
    sections = _detect_sections(text)
    skills = _extract_skills(text, sections.get("skills", ""))
    job_titles, companies = _extract_titles_and_companies(
        sections.get("experience", text)
    )
    education = _extract_education(sections.get("education", ""))
    years = _estimate_years(sections.get("experience", text))

    return ParsedResume(
        filename=filename,
        full_text=text,
        sections=sections,
        skills=skills,
        job_titles=job_titles,
        companies_worked_at=companies,
        education=education,
        years_of_experience=years,
        parsed_at=datetime.now(timezone.utc).isoformat(),
    )


def _detect_sections(text: str) -> dict[str, str]:
    """Split text into sections based on heading patterns."""
    lines = text.splitlines()
    boundaries: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip().rstrip(":")
        if not stripped:
            continue
        for pattern, name in SECTION_PATTERNS:
            if pattern.search(stripped):
                boundaries.append((i, name))
                break

    if not boundaries:
        return {"full": text}

    sections: dict[str, str] = {}
    for idx, (line_num, name) in enumerate(boundaries):
        start = line_num + 1
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        if content:
            sections[name] = content

    return sections


def _extract_skills(full_text: str, skills_section: str) -> list[str]:
    """Extract skills from a dedicated section, or fall back to full text scan."""
    skills: set[str] = set()

    if skills_section:
        # Split by common delimiters
        for chunk in SKILL_DELIMITERS.split(skills_section):
            chunk = chunk.strip().strip("-").strip()
            if chunk and len(chunk) < 60:
                skills.add(chunk)

    # Also scan line-by-line for bullet-pointed skills
    for line in (skills_section or full_text).splitlines():
        line = line.strip()
        if line.startswith(("-", "*", "+")):
            item = line.lstrip("-*+ ").strip()
            if item and len(item) < 60:
                skills.add(item)

    return sorted(skills)


def _extract_titles_and_companies(
    experience_text: str,
) -> tuple[list[str], list[str]]:
    """Extract job titles and company names from experience text."""
    titles: list[str] = []
    companies: list[str] = []

    for match in TITLE_COMPANY_PATTERN.finditer(experience_text):
        # Group 1,2 = "Title at Company" pattern
        # Group 3,4 = "Title - Company" pattern
        title = (match.group(1) or match.group(3) or "").strip()
        company = (match.group(2) or match.group(4) or "").strip()

        if title and _looks_like_title(title):
            titles.append(title)
        if company and len(company) < 80:
            # Strip trailing dates
            company = re.sub(r"\s*\(?\d{4}.*$", "", company).strip()
            if company:
                companies.append(company)

    return titles, companies


def _looks_like_title(text: str) -> bool:
    """Heuristic: does this text look like a job title?"""
    lower = text.lower()
    return any(kw in lower for kw in TITLE_KEYWORDS)


def _extract_education(education_text: str) -> list[str]:
    """Extract education entries as plain strings."""
    if not education_text:
        return []
    entries = []
    for line in education_text.splitlines():
        line = line.strip().lstrip("-*• ")
        if line and len(line) > 5:
            entries.append(line)
    return entries


def _estimate_years(experience_text: str) -> int | None:
    """Estimate years of experience from date ranges."""
    current_year = datetime.now().year
    years_set: list[int] = []

    for match in DATE_RANGE_PATTERN.finditer(experience_text):
        start_year = int(match.group(1))
        end_str = match.group(2)
        end_year = (
            current_year
            if end_str.lower() in ("present", "current")
            else int(end_str)
        )
        if 1970 < start_year <= current_year and start_year <= end_year:
            years_set.append(end_year - start_year)

    return sum(years_set) if years_set else None
