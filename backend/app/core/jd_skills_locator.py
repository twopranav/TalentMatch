"""
Locates the required-skills / requirements section of a job description
and returns its raw text.

The flat-text path below (DOCX/TXT) has its own heading vocabulary,
since a JD's requirements block is bounded by headings such as
"Nice to Have", "Benefits" or "About the Team", not by resume sections
like "Experience" or "Education". The PDF path instead delegates to
app/core/jd_requirements_extractor.py, a separate, more thorough
column/font/position-aware engine (see that module's docstring) --
this file's job for PDFs is just the bytes-in/dict-out adapter around
it, `_locate_in_pdf_bytes` below.

Public API (this is exactly what tests/test_jd_locator.py imports):

    locate_jd_requirements(raw: bytes, filename: str) -> dict
        Dispatches on file type: PDF -> column-aware path, anything else
        -> text extraction + flat path. Used when the JD file is stored.

    locate_required_skills(text: str) -> dict
        Flat-text path. Also the fallback for legacy Job rows that only
        have jd_raw_text and no stored blob.

    is_section_boundary(line: str) -> bool
    split_embedded_section_boundary(line: str) -> tuple[str, str | None]

Both locate_* functions return the same shape as the resume locator:
    {"found": bool, "heading": str | None, "section_text": str}

"No requirements section" is a normal outcome (found=False), never an
exception. Corrupt or unsupported files DO raise, same as the resume
locator.

Known, deliberate quirks (kept so the tests can pin them):
- The PDF path lowercases section_text; the flat path preserves case.
  Downstream (skills_text_prep.normalize_parentheses) lowercases anyway.
- On the heading's own page, any segment whose top is at or above the
  heading's top is dropped, in every column.
"""

import os
import re

_NOT_FOUND = {"found": False, "heading": None, "section_text": ""}

_BULLET_RE = re.compile(r"^\s*([-*\u2022\u25cf\u2013>]|\d+[.)])\s+")

# Words that may stay lowercase inside a Title Case heading.
_MINOR_WORDS = {"&", "and", "or", "of", "to", "the", "a", "for", "in", "on"}

# ---------------------------------------------------------------------
# Heading vocabulary (all compared normalized: lowercase, no trailing ":")
# ---------------------------------------------------------------------

REQUIREMENT_HEADINGS = {
    "requirements",
    "required skills",
    "required qualifications",
    "required experience",
    "minimum requirements",
    "minimum qualifications",
    "basic qualifications",
    "qualifications",
    "must have",
    "must haves",
    "must-have",
    "must-haves",
    "essential skills",
    "key skills",
    "skills",
    "technical skills",
    "skills & experience",
    "skills and experience",
    "skills & qualifications",
    "what you'll need",
    "what you need",
    "what you'll bring",
    "what we're looking for",
    "who you are",
    "about you",
    "your profile",
    "your skills",
}

# Fuzzy fallback for headings not in the exact list above, e.g.
# "Required Technical Skills", "Key Requirements", "Mandatory Qualifications".
# "Preferred ..." / "Nice to have ..." are intentionally NOT prefixes here.
_REQUIREMENT_HEADING_RE = re.compile(
    r"^(required|requirements?|essential|minimum|basic|key|mandatory|core|technical|must[- ]haves?)\b"
    r".{0,40}\b(skills?|qualifications?|requirements?|experience|competenc\w+)$",
    re.IGNORECASE,
)

BOUNDARY_HEADINGS = {
    "about the role",
    "about the job",
    "about the position",
    "about us",
    "about the team",
    "about the company",
    "about",
    "the role",
    "role overview",
    "overview",
    "job description",
    "job summary",
    "summary",
    "description",
    "responsibilities",
    "key responsibilities",
    "what you'll do",
    "what you will do",
    "the opportunity",
    "nice to have",
    "nice to haves",
    "nice-to-have",
    "nice-to-haves",
    "good to have",
    "preferred",
    "preferred skills",
    "preferred qualifications",
    "bonus",
    "bonus points",
    "benefits",
    "perks",
    "perks & benefits",
    "perks and benefits",
    "what we offer",
    "we offer",
    "compensation",
    "salary",
    "company & culture",
    "our culture",
    "culture",
    "why join us",
    "why us",
    "how to apply",
    "equal opportunity employer",
    "diversity & inclusion",
    "education",
    "location",
}

_ABOUT_PREFIX_RE = re.compile(r"^(about|why|how to)\b")


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().rstrip(":")).lower()


# ---------------------------------------------------------------------
# Line classifiers (shared by both paths)
# ---------------------------------------------------------------------


def _requirements_heading_score(line: str) -> int:
    """2 = exact known heading, 1 = fuzzy match, 0 = not a heading."""
    s = line.strip()

    if not s or len(s) > 60 or _BULLET_RE.match(s) or s.endswith((".", ";", ",")):
        return 0

    n = _norm(s)

    if n in REQUIREMENT_HEADINGS:
        return 2

    if _REQUIREMENT_HEADING_RE.match(n):
        return 1

    return 0


def is_section_boundary(line: str) -> bool:
    """True if `line` looks like the heading of a *different* JD section.

    Bulleted lines and lone all-caps tokens ("SQL", "AWS") are skills,
    never headings. There is deliberately no generic "any ALL-CAPS line
    is a heading" rule, because 2-word all-caps skill lines exist.
    """
    s = line.strip()

    if not s or len(s) > 60 or _BULLET_RE.match(s):
        return False

    if _requirements_heading_score(s):
        return False

    n = _norm(s)

    if n in BOUNDARY_HEADINGS:
        return True

    return bool(_ABOUT_PREFIX_RE.match(n)) and len(n.split()) <= 5


def split_embedded_section_boundary(line: str) -> tuple[str, str | None]:
    """PDF rows sometimes glue the next heading onto the end of the last
    requirement ("own the deploy pipeline Company & Culture"). Split it.

    Only splits when the trailing words are Title Case (minor words like
    "&" / "to" excepted) AND form a known boundary heading, so prose that
    merely contains a boundary word ("our benefits platform") is left
    alone. Returns (text_before, heading_or_None).
    """
    tokens = line.split()

    for i in range(1, len(tokens)):
        tail = tokens[i:]

        if len(tail) > 5 or not tail[0][:1].isupper():
            continue

        if not all(t[:1].isupper() or t.lower() in _MINOR_WORDS for t in tail):
            continue

        candidate = " ".join(tail)

        if is_section_boundary(candidate):
            return " ".join(tokens[:i]).rstrip(), candidate

    return line, None


# ---------------------------------------------------------------------
# Flat-text path (DOCX / TXT / Job.jd_raw_text fallback)
# ---------------------------------------------------------------------


def locate_required_skills(text: str) -> dict:
    lines = (text or "").split("\n")

    best_idx, best_score = None, 0

    for i, line in enumerate(lines):
        score = _requirements_heading_score(line)

        if score > best_score:  # strict: earliest heading wins ties
            best_idx, best_score = i, score

    if best_idx is None:
        return dict(_NOT_FOUND)

    section: list[str] = []

    for line in lines[best_idx + 1 :]:
        if not line.strip():
            continue

        if _requirements_heading_score(line):
            continue  # repeated sub-heading like "Required skills:"

        if is_section_boundary(line):
            break

        head, tail = split_embedded_section_boundary(line)

        if head.strip():
            section.append(head)

        if tail:
            break

    return {
        "found": True,
        "heading": lines[best_idx].strip(),
        "section_text": "\n".join(section),
    }


# ---------------------------------------------------------------------
# PDF path (column-aware, pdfplumber word coordinates)
#
# The actual extraction engine lives in app/core/jd_requirements_extractor
# (ported from the JD requirements locator notebook). It works on a PDF
# *path*, not bytes, and returns a richer dict (confidence/page/column)
# than the rest of this app needs. `_locate_in_pdf_bytes` below is just
# the bridge: bytes -> temp file -> engine -> this module's plain
# {"found", "heading", "section_text"} shape.
# ---------------------------------------------------------------------


def _locate_in_pdf_bytes(raw: bytes) -> dict:
    import tempfile

    from app.core.jd_requirements_extractor import extract_requirements_section_from_pdf

    # The engine takes a filesystem path (it calls pdfplumber.open(path)
    # internally), so the incoming bytes are spooled to a throwaway file
    # first. delete=False because on some platforms pdfplumber can't
    # reopen a NamedTemporaryFile by name while it's still held open by
    # us; we remove it ourselves in `finally` regardless of outcome.
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)

    try:
        tmp.write(raw)
        tmp.flush()
        tmp.close()

        engine_result = extract_requirements_section_from_pdf(tmp.name)
    finally:
        os.unlink(tmp.name)

    if not engine_result["found"]:
        return dict(_NOT_FOUND)

    return {
        "found": True,
        "heading": engine_result["heading"],
        # engine_result["requirements_text"] is already stripped+lowercased
        # by the engine itself, matching this module's PDF-path quirk.
        "section_text": engine_result["requirements_text"],
    }


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def locate_jd_requirements(raw: bytes, filename: str) -> dict:
    if _get_extension(filename) == ".pdf":
        return _locate_in_pdf_bytes(raw)

    # DOCX / TXT have no page geometry; unsupported types raise
    # UnsupportedFileTypeError from extract_text_from_bytes.
    from app.core.text_extract import extract_text_from_bytes

    return locate_required_skills(extract_text_from_bytes(raw, filename))