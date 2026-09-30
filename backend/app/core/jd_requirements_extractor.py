"""
Deterministic, column-aware extractor for a job description's
requirements / required-skills section, read directly from a PDF's
word coordinates (font, size, x/y position) rather than plain text.

Ported as-is from the JD requirements locator notebook
(jd_requirements_locator_batch_tester.ipynb, sections 3-5: heading
vocabulary and text helpers, PDF layout helpers, and the single
authoritative extractor). The notebook's Colab upload cell and its
"quick sanity checks" cell are intentionally left out here -- this
module is only the extraction engine itself.

Public entry point:

    extract_requirements_section_from_pdf(pdf_path: str | Path) -> dict

Returns:
    {
        "found": bool,
        "file": str,               # pdf_path.name
        "heading": str | None,     # the heading text as it appears in the PDF
        "confidence": float,       # 0.0-1.0, see _heading_confidence()
        "page": int | None,        # 1-indexed page the heading was found on
        "column": str | None,      # "left" | "right" | "single"
        "requirements_text": str,  # lower-cased, "\n"-joined section body
    }

"found" is False, never an exception, when no requirements-style
heading is present -- that is a normal outcome for a JD that genuinely
has no such section. A malformed/corrupt PDF still raises, same as
elsewhere in this codebase (pdfplumber does the raising).

This module has no dependency on app.core.jd_skills_locator or on
FastAPI/Celery -- it only knows about PDF bytes on disk. The bytes ->
temp-file bridge and the JSON-shape adapter (section_text vs.
requirements_text, dropping confidence/page/column) live in
jd_skills_locator._locate_in_pdf_bytes, which is what the rest of the
app actually calls.
"""

import math
import re
from collections import Counter
from pathlib import Path
from statistics import median

import pdfplumber


# ============================================================
# HEADING VOCABULARY, BOUNDARIES AND TEXT HELPERS
# ============================================================



# Headings that START a requirements section. Matched after
# normalize_heading_text(), so case, trailing colons, curly
# apostrophes and "&" spacing do not matter.
STRONG_JD_HEADINGS = {
    "requirements",
    "key requirements",
    "job requirements",
    "role requirements",
    "minimum requirements",
    "mandatory requirements",
    "essential requirements",
    "technical requirements",
    "qualifications",
    "key qualifications",
    "minimum qualifications",
    "required qualifications",
    "basic qualifications",
    "essential qualifications",
    "requirements & qualifications",
    "requirements and qualifications",
    "qualifications & skills",
    "qualifications and skills",
    "skills & qualifications",
    "skills and qualifications",
    "skills required",
    "required skills",
    "essential skills",
    "essential criteria",
    "skills & experience",
    "skills and experience",
    "experience & skills",
    "experience and skills",
    "what you'll need",
    "what you will need",
    "what you need",
    "what you bring",
    "what you'll bring",
    "what you will bring",
    "what we're looking for",
    "what we are looking for",
    "who you are",
    "about you",
    "your profile",
    "your background",
    "must haves",
    "must-haves",
    "must have",
    "must-have qualifications",
    "must have qualifications",
    "must-have skills",
    "must have skills",
    "basic requirements",
    "required experience",
    "experience required",
    "required skills & experience",
    "required skills and experience",
    "qualifications & experience",
    "qualifications and experience",
    "experience & qualifications",
    "experience and qualifications",
    "your qualifications",
    "your experience",
    "your skills",
    "you have",
    "you should have",
    "you bring",
    "what you have",
    "required",
    "essential",
    "minimum",
    # Compulsory-skills family. These get PRIORITY over generic
    # experience headings (see PRIORITY_JD_HEADINGS below).
    "compulsory skills",
    "compulsory skill set",
    "compulsory requirements",
    "compulsory qualifications",
    "compulsory",
    # Candidate-facing requirement headings.
    "candidate profile",
    "candidate profile & experience",
    "candidate profile and experience",
    "candidate requirements",
    "candidate qualifications",
    "ideal candidate",
    "the ideal candidate",
    "required skills & qualifications",
    "required skills and qualifications",
    "required qualifications & skills",
    "required qualifications and skills",
}


# Headings that name the explicit must-have skills block. When one of
# these exists in a JD it wins over any other strong heading, even one
# with a higher visual confidence (e.g. a bulleted "Required
# Experience" list). Other strong headings then act as section
# boundaries while this one is being read.
PRIORITY_JD_HEADINGS = {
    "compulsory skills",
    "compulsory skill set",
    "compulsory requirements",
    "compulsory qualifications",
    "compulsory",
}


# Headings that END a requirements section.
#
# NOTE: "preferred qualifications" / "nice to have" are deliberately
# boundaries, not locatable headings, so a Requirements section does
# not bleed into them.
MAJOR_SECTION_HEADINGS = {
    "about us",
    "about the company",
    "about the role",
    "about the job",
    "about the team",
    "about the position",
    "the role",
    "your role",
    "the opportunity",
    "the team",
    "our team",
    "overview",
    "job overview",
    "role overview",
    "position overview",
    "job summary",
    "position summary",
    "job description",
    "summary",
    "who we are",
    "what we do",
    "our mission",
    "our values",
    "our story",
    "our culture",
    "company culture",
    "company & culture",
    "culture",
    "why join us",
    "why us",
    "why work with us",
    "responsibilities",
    "key responsibilities",
    "core responsibilities",
    "primary responsibilities",
    "job responsibilities",
    "role responsibilities",
    "responsibilities & duties",
    "responsibilities and duties",
    "your responsibilities",
    "duties",
    "key duties",
    "day to day",
    "your day to day",
    "what you'll do",
    "what you will do",
    "what you'll be doing",
    "you will",
    "your impact",
    "benefits",
    "perks",
    "perks & benefits",
    "benefits & perks",
    "compensation",
    "compensation & benefits",
    "salary",
    "what we offer",
    "what we offer you",
    "what's in it for you",
    "what you'll get",
    "location",
    "job type",
    "logistics",
    "working hours",
    "how to apply",
    "application information",
    "to apply",
    "apply now",
    "application process",
    "additional information",
    "equal opportunity",
    "equal opportunity employer",
    "equal employment opportunity",
    "diversity & inclusion",
    "diversity and inclusion",
    "eeo statement",
    "preferred qualifications",
    "preferred skills",
    "preferred requirements",
    "nice to have",
    "nice-to-have",
    "nice to haves",
    "bonus points",
    "bonus skills",
    "bonus",
    "bonus qualifications",
    "preferred",
    "preferred experience",
    "desired qualifications",
    "desired skills",
    "desirable",
    "desirable skills",
    "desirable qualifications",
    "additional qualifications",
    "additional skills",
    "good to have",
    "good-to-have",
    "a plus",
    "compensation & perks",
    "compensation and perks",
    "compensation and benefits",
    "perks and benefits",
    "benefits and perks",
    "our benefits",
    "how we work",
    "how we hire",
    "hiring process",
    "interview process",
    "our hiring process",
    "team",
    "tech stack",
    "our tech stack",
    "our stack",
    "technology stack",
    "what we value",
    "what we believe",
    "our principles",
    "work environment",
    "working here",
    "work location",
    "work arrangement",
}


# Only multi-word / unambiguous phrases are searched for INSIDE a longer
# line (PDF spacing corruption such as "some requirement Company &Culture").
# Generic words ("team", "location", ...) would cause false positives.
_EMBEDDED_BOUNDARY_PHRASES = sorted(
    {
        phrase
        for phrase in MAJOR_SECTION_HEADINGS
        if len(phrase.split()) >= 2
        and phrase.split()[0] not in {"the", "you", "your", "a", "an"}
    }
    | {"benefits", "responsibilities", "perks"},
    key=len,
    reverse=True,
)

_EMBEDDED_BOUNDARY_RES = [
    (
        phrase,
        re.compile(
            r"(?<![A-Za-z])"
            + r"\s*".join(re.escape(word) for word in phrase.split())
            + r"\s*:?\s*$",
            re.IGNORECASE,
        ),
    )
    for phrase in _EMBEDDED_BOUNDARY_PHRASES
]

_SMALL_WORDS = {"the", "a", "an", "and", "of", "to", "for", "in", "on", "with", "or"}

_DANGLING_TAIL_RE = re.compile(
    r"(?:\b(?:of|the|and|or|our|with|for|to|in|on|a|an|&|/)|[&/,(])\s*$",
    re.IGNORECASE,
)


# Bullet markers: unicode bullet glyphs, Symbol/Wingdings private-use
# glyphs, pdfplumber's "(cid:NNN)" placeholder for unmapped glyphs,
# dashes/asterisks, and "1." / "1)" numbering.
BULLET_RE = re.compile(
    r"^\s*(?:"
    r"(?:[\u2022\u2023\u2043\u25a0\u25aa\u25ab\u25cf\u25cb\u25e6\u00b7\uf000-\uf8ff]"
    r"|\(cid:\d+\))\s*"
    r"|(?:[-*\u2013\u2014]|\d{1,2}[.)])\s+"
    r")"
)

_PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s+)?\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?$",
    re.IGNORECASE,
)

_CONTINUATION_TAIL_RE = re.compile(
    r"(?:[,&/(-]"
    r"|\b(?:and|or|of|with|in|to|for|a|an|the|as|by|on|at|from|including)"
    r")\s*$",
    re.IGNORECASE,
)


def looks_bulleted(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def normalize_heading_text(text) -> str:
    """
    Canonical form used for every heading comparison.

    "Company &Culture" -> "company & culture"
    "What You\u2019ll Need:" -> "what you'll need"
    """

    value = (
        (text or "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u00a0", " ")
    )

    value = re.sub(r"\s*&\s*", " & ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.rstrip(":").strip()

    return value.lower()


def _compact(text) -> str:
    """Letters and digits only, lower-case: survives letter-spaced
    ("R E Q U I R E M E N T S") and space-less ("RequiredQualifications")
    PDF text."""

    return re.sub(r"[^a-z0-9]", "", normalize_heading_text(text))


_STRONG_COMPACT = {_compact(phrase) for phrase in STRONG_JD_HEADINGS}
_MAJOR_COMPACT = {_compact(phrase) for phrase in MAJOR_SECTION_HEADINGS}


def _looks_like_sentence_fragment(text: str) -> bool:
    """
    A wrapped tail of a sentence, not a heading: it ends in sentence
    punctuation ("requirements.") or starts lower-case ("requirements").
    A trailing colon is fine ("Requirements:").
    """

    stripped = (text or "").strip()

    if not stripped:
        return False

    if re.search(r"[.;!?,]$", stripped):
        return True

    first_letter = next((ch for ch in stripped if ch.isalpha()), "")

    return bool(first_letter) and first_letter.islower()


def is_strong_jd_heading(text: str) -> bool:
    if _looks_like_sentence_fragment(text):
        return False

    if normalize_heading_text(text) in STRONG_JD_HEADINGS:
        return True

    compact = _compact(text)

    return len(compact) >= 6 and compact in _STRONG_COMPACT


_PRIORITY_COMPACT = {_compact(phrase) for phrase in PRIORITY_JD_HEADINGS}


def heading_priority(text: str) -> int:
    """1 for a compulsory-skills style heading, else 0."""

    if normalize_heading_text(text) in PRIORITY_JD_HEADINGS:
        return 1

    compact = _compact(text)

    return 1 if len(compact) >= 6 and compact in _PRIORITY_COMPACT else 0


def _title_cased(text: str) -> bool:
    """Every content word starts upper-case (or the text is ALL CAPS)."""

    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z']*", text)
        if word.lower() not in _SMALL_WORDS
    ]

    return bool(words) and all(word[0].isupper() for word in words)


# "Must have: Python, SQL" -- a strong heading and its content on one line.
_INLINE_LABEL_RES = [
    (
        phrase,
        re.compile(
            r"^\s*"
            + r"\s*".join(re.escape(word) for word in phrase.split())
            + r"\s*:\s*(?P<rest>\S.*)$",
            re.IGNORECASE | re.DOTALL,
        ),
    )
    for phrase in sorted(STRONG_JD_HEADINGS, key=len, reverse=True)
]


def split_inline_requirements_label(text: str) -> tuple[str, str] | None:
    """
    "Required skills: Python, SQL" -> ("Required skills", "Python, SQL")
    Returns None if the line is not a labelled requirements line.
    """

    value = (text or "").replace("\u2019", "'").replace("\u2018", "'")

    for _, pattern in _INLINE_LABEL_RES:
        match = pattern.match(value)

        if match:
            heading = value[: match.start("rest")].rstrip().rstrip(":").strip()
            return heading, match.group("rest").strip()

    return None


_FUZZY_KEYWORD_RE = re.compile(
    r"\b(requirements?|qualifications?|required|minimum|essential|mandatory)\b",
    re.IGNORECASE,
)


def is_fuzzy_requirements_heading(text: str) -> bool:
    """
    Lower-confidence fallback for headings not in STRONG_JD_HEADINGS
    ("Basic Requirements & Experience"): a short, Title-Case line with no
    sentence punctuation or digits that contains a requirements keyword.
    """

    stripped = (text or "").strip().rstrip(":").strip()
    words = stripped.split()

    if not 1 <= len(words) <= 7:
        return False

    if looks_bulleted(stripped):
        return False

    if re.search(r"[.;!?,\d]", stripped):
        return False

    if not _FUZZY_KEYWORD_RE.search(stripped):
        return False

    if not stripped[0].isupper() or not _title_cased(stripped):
        return False

    return not is_section_boundary(stripped)


def _looks_like_caps_heading(text: str) -> bool:
    """
    Unknown ALL-CAPS heading such as "WHAT WE VALUE". Deliberately
    conservative: 2-5 words, letters only, never a bullet line, so
    "AWS" or "5+ YEARS" requirement lines are not mistaken for one.
    """

    stripped = text.strip().rstrip(":").strip()

    if not stripped or looks_bulleted(stripped):
        return False

    words = stripped.split()

    return (
        stripped.isupper()
        and 2 <= len(words) <= 5
        and len(stripped) < 40
        and not re.search(r"[\d,.;]", stripped)
    )


_LEADING_BOUNDARY_RES = [
    (
        phrase,
        re.compile(
            r"^\s*"
            + r"\s*".join(re.escape(word) for word in phrase.split())
            + r"(?![A-Za-z])",
            re.IGNORECASE,
        ),
    )
    for phrase in sorted(MAJOR_SECTION_HEADINGS, key=len, reverse=True)
]

# Single-word boundaries safe to extend ("Benefits at Acme").
_EXTENDABLE_SINGLE_WORDS = {
    "benefits",
    "perks",
    "compensation",
    "responsibilities",
    "duties",
    "salary",
}


def _leading_boundary(text: str) -> str | None:
    """
    A boundary heading at the START of the line, followed by more text:

      "Location: Pune"                          (label form)
      "Preferred Qualifications & Broad Expertise"  (extended heading)
      "Nice-to-Have / Preferred Qualifications"

    Bulleted lines are never headings.
    """

    stripped = (text or "").strip()

    if not stripped or looks_bulleted(stripped):
        return None

    for phrase, pattern in _LEADING_BOUNDARY_RES:
        match = pattern.match(stripped)

        if match is None:
            continue

        rest = stripped[match.end():].strip()

        if not rest:
            return phrase

        # Label form: "Benefits: health insurance".
        if rest.startswith(":"):
            return phrase

        # Extended heading form: short, Title Case, no sentence
        # punctuation, and the phrase itself must be multi-word.
        multi_word = len(re.findall(r"[a-z]+", phrase)) >= 2
        trusted = phrase in _EXTENDABLE_SINGLE_WORDS

        if (
            (multi_word or trusted)
            and len(stripped.split()) <= len(phrase.split()) + 4
            and not re.search(r"[.;!?,]$", stripped)
            and _title_cased(stripped)
        ):
            return phrase

    return None


def is_section_boundary(text: str) -> bool:
    """
    True if this whole line is a heading that ends the requirements
    section (Responsibilities, Benefits, Preferred Qualifications, ...).
    """

    normalized = normalize_heading_text(text)

    if not normalized:
        return False

    if normalized in MAJOR_SECTION_HEADINGS:
        return True

    if is_strong_jd_heading(text):
        return False

    compact = _compact(text)

    # A wrapped sentence tail such as "preferred." (the last word of
    # "...advanced degree preferred.") is not a heading.
    if (
        len(compact) >= 6
        and compact in _MAJOR_COMPACT
        and not re.search(r"[.;!?,]$", (text or "").strip())
    ):
        return True

    if _leading_boundary(text) is not None:
        return True

    return _looks_like_caps_heading(text)


# Sub-headings INSIDE a requirements section ("Technical Skills",
# "Management & Leadership Skills") are set in the same bold style as
# the section heading but do not end it.
_SUBHEADING_TAIL_RE = re.compile(
    r"\b(?:skills?|experience|qualifications?|requirements?|knowledge"
    r"|expertise|competenc(?:y|ies)|education)\s*:?$",
    re.IGNORECASE,
)


def is_style_boundary(segment: dict, heading_style: dict | None) -> bool:
    """
    Catch section headings that are not in the vocabulary: a short
    line set in exactly the same (distinctive) font and size as the
    requirements heading is itself a heading.

    Only used when the requirements heading was visibly styled (bold or
    larger than body text); otherwise every short line would match.
    """

    if not heading_style:
        return False

    if segment.get("fontname") != heading_style.get("fontname"):
        return False

    if abs(segment.get("size", 0) - (heading_style.get("size") or 0)) > 0.5:
        return False

    text = segment["text"].strip()

    if not 1 <= len(text.split()) <= 8:
        return False

    if looks_bulleted(text) or text[-1] in ".;,":
        return False

    if _SUBHEADING_TAIL_RE.search(text):
        return False

    return not is_strong_jd_heading(text)


def split_embedded_section_boundary(text: str) -> tuple[str, str | None]:
    """
    Detect a section heading glued onto the END of a line, e.g.
    "5+ years Python Company &Culture".

    Returns (text_before_boundary, boundary_phrase). boundary_phrase is
    None if no boundary was found, in which case the original text is
    returned unchanged.

    When the whole line is the boundary, text_before_boundary is "".
    """

    stripped = (text or "").strip()

    if not stripped:
        return "", None

    if normalize_heading_text(stripped) in MAJOR_SECTION_HEADINGS:
        return "", normalize_heading_text(stripped)

    leading = _leading_boundary(stripped)

    if leading is not None:
        return "", leading

    for phrase, pattern in _EMBEDDED_BOUNDARY_RES:
        match = pattern.search(stripped)

        if match is None:
            continue

        before = stripped[: match.start()].rstrip()
        matched = stripped[match.start() : match.end()]

        if not before:
            return "", phrase

        # Must be written like a heading (Title Case / ALL CAPS), not
        # like the tail of an ordinary sentence.
        cased_words = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z']*", matched)
            if word.lower() not in _SMALL_WORDS
        ]

        if not cased_words or not all(word[0].isupper() for word in cased_words):
            continue

        # "... experience of Benefits" style sentence endings.
        if _DANGLING_TAIL_RE.search(before):
            continue

        return before, phrase

    return stripped, None


# ------------------------------------------------------------
# Text reconstruction
# ------------------------------------------------------------

def _is_continuation(previous: str, line: str, has_bullets: bool) -> bool:
    """Is `line` the wrapped remainder of `previous` rather than a new item?"""

    first = line[0]

    if first.islower() or first in ")],;":
        return True

    if _CONTINUATION_TAIL_RE.search(previous):
        return True

        # A short Title Case sub-heading ("Management Skills") is a new
    # item, not the wrapped tail of the bullet above it.
    if (
        2 <= len(line.split()) <= 6
        and _SUBHEADING_TAIL_RE.search(line)
        and _title_cased(line)
    ):
        return False

    # In a bulleted section, a non-bulleted line following an
    # unfinished bullet is a wrapped line.
    if has_bullets and not re.search(r"[.!?;:]$", previous):
        return True

    return False


def join_wrapped_requirement_lines(lines: list[str]) -> list[str]:
    """
    Re-join visually wrapped lines into one string per requirement.

    A line with a bullet marker always starts a new item. Other lines
    are appended to the previous item when they look like a wrap.
    """

    cleaned = [
        line.strip()
        for line in lines
        if line and line.strip()
    ]

    has_bullets = any(looks_bulleted(line) for line in cleaned)

    items: list[str] = []

    for line in cleaned:
        if not items or looks_bulleted(line):
            items.append(line)
            continue

        previous = items[-1]

        if not _is_continuation(previous, line, has_bullets):
            items.append(line)
            continue

        if (
            previous.endswith("-")
            and len(previous) > 1
            and previous[-2].isalpha()
            and line[0].islower()
        ):
            items[-1] = previous + line
        else:
            items[-1] = previous + " " + line

    return items


def clean_requirements_text(text: str) -> str:
    """
    Normalise whitespace, unify bullet glyphs to "- ", and drop empty
    bullets and stray page-number lines.
    """

    output = []

    for raw in (text or "").splitlines():
        line = raw.replace("\u00a0", " ")
        line = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", line)
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue

        match = BULLET_RE.match(line)

        if match:
            rest = line[match.end():].strip()

            if not rest:
                continue

            if not re.match(r"\d", line):
                line = "- " + rest

        if _PAGE_NUMBER_RE.match(line):
            continue

        output.append(line)

    return "\n".join(output).strip()


# ============================================================
# PDF LAYOUT HELPERS
#   words -> column layout -> visual segments -> heading detectors
# ============================================================




def extract_page_words(page) -> list[dict]:
    """Words with coordinates and font info, blanks removed."""

    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        use_text_flow=False,
        extra_attrs=["fontname", "size"],
    )

    return [
        word
        for word in words
        if word["text"].strip()
    ]


def _group_words_into_rows(words: list[dict], tolerance: float = 3.0) -> list[dict]:
    rows: list[dict] = []

    for word in sorted(
        words,
        key=lambda item: (item["top"], item["x0"]),
    ):
        row = None

        for candidate in reversed(rows[-3:]):
            if abs(word["top"] - candidate["top"]) <= tolerance:
                row = candidate
                break

        if row is None:
            row = {
                "top": word["top"],
                "words": [],
            }
            rows.append(row)

        row["words"].append(word)

    for row in rows:
        row["words"].sort(key=lambda item: item["x0"])

    return rows


def detect_page_column_layout(
    words: list[dict],
    page_width: float,
    min_gap: float = 10.0,
) -> dict | None:
    """
    Find a vertical gutter separating a left and a right column
    (two-column body, or a sidebar next to a main column).

    A gutter is a run of x positions at least `min_gap` wide that
    (almost) no word straddles, with substantial text on both sides
    that overlaps vertically. Occasional full-width lines (titles,
    footers) are tolerated.

    Returns {"boundary", "gap", "left_words", "right_words"} or None
    for a single-column page.
    """

    if len(words) < 20 or page_width <= 0:
        return None

    size = int(math.ceil(page_width)) + 2
    diff = [0] * (size + 1)

    for word in words:
        start = max(0, int(math.floor(word["x0"])))
        end = min(size - 1, int(math.ceil(word["x1"])))

        if end > start:
            diff[start] += 1
            diff[end] -= 1

    coverage = []
    running = 0

    for index in range(size):
        running += diff[index]
        coverage.append(running)

    line_count = len(_group_words_into_rows(words))
    max_crossing = max(2, int(0.10 * line_count))

    low = int(page_width * 0.15)
    high = int(page_width * 0.85)

    runs = []
    run_start = None

    for x in range(low, high + 1):
        if coverage[x] <= max_crossing:
            if run_start is None:
                run_start = x
        else:
            if run_start is not None:
                runs.append((run_start, x - 1))
                run_start = None

    if run_start is not None:
        runs.append((run_start, high))

    best = None

    for start, end in runs:
        gap = end - start + 1

        if gap < min_gap:
            continue

        boundary = (start + end) / 2

        left = [w for w in words if w["x1"] <= boundary + 1]
        right = [w for w in words if w["x0"] >= boundary - 1]

        if len(left) < 10 or len(right) < 10:
            continue

        if len(left) < 0.10 * len(words) or len(right) < 0.10 * len(words):
            continue

        if len(_group_words_into_rows(left)) < 4:
            continue

        if len(_group_words_into_rows(right)) < 4:
            continue

        left_top = min(w["top"] for w in left)
        left_bottom = max(w["bottom"] for w in left)
        right_top = min(w["top"] for w in right)
        right_bottom = max(w["bottom"] for w in right)

        overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
        shorter = min(left_bottom - left_top, right_bottom - right_top)

        if shorter <= 0 or overlap < 0.30 * shorter:
            continue

        candidate = {
            "boundary": boundary,
            "gap": gap,
            "left_words": len(left),
            "right_words": len(right),
        }

        if best is None or candidate["gap"] > best["gap"]:
            best = candidate

    return best


def _word_column(word: dict, boundary: float | None) -> str:
    if boundary is None:
        return "single"

    if word["x1"] <= boundary + 1:
        return "left"

    if word["x0"] >= boundary - 1:
        return "right"

    return "single"


def _make_segment(words: list[dict], column: str) -> dict:
    dominant = max(words, key=lambda item: len(item["text"]))
    fontname = dominant.get("fontname") or ""

    return {
        "text": " ".join(word["text"] for word in words),
        "top": min(word["top"] for word in words),
        "bottom": max(word["bottom"] for word in words),
        "x0": min(word["x0"] for word in words),
        "x1": max(word["x1"] for word in words),
        "fontname": fontname,
        "size": round(float(dominant.get("size") or 0.0), 1),
        "bold": "bold" in fontname.lower(),
        "column": column,
    }


def build_visual_segments(
    words: list[dict],
    column_layout: dict | None = None,
) -> list[dict]:
    """
    Group words into line-level segments.

    Each segment is tagged column = "left" | "right" | "single":
    "left"/"right" sit fully on one side of the gutter, "single" is
    anything spanning it (or every segment on a one-column page).
    Segments are returned in top-to-bottom order.
    """

    if not words:
        return []

    boundary = (
        column_layout["boundary"]
        if column_layout
        else None
    )

    median_size = median(
        float(word.get("size") or 0.0)
        for word in words
    ) or 10.0

    # Two segments on one row belong together unless separated by
    # much more than a normal word space.
    gap_threshold = max(18.0, 2.5 * median_size)

    buckets: dict[str, list[dict]] = {
        "left": [],
        "right": [],
        "single": [],
    }

    for word in words:
        buckets[_word_column(word, boundary)].append(word)

    segments = []

    for column, bucket in buckets.items():
        for row in _group_words_into_rows(bucket):
            current: list[dict] = []

            for word in row["words"]:
                if (
                    current
                    and word["x0"] - current[-1]["x1"] > gap_threshold
                ):
                    segments.append(_make_segment(current, column))
                    current = []

                current.append(word)

            if current:
                segments.append(_make_segment(current, column))

    segments.sort(
        key=lambda item: (item["top"], item["x0"])
    )

    return segments


def infer_heading_column_from_following_content(
    segments: list[dict],
    heading_bottom: float,
    column_layout: dict | None,
) -> str | None:
    """
    A heading that spans the gutter does not say which column holds
    the requirements. Look at the content below it: the column whose
    next few lines are real content (bullets count double) wins, and a
    column that opens with a section boundary scores zero.
    """

    if not column_layout:
        return None

    scores = {"left": 0, "right": 0}

    for column in ("left", "right"):
        seen = 0

        for segment in segments:
            if segment.get("column") != column:
                continue

            if segment["top"] < heading_bottom - 1:
                continue

            text = segment["text"].strip()

            if not text:
                continue

            if is_section_boundary(text):
                break

            scores[column] += 2 if looks_bulleted(text) else 1
            seen += 1

            if seen >= 6:
                break

    if scores["left"] == 0 and scores["right"] == 0:
        return None

    # Tie -> the left (main body) column.
    return "right" if scores["right"] > scores["left"] else "left"


# ------------------------------------------------------------
# Heading detectors. Each returns the best strong-heading match on
# a page (or None) as a dict with at least: heading, confidence,
# column, bottom. Confidence bands keep the modes ordered:
#   visual 0.80-1.00  >  word 0.75  >  plain 0.60
# ------------------------------------------------------------


def _heading_confidence(
    segment: dict,
    index: int,
    segments: list[dict],
    median_size: float,
) -> float:
    text = segment["text"].strip()
    confidence = 0.80

    if text.endswith(":"):
        confidence += 0.03

    if text.isupper() or text.istitle():
        confidence += 0.03

    if segment.get("bold") or segment["size"] > median_size * 1.05:
        confidence += 0.05

    following = [
        item
        for item in segments[index + 1:]
        if item.get("column") == segment.get("column")
    ][:3]

    if any(looks_bulleted(item["text"]) for item in following):
        confidence += 0.05
    elif following:
        confidence += 0.02

    return round(min(confidence, 1.0), 2)


def locate_requirements_heading_on_page(segments: list[dict]) -> dict | None:
    """
    Best requirements heading among a page's segments.

    Tiers, strongest first:
      1. exact heading from STRONG_JD_HEADINGS       (0.80 - 1.00)
      2. labelled line "Must have: Python, SQL"      (0.80 - 1.00)
      3. fuzzy keyword heading, only if 1-2 found none  (0.60 - 0.72)

    The returned dict carries the heading's font/size and whether it is
    visually distinct from body text, so the extractor can spot
    unfamiliar section headings by style.
    """

    sizes = [
        item["size"]
        for item in segments
        if item["size"] > 0
    ]

    median_size = median(sizes) if sizes else 10.0

    def build(index, segment, heading, confidence, inline_text=None):
        return {
            "heading": heading,
            "confidence": confidence,
            "column": segment.get("column", "single"),
            "segment_index": index,
            "top": segment["top"],
            "bottom": segment["bottom"],
            "fontname": segment.get("fontname"),
            "size": segment["size"],
            "bold": segment.get("bold", False),
            "distinct": bool(
                segment.get("bold")
                or segment["size"] > median_size * 1.05
            ),
            "inline_text": inline_text,
            "priority": heading_priority(heading),
        }

    best = None

    for index, segment in enumerate(segments):
        text = segment["text"].strip()

        if not text:
            continue

        if is_strong_jd_heading(text):
            candidate = build(
                index,
                segment,
                text.rstrip(":").strip(),
                _heading_confidence(segment, index, segments, median_size),
            )
        else:
            labelled = split_inline_requirements_label(text)

            if labelled is None:
                continue

            heading, rest = labelled

            candidate = build(
                index,
                segment,
                heading,
                _heading_confidence(segment, index, segments, median_size),
                inline_text=rest,
            )

        if best is None or (
            candidate["priority"],
            candidate["confidence"],
        ) > (
            best["priority"],
            best["confidence"],
        ):
            best = candidate

    if best is not None:
        return best

    # Fuzzy fallback.
    for index, segment in enumerate(segments):
        text = segment["text"].strip()

        if not text or not is_fuzzy_requirements_heading(text):
            continue

        confidence = 0.60

        if segment.get("bold") or segment["size"] > median_size * 1.05:
            confidence += 0.06

        if text.endswith(":"):
            confidence += 0.03

        if text.isupper():
            confidence += 0.03

        candidate = build(
            index,
            segment,
            text.rstrip(":").strip(),
            round(min(confidence, 0.72), 2),
        )

        if best is None or (
            candidate["priority"],
            candidate["confidence"],
        ) > (
            best["priority"],
            best["confidence"],
        ):
            best = candidate

    return best


def locate_heading_by_words(
    words: list[dict],
    page_width: float,
    column_layout: dict | None,
) -> dict | None:
    """
    Word-level fallback for headings the segment builder merged into a
    longer line, e.g. a narrow gutter: "Requirements   Benefits".

    Accepts a run of up to 5 tight-spaced, capitalised words that spells
    a strong heading AND is set apart from its neighbours on the line
    by a real gap. That is what separates a heading from the word
    "requirements" inside a sentence.
    """

    boundary = (
        column_layout["boundary"]
        if column_layout
        else None
    )

    best = None

    for row in _group_words_into_rows(words):
        row_words = row["words"]

        for start in range(len(row_words)):
            for length in range(1, 6):
                end = start + length

                if end > len(row_words):
                    break

                window = row_words[start:end]

                if any(
                    window[k + 1]["x0"] - window[k]["x1"] > 8
                    for k in range(length - 1)
                ):
                    break

                joined = " ".join(word["text"] for word in window)

                if not is_strong_jd_heading(joined):
                    continue

                if not joined[0].isupper():
                    continue

                if start > 0:
                    if window[0]["x0"] - row_words[start - 1]["x1"] < 8:
                        continue

                if end < len(row_words):
                    if row_words[end]["x0"] - window[-1]["x1"] < 8:
                        continue

                x0 = window[0]["x0"]
                x1 = window[-1]["x1"]

                if boundary is None:
                    column = "single"
                elif x1 <= boundary + 1:
                    column = "left"
                elif x0 >= boundary - 1:
                    column = "right"
                else:
                    column = "single"

                candidate = {
                    "heading": joined.rstrip(":").strip(),
                    "confidence": 0.75,
                    "priority": heading_priority(joined),
                    "column": column,
                    "top": min(word["top"] for word in window),
                    "bottom": max(word["bottom"] for word in window),
                }

                if best is None or (
                    -candidate["priority"],
                    candidate["top"],
                ) < (
                    -best["priority"],
                    best["top"],
                ):
                    best = candidate

    return best


def locate_heading_plain_text(page) -> dict | None:
    """Last resort: scan page.extract_text() lines for a strong heading."""

    try:
        text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    except Exception:
        return None

    for line in text.split("\n"):
        if not is_strong_jd_heading(line):
            continue

        heading = line.strip().rstrip(":").strip()

        top = None
        bottom = None

        try:
            hits = page.search(
                re.escape(heading),
                regex=True,
                case=False,
            )

            if hits:
                top = hits[0]["top"]
                bottom = hits[0]["bottom"]
        except Exception:
            pass

        return {
            "heading": heading,
            "confidence": 0.60,
            "column": "single",
            "top": top,
            "bottom": bottom,
        }

    return None


# ------------------------------------------------------------
# Debugging
# ------------------------------------------------------------

def debug_jd_headings(pdf_path, max_lines_per_page: int = 40) -> None:
    """
    Explain why a PDF produced no requirements heading: prints the
    text layer status, the detected column layout, and every
    heading-looking line (bold, larger than body, ALL CAPS, ends with
    a colon, or short Title Case) with its style.
    """

    pdf_path = Path(pdf_path)

    print("=" * 90)
    print(pdf_path.name)

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = extract_page_words(page)

            if not words:
                print(
                    f"--- page {page_number}: NO TEXT LAYER "
                    "(scanned/image PDF -- needs OCR)"
                )
                continue

            layout = detect_page_column_layout(
                words,
                float(page.width),
            )

            segments = build_visual_segments(words, layout)

            sizes = [
                item["size"]
                for item in segments
                if item["size"] > 0
            ]

            median_size = median(sizes) if sizes else 10.0

            layout_text = (
                "single column"
                if layout is None
                else f"gutter at x={layout['boundary']:.0f}"
            )

            print(
                f"--- page {page_number}: {len(words)} words, "
                f"{len(segments)} segments, {layout_text}, "
                f"body size ~{median_size:.1f}"
            )

            shown = 0

            for segment in segments:
                text = segment["text"].strip()

                if not text or len(text) > 80:
                    continue

                headingish = (
                    segment["bold"]
                    or segment["size"] > median_size * 1.05
                    or text.isupper()
                    or text.endswith(":")
                    or (len(text.split()) <= 6 and text.istitle())
                )

                if not headingish:
                    continue

                if is_strong_jd_heading(text):
                    tag = "STRONG"
                elif is_section_boundary(text):
                    tag = "boundary"
                elif is_fuzzy_requirements_heading(text):
                    tag = "fuzzy"
                else:
                    tag = ""

                print(
                    f"  [{segment['column']:<6}] "
                    f"size={segment['size']:<5} "
                    f"bold={str(segment['bold']):<5} "
                    f"{tag:<8} {text!r}"
                )

                shown += 1

                if shown >= max_lines_per_page:
                    print("  ... (truncated)")
                    break


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_requirements_section_from_pdf(
    pdf_path: str | Path,
) -> dict:

    pdf_path = Path(
        pdf_path
    )

    if not pdf_path.exists():

        return {
            "found": False,
            "file": pdf_path.name,
            "heading": None,
            "confidence": 0.0,
            "page": None,
            "column": None,
            "requirements_text": "",
        }

    pages_data = []

    # --------------------------------------------------------
    # Read PDF.
    # --------------------------------------------------------

    with pdfplumber.open(
        pdf_path
    ) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):

            words = extract_page_words(
                page
            )

            page_width = float(
                page.width
            )

            column_layout = (
                detect_page_column_layout(
                    words,
                    page_width,
                )
            )

            segments = build_visual_segments(
                words,
                column_layout,
            )

            visual_heading = (
                locate_requirements_heading_on_page(
                    segments
                )
            )

            word_heading = (
                locate_heading_by_words(
                    words,
                    page_width,
                    column_layout,
                )
            )

            plain_heading = None

            if (
                visual_heading is None
                and word_heading is None
            ):

                plain_heading = (
                    locate_heading_plain_text(
                        page
                    )
                )

            pages_data.append(
                {
                    "page_number": page_number,
                    "page": page,
                    "words": words,
                    "page_width": page_width,
                    "column_layout": column_layout,
                    "segments": segments,
                    "visual_heading": visual_heading,
                    "word_heading": word_heading,
                    "plain_heading": plain_heading,
                }
            )

    # --------------------------------------------------------
    # Collect candidate headings.
    # --------------------------------------------------------

    candidates = []

    for page_data in pages_data:

        visual = page_data[
            "visual_heading"
        ]

        if visual is not None:

            item = dict(
                visual
            )

            item[
                "page_number"
            ] = page_data[
                "page_number"
            ]

            item[
                "mode"
            ] = "visual"

            candidates.append(
                item
            )

        word = page_data[
            "word_heading"
        ]

        if word is not None:

            item = dict(
                word
            )

            item[
                "page_number"
            ] = page_data[
                "page_number"
            ]

            item[
                "mode"
            ] = "word"

            candidates.append(
                item
            )

        plain = page_data[
            "plain_heading"
        ]

        if plain is not None:

            item = dict(
                plain
            )

            item[
                "page_number"
            ] = page_data[
                "page_number"
            ]

            item[
                "mode"
            ] = "plain"

            candidates.append(
                item
            )

    if not candidates:

        return {
            "found": False,
            "file": pdf_path.name,
            "heading": None,
            "confidence": 0.0,
            "page": None,
            "column": None,
            "requirements_text": "",
        }

    # Prefer highest confidence, then earliest page.
    mode_priority = {
        "visual": 2,
        "word": 1,
        "plain": 0,
    }

    candidates.sort(
        key=lambda item: (
            -item.get("priority", 0),
            -item["confidence"],
            item["page_number"],
            -mode_priority.get(
                item.get(
                    "mode",
                    "plain",
                ),
                0,
            ),
        )
    )

    heading_info = candidates[0]

    heading_page = next(
        (
            page_data
            for page_data in pages_data
            if page_data[
                "page_number"
            ]
            == heading_info[
                "page_number"
            ]
        ),
        None,
    )

    if heading_page is None:

        return {
            "found": False,
            "file": pdf_path.name,
            "heading": None,
            "confidence": 0.0,
            "page": None,
            "column": None,
            "requirements_text": "",
        }

    extraction_column = heading_info.get(
        "column",
        "single",
    )

    # --------------------------------------------------------
    # If the heading spans the gutter, infer the actual
    # requirements column from the content below it.
    # --------------------------------------------------------

    heading_bottom = heading_info.get(
        "bottom"
    )

    if (
        heading_bottom is None
        and heading_info.get(
            "mode"
        )
        == "visual"
    ):

        segment_index = heading_info.get(
            "segment_index"
        )

        if (
            segment_index is not None
            and 0
            <= segment_index
            < len(
                heading_page[
                    "segments"
                ]
            )
        ):

            heading_bottom = (
                heading_page[
                    "segments"
                ][
                    segment_index
                ][
                    "bottom"
                ]
            )

    if (
        extraction_column
        == "single"
        and heading_bottom is not None
    ):

        inferred = (
            infer_heading_column_from_following_content(
                heading_page[
                    "segments"
                ],
                heading_bottom,
                heading_page[
                    "column_layout"
                ],
            )
        )

        if inferred in {
            "left",
            "right",
        }:
            extraction_column = inferred

    # A visibly styled heading (bold / larger than body text) lets us
    # recognise unfamiliar section headings later by matching its style.
    heading_style = None

    if heading_info.get("distinct"):
        heading_style = {
            "fontname": heading_info.get("fontname"),
            "size": heading_info.get("size"),
        }

    # --------------------------------------------------------
    # Collect source lines.
    #
    # Column handling:
    #
    # - The heading's own column is read top-to-bottom until the
    #   first section boundary (Responsibilities, Benefits, ...).
    #   A boundary ends the section outright: it never spills into
    #   the neighbouring column.
    #
    # - Only when the heading's column runs all the way down the
    #   page WITHOUT hitting a boundary can the section flow into
    #   the next column (a two-column body). A sidebar that merely
    #   sits beside the section is left alone.
    #
    # - The neighbouring column is read from its own top and cut at
    #   its own first boundary; its boundaries never truncate the
    #   heading's column, and vice versa.
    # --------------------------------------------------------

    # When a compulsory-skills heading was chosen, any OTHER
    # requirements-style heading (Required Experience, Candidate
    # Requirements, "Must have: ...") starts a different block and
    # therefore ends this one.
    stop_at_other_headings = heading_info.get("priority", 0) > 0

    chosen_heading_normalized = normalize_heading_text(
        heading_info.get("heading") or ""
    )

    def is_other_requirements_heading(text: str) -> bool:

        if normalize_heading_text(text) == chosen_heading_normalized:
            return False

        if is_strong_jd_heading(text):
            return True

        if is_fuzzy_requirements_heading(text):
            return True

        return split_inline_requirements_label(text) is not None

    def columns_for_page(page_data: dict) -> list[str]:

        if page_data["column_layout"] is None:
            return ["single"]

        if extraction_column == "right":
            return ["right"]

        # "left", or a spanning heading with no clear column.
        return ["left", "right"]

    def collect_column(
        segments: list[dict],
        column: str,
        skip_above: float | None,
    ) -> tuple[list[str], float | None, bool]:
        """
        Read one column top-to-bottom.

        Returns (lines, bottom_of_last_line, hit_boundary).
        `skip_above` drops anything at or above that y position
        (the heading row itself, and whatever precedes it).
        """

        lines = []
        last_bottom = None

        for segment in segments:

            if segment.get("column", "single") != column:
                continue

            if (
                skip_above is not None
                and segment["bottom"] <= skip_above + 2
            ):
                continue

            text = segment["text"].strip()

            if not text:
                continue

            if (
                stop_at_other_headings
                and is_other_requirements_heading(text)
            ):
                return lines, last_bottom, True

            if (
                is_section_boundary(text)
                or is_style_boundary(segment, heading_style)
            ):
                return lines, last_bottom, True

            before, boundary = split_embedded_section_boundary(text)

            if boundary is not None:

                # Boundary glued onto the end of a line: keep only
                # the text in front of it.
                if before:
                    lines.append(before)
                    last_bottom = segment["bottom"]

                return lines, last_bottom, True

            lines.append(text)
            last_bottom = segment["bottom"]

        return lines, last_bottom, False

    def neighbour_column_continues(
        segments: list[dict],
        column: str,
    ) -> bool:
        """
        Does the neighbouring column pick up where the heading's
        column left off, or is it an unrelated block?

        Inspects the first few non-blank segments rather than one
        (a stray fragment can precede the real heading). A boundary
        seen before any continuation-looking line (a bullet or a
        lower-case wrapped line) means "unrelated".
        """

        checked = 0

        for segment in segments:

            if segment.get("column", "single") != column:
                continue

            text = segment["text"].strip()

            if not text:
                continue

            if looks_bulleted(text) or text[0].islower():
                return True

            if is_section_boundary(text):
                return False

            _, boundary = split_embedded_section_boundary(text)

            if boundary is not None:
                return False

            checked += 1

            if checked >= 3:
                break

        return checked > 0

    collected_lines = []

    heading_page_number = heading_info["page_number"]

    for page_data in pages_data:

        page_number = page_data["page_number"]

        if page_number < heading_page_number:
            continue

        segments = page_data["segments"]

        is_heading_page = page_number == heading_page_number

        page_columns = columns_for_page(page_data)

        primary = page_columns[0]

        # Nothing at or above the heading row belongs to the section,
        # but only in the heading's own column.
        skip_above = (
            heading_bottom
            if is_heading_page and heading_bottom is not None
            else None
        )

        lines, last_bottom, hit_boundary = collect_column(
            segments,
            primary,
            skip_above,
        )

        collected_lines.extend(lines)

        if hit_boundary:
            break

        # Flow into the neighbouring column only if the primary
        # column ran to the foot of the page.
        if len(page_columns) > 1:

            page_height = float(page_data["page"].height)

            runs_to_page_foot = (
                last_bottom is not None
                and last_bottom >= 0.75 * page_height
            )

            if (
                runs_to_page_foot
                and neighbour_column_continues(
                    segments,
                    page_columns[1],
                )
            ):

                lines, _, hit_boundary = collect_column(
                    segments,
                    page_columns[1],
                    None,
                )

                collected_lines.extend(lines)

                if hit_boundary:
                    break

    # "Must have: Python, SQL" -- the heading line also carried content.
    if heading_info.get("inline_text"):
        collected_lines.insert(
            0,
            heading_info["inline_text"],
        )

    # ========================================================
    # RECONSTRUCT
    # ========================================================

    reconstructed = (
        join_wrapped_requirement_lines(
            collected_lines
        )
    )

    requirements_text = (
        clean_requirements_text(
            "\n".join(
                reconstructed
            )
        )
    )

    # --------------------------------------------------------
    # Remove heading if it survived.
    # --------------------------------------------------------

    heading_normalized = (
        normalize_heading_text(
            heading_info.get(
                "heading",
                "",
            )
        )
    )

    final_lines = []

    for line in (
        requirements_text.splitlines()
    ):

        if (
            normalize_heading_text(
                line
            )
            == heading_normalized
        ):
            continue

        final_lines.append(
            line
        )

    requirements_text = "\n".join(
        final_lines
    ).strip().lower()

    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {
        "found": bool(
            requirements_text
        ),
        "file": pdf_path.name,
        "heading": heading_info.get(
            "heading"
        ),
        "confidence": round(
            float(
                heading_info.get(
                    "confidence",
                    0.0,
                )
            ),
            2,
        ),
        "page": heading_info.get(
            "page_number"
        ),
        "column": extraction_column,
        "requirements_text": requirements_text,
    }


# ============================================================
# BATCH HELPER
# ============================================================

def extract_candidate_requirements(
    pdf_paths,
) -> list[dict]:

    if isinstance(
        pdf_paths,
        (str, Path),
    ):
        pdf_paths = [
            pdf_paths
        ]

    results = []

    for pdf_path in pdf_paths:

        try:

            result = (
                extract_requirements_section_from_pdf(
                    pdf_path
                )
            )

        except Exception as exc:

            result = {
                "found": False,
                "file": Path(
                    pdf_path
                ).name,
                "heading": None,
                "confidence": 0.0,
                "page": None,
                "column": None,
                "requirements_text": "",
                "error": str(exc),
            }

        results.append(
            result
        )

    return results