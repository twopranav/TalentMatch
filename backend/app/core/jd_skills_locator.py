"""
Locates the "required skills" section of a job description and returns
its raw text.

Mirrors skills_pdf_locator.py's flat-text fallback path (_locate_in_text),
not its column-aware PDF path: unlike Resume, Job stores no file blob at
extraction time (see the storage-parity work in progress), only
Job.jd_raw_text, a plain linear string with no page/column geometry to
reconstruct. So there's only one path here, not two.

Heading vocabulary is JD-specific, not resume-specific: a JD's skills
section is usually explicitly framed as a requirement ("Required
Skills", "Must Have", "Minimum Qualifications"), separate from a
"Nice to Have" / "Preferred Qualifications" section that must NOT be
swept in -- those are optional, not required, and mixing them in would
corrupt what the compulsory-skills pipeline is trying to isolate. That
split is why NICE_TO_HAVE_HEADINGS exists as its own boundary set,
distinct from MAJOR_SECTION_HEADINGS: a JD skills section should stop at
either.

Same return shape as skills_pdf_locator.locate_skills_section(), same
"never raises for not-found" contract:
    {"found": bool, "section_text": str, "heading": str | None}
"""

import re

# ---------------------------------------------------------------------
# Heading detection, tuned for JD vocabulary.
# ---------------------------------------------------------------------

STRONG_SKILLS_HEADINGS = {
    "required skills",
    "requirements",
    "required qualifications",
    "minimum qualifications",
    "minimum requirements",
    "must have",
    "must-haves",
    "must haves",
    "compulsory skills",
    "mandatory skills",
    "mandatory requirements",
    "skills required",
    "skills",
    "technical requirements",
    "technical skills",
    "what you'll need",
    "what you will need",
    "what we're looking for",
    "what we are looking for",
    "qualifications",
    "basic qualifications",
}

HEADING_KEYWORDS = re.compile(
    r"\b("
    r"required|requirements?|"
    r"qualifications?|"
    r"must[\s-]?have(?:s)?|"
    r"compulsory|mandatory|"
    r"skills?|"
    r"technical|"
    r"minimum"
    r")\b",
    re.IGNORECASE,
)

SCORE_THRESHOLD = 3.0

# Sections that mark the end of the required-skills section but are
# still part of the JD proper (as opposed to NICE_TO_HAVE_HEADINGS,
# which are the specific case of optional-skills content that must
# never be swept into a *required*-skills section).
MAJOR_SECTION_HEADINGS = {
    "responsibilities",
    "role",
    "about the role",
    "key responsibilities",
    "what you'll do",
    "what you will do",
    "about us",
    "about the company",
    "about the team",
    "company overview",
    "benefits",
    "perks",
    "compensation",
    "salary",
    "how to apply",
    "equal opportunity",
    "equal opportunity employer",
    "location",
}

NICE_TO_HAVE_HEADINGS = {
    "nice to have",
    "nice-to-haves",
    "nice to haves",
    "preferred qualifications",
    "preferred skills",
    "bonus points",
    "bonus skills",
    "good to have",
    "good-to-haves",
    "pluses",
    "a plus",
}

_ALL_BOUNDARY_HEADINGS = MAJOR_SECTION_HEADINGS | NICE_TO_HAVE_HEADINGS


def _normalize_heading_text(line: str) -> str:
    normalized = line.strip().rstrip(":")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def _score_heading_candidate(line: str, following_lines: list[str]) -> float:
    stripped = line.strip()

    if not stripped:
        return 0.0

    normalized = _normalize_heading_text(stripped)

    if normalized in _ALL_BOUNDARY_HEADINGS:
        return 0.0

    score = 0.0

    if normalized in STRONG_SKILLS_HEADINGS:
        score += 8.0

    if len(stripped) < 60:
        score += 1.0

    if stripped.isupper() or stripped.istitle():
        score += 1.0

    if stripped.endswith(":"):
        score += 1.0

    has_heading_keyword = bool(HEADING_KEYWORDS.search(stripped))

    if has_heading_keyword:
        score += 2.0

    following_text = " ".join(following_lines[:3])

    if has_heading_keyword and following_text:
        # Requirement lines are usually one bullet per line rather than
        # comma-separated, unlike a resume's skills line -- so density
        # of short following lines (bullets) is the JD-side signal,
        # in place of the resume locator's comma-density check.
        short_line_ratio = sum(
            1 for ln in following_lines[:3] if ln.strip() and len(ln.strip()) < 100
        ) / max(len([ln for ln in following_lines[:3] if ln.strip()]), 1)

        if short_line_ratio > 0.5:
            score += 1.5

    if normalized in STRONG_SKILLS_HEADINGS:
        score = max(score, 9.0)

    return score


def _is_section_boundary(line: str) -> bool:
    stripped = line.strip().rstrip(":")
    normalized = re.sub(r"\s+", " ", stripped).lower()

    if not normalized:
        return False

    if normalized in _ALL_BOUNDARY_HEADINGS:
        return True

    return stripped.isupper() and len(stripped) < 40


def locate_required_skills(jd_text: str) -> dict:
    """
    Locate the required-skills section of a job description.

    Returns {"found": bool, "section_text": str, "heading": str | None}.
    Never raises for "no section found" -- found=False is a normal,
    expected outcome the caller turns into a clean FAILED status, not a
    crash, matching skills_pdf_locator.locate_skills_section()'s
    contract.
    """
    if not jd_text:
        return {"found": False, "section_text": "", "heading": None}

    lines = jd_text.split("\n")

    scores = [
        _score_heading_candidate(line, lines[i + 1 : i + 4])
        for i, line in enumerate(lines)
    ]

    if not scores:
        return {"found": False, "section_text": "", "heading": None}

    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_score = scores[best_idx]

    if best_score < SCORE_THRESHOLD:
        return {"found": False, "section_text": "", "heading": None}

    heading_text = lines[best_idx].strip()

    section_lines = []

    for line in lines[best_idx + 1 :]:
        if _is_section_boundary(line):
            break

        if line.strip():
            section_lines.append(line)

    return {
        "found": True,
        "section_text": "\n".join(section_lines),
        "heading": heading_text,
    }