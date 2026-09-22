"""
Locates the Skills section of a resume and returns its raw text.

This is a separate, more expensive extraction step than
app/core/text_extract.py's extract_text_from_bytes(): that function
answers "give me some usable text from this file" (pypdf, first 3 pages,
flattened reading order) for the *full-profile* LLM call, which reads
the whole document anyway and doesn't care about column order. This
module answers a narrower question -- "where exactly is the Skills
section, and what does it say" -- which does care about column order,
because a flattened two-column resume interleaves the Skills column
with whatever sits beside it (usually dates/titles from an Experience
column), corrupting the very thing we're trying to extract cleanly.

Two paths:

- PDF: extract_words() gives per-word (x, y) coordinates. We rebuild
  rows from those coordinates, detect a genuine two-column split, find
  the strongest "Skills"-like heading, and read forward from it while
  staying inside its column until the next major section heading. This
  is the notebook's `pdfplumber column-aware extraction`, adapted to
  read from bytes already in memory (this backend downloads the stored
  blob rather than keeping a file on disk) instead of a file path.

- DOCX / TXT: there is no column geometry to reconstruct (docx paragraph
  order and plain text are already linear), so we fall back to a flat
  text scan using the same heading-scoring heuristic, over text already
  produced by text_extract.extract_text_from_bytes().

Both paths return the same shape:
    {"found": bool, "heading": str | None, "section_text": str}
"""

import io
import re

# ---------------------------------------------------------------------
# Heading detection shared by both the column-aware and flat-text paths.
# ---------------------------------------------------------------------

STRONG_SKILLS_HEADINGS = {
    "skills",
    "technical skills",
    "core skills",
    "key skills",
    "professional skills",
    "skills & technologies",
    "technical proficiencies",
    "proficiencies",
    "competencies",
    "technologies",
    "technology stack",
    "tech stack",
    "skills / tools",
    "skills & tools",
    "technical",
}

HEADING_KEYWORDS = re.compile(
    r"\b("
    r"skills?|"
    r"technical|"
    r"competenc(?:e|ies)|"
    r"proficienc(?:y|ies)|"
    r"technolog(?:y|ies)|"
    r"stacks?|"
    r"tools?|"
    r"languages?|"
    r"expertise|"
    r"qualifications?"
    r")\b",
    re.IGNORECASE,
)

ROLE_TERMS = re.compile(
    r"\b("
    r"engineer|developer|architect|scientist|analyst|"
    r"manager|consultant|specialist|intern|designer|"
    r"director|officer|lead|senior|junior|principal"
    r")\b",
    re.IGNORECASE,
)

SCORE_THRESHOLD = 3.0

MAJOR_SECTION_HEADINGS = {
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "education",
    "projects",
    "certifications",
    "awards",
    "publications",
    "summary",
    "professional summary",
    "objective",
    "references",
}


def _normalize_heading_text(line: str) -> str:
    normalized = line.strip().rstrip(":")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def _score_heading_candidate(line: str, following_lines: list[str]) -> float:
    stripped = line.strip()

    if not stripped:
        return 0.0

    normalized = _normalize_heading_text(stripped)

    if normalized in MAJOR_SECTION_HEADINGS:
        return 0.0

    score = 0.0

    # Explicit skills headings get a strong advantage.
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

    # Prevent job titles such as "SENIOR FULL STACK SOFTWARE ENGINEER"
    # from winning.
    if ROLE_TERMS.search(stripped):
        score -= 6.0

    following_text = " ".join(following_lines[:3])

    if has_heading_keyword and following_text:
        comma_density = following_text.count(",") / max(len(following_text), 1)

        if comma_density > 0.01:
            score += 1.5

    if normalized in STRONG_SKILLS_HEADINGS:
        score = max(score, 9.0)

    return score


def _is_major_section_boundary(line: str) -> bool:
    stripped = line.strip().rstrip(":")
    normalized = re.sub(r"\s+", " ", stripped).lower()

    if not normalized:
        return False

    if normalized in MAJOR_SECTION_HEADINGS:
        return True

    return stripped.isupper() and len(stripped) < 40


# ---------------------------------------------------------------------
# Path A: column-aware PDF extraction (pdfplumber word coordinates).
# ---------------------------------------------------------------------


def _make_word_segment(words: list[dict]) -> dict:
    return {
        "text": " ".join(word["text"] for word in words),
        "top": min(word["top"] for word in words),
        "bottom": max(word["bottom"] for word in words),
        "x0": min(word["x0"] for word in words),
        "x1": max(word["x1"] for word in words),
        "fontname": words[0].get("fontname"),
        "size": round(words[0].get("size", 0), 1),
    }


def _extract_visual_segments(page) -> list[dict]:
    """
    Reconstruct visually meaningful text segments from a PDF page.

    Unlike page.extract_text(), this keeps x/y position information so
    multi-column layouts can be separated.
    """
    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        use_text_flow=False,
        extra_attrs=["fontname", "size"],
    )

    words = [word for word in words if word["text"].strip()]

    # Group words into horizontal rows.
    rows: list[dict] = []

    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        matched_row = None

        for row in reversed(rows[-3:]):
            if abs(word["top"] - row["top"]) <= 3:
                matched_row = row
                break

        if matched_row is None:
            matched_row = {"top": word["top"], "words": []}
            rows.append(matched_row)

        matched_row["words"].append(word)

    segments = []

    # A large horizontal gap usually means a second column.
    gap_threshold = max(18, page.width * 0.06)

    for row in rows:
        row_words = sorted(row["words"], key=lambda item: item["x0"])

        current_segment: list[dict] = []

        for word in row_words:
            if current_segment:
                horizontal_gap = word["x0"] - current_segment[-1]["x1"]

                if horizontal_gap > gap_threshold:
                    segments.append(_make_word_segment(current_segment))
                    current_segment = []

            current_segment.append(word)

        if current_segment:
            segments.append(_make_word_segment(current_segment))

    return segments


def _has_vertical_continuity(
    segs: list[dict],
    max_dy: float = 20,
    min_ratio: float = 0.6,
) -> bool:
    """
    A real text column has consecutive lines close together.
    Right-aligned dates on a single-column resume do not.
    """
    tops = sorted(seg["top"] for seg in segs)

    if len(tops) < 2:
        return False

    close = sum(1 for a, b in zip(tops, tops[1:]) if b - a <= max_dy)

    return close / (len(tops) - 1) >= min_ratio


def _detect_column_split(segments: list[dict]) -> dict | None:
    """
    Detect a genuine two-column layout.

    We only accept a split when:
    - both sides contain substantial content
    - both sides look like real columns (consecutive lines)
    - multiple rows contain left + right content simultaneously
    - the split is much cleaner than the crossing text
    """
    candidates = set()

    for left in segments:
        for right in segments:
            if left["x1"] < right["x0"]:
                boundary = (left["x1"] + right["x0"]) / 2
                candidates.add(round(boundary, 2))

    best = None

    for boundary in candidates:
        left_segments = [s for s in segments if s["x1"] <= boundary]
        right_segments = [s for s in segments if s["x0"] >= boundary]

        if len(left_segments) < 5:
            continue

        if len(right_segments) < 5:
            continue

        if not _has_vertical_continuity(left_segments):
            continue

        if not _has_vertical_continuity(right_segments):
            continue

        # Count rows where both columns contain content.
        paired_rows = 0

        for left in left_segments:
            has_right_neighbor = any(
                abs(left["top"] - right["top"]) <= 16 for right in right_segments
            )

            if has_right_neighbor:
                paired_rows += 1

        crossing_segments = len(segments) - len(left_segments) - len(right_segments)

        score = paired_rows - crossing_segments * 1.5

        candidate = {
            "score": score,
            "boundary": boundary,
            "left": left_segments,
            "right": right_segments,
            "paired_rows": paired_rows,
            "crossing_segments": crossing_segments,
        }

        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best is None:
        return None

    if best["score"] < 5:
        return None

    if best["crossing_segments"] > 0.25 * len(segments):
        return None

    return best


def _is_section_boundary(segment: dict, heading_segment: dict) -> bool:
    """
    A segment ends the skills section if it is a known major heading, or
    an all-caps line styled like the skills heading itself (same font
    and size).
    """
    text = segment["text"].strip()

    if _normalize_heading_text(text) in MAJOR_SECTION_HEADINGS:
        return True

    same_style = (
        segment["fontname"] == heading_segment["fontname"]
        and abs(segment["size"] - heading_segment["size"]) <= 0.5
    )

    return same_style and text.isupper() and len(text) < 40


def _locate_skills_section_in_page(segments: list[dict]) -> dict:
    """Locate the skills heading directly from visual PDF segments."""
    scores = []

    for index, segment in enumerate(segments):
        following = [item["text"] for item in segments[index + 1 : index + 4]]
        scores.append(_score_heading_candidate(segment["text"], following))

    if not scores:
        return {"found": False, "heading": None, "heading_index": None, "column": None, "column_boundary": None}

    best_index = max(range(len(scores)), key=lambda index: scores[index])
    best_score = scores[best_index]

    if best_score < SCORE_THRESHOLD:
        return {"found": False, "heading": None, "heading_index": None, "column": None, "column_boundary": None}

    heading = segments[best_index]

    split = _detect_column_split(segments)

    if split is None:
        column = None
        boundary = None
    else:
        boundary = split["boundary"]

        if heading["x1"] <= boundary:
            column = "left"
        elif heading["x0"] >= boundary:
            column = "right"
        else:
            column = None

    return {
        "found": True,
        "heading": heading["text"],
        "heading_index": best_index,
        "column": column,
        "column_boundary": boundary,
    }


def _locate_in_pdf_bytes(raw: bytes) -> dict:
    """
    Extract the complete Skills section from PDF bytes while respecting
    the document's visual columns.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page_segments = [_extract_visual_segments(page) for page in pdf.pages]

        # Find the strongest skills heading across all pages.
        best_match = None

        for page_index, segments in enumerate(page_segments):
            located = _locate_skills_section_in_page(segments)

            if not located["found"]:
                continue

            heading_index = located["heading_index"]
            heading_segment = segments[heading_index]

            score = _score_heading_candidate(
                heading_segment["text"],
                [item["text"] for item in segments[heading_index + 1 : heading_index + 4]],
            )

            candidate = {
                "score": score,
                "page_index": page_index,
                "heading_index": heading_index,
                "heading_segment": heading_segment,
                "column": located["column"],
                "boundary": located["column_boundary"],
            }

            if best_match is None or candidate["score"] > best_match["score"]:
                best_match = candidate

        if best_match is None:
            return {"found": False, "heading": None, "section_text": ""}

        output = []

        start_page = best_match["page_index"]
        heading_segment = best_match["heading_segment"]
        column = best_match["column"]
        boundary = best_match["boundary"]

        for page_index in range(start_page, len(page_segments)):
            segments = page_segments[page_index]

            for segment in segments:
                if page_index == start_page:
                    if segment["top"] <= heading_segment["top"]:
                        continue

                # Skip segments that lie entirely in the other column.
                if boundary is not None:
                    if column == "left" and segment["x0"] >= boundary:
                        continue

                    if column == "right" and segment["x1"] <= boundary:
                        continue

                # Stop at the next major section.
                if _is_section_boundary(segment, heading_segment):
                    return {
                        "found": True,
                        "heading": heading_segment["text"],
                        "section_text": "\n".join(output).strip(),
                    }

                if segment["text"].strip():
                    output.append(segment["text"])

        return {
            "found": True,
            "heading": heading_segment["text"],
            "section_text": "\n".join(output).strip(),
        }


# ---------------------------------------------------------------------
# Path B: flat-text fallback for DOCX / TXT (no page geometry).
# ---------------------------------------------------------------------


def _locate_in_text(resume_text: str) -> dict:
    lines = resume_text.split("\n")

    scores = [
        _score_heading_candidate(line, lines[i + 1 : i + 4])
        for i, line in enumerate(lines)
    ]

    if not scores:
        return {"found": False, "heading": None, "section_text": ""}

    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_score = scores[best_idx]

    if best_score < SCORE_THRESHOLD:
        return {"found": False, "heading": None, "section_text": ""}

    heading_text = lines[best_idx].strip()

    section_lines = []

    for line in lines[best_idx + 1 :]:
        if _is_major_section_boundary(line):
            break

        if line.strip():
            section_lines.append(line)

    return {
        "found": True,
        "heading": heading_text,
        "section_text": "\n".join(section_lines),
    }


# ---------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def locate_skills_section(raw: bytes, filename: str) -> dict:
    """
    Locate the Skills section of a resume.

    Returns {"found": bool, "heading": str | None, "section_text": str}.
    Never raises for "no section found" -- that's a normal, expected
    outcome (found=False) that the caller turns into a clean FAILED
    status rather than a crash. Extraction-level failures (corrupt file,
    unsupported type) still propagate, same as text_extract.py.
    """
    ext = _get_extension(filename)

    if ext == ".pdf":
        return _locate_in_pdf_bytes(raw)

    # DOCX / TXT: no column geometry to reconstruct, so reuse the
    # existing linear text extraction and scan it the same way the
    # notebook's flat-text fallback does.
    from app.core.text_extract import extract_text_from_bytes

    text = extract_text_from_bytes(raw, filename)
    return _locate_in_text(text)