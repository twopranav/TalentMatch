"""
Deterministic text preparation for the standalone skills-extraction path.

None of this calls the model. It runs immediately before the call (to
hand the model the cleanest possible input) and immediately after (as a
safety net the model's own mistakes can't undermine). Splitting work this
way -- regex/rules for anything that is genuinely mechanical, the model
only for the part that actually requires judgement (deciding where one
skill name ends and the next begins) -- is what keeps the LLM prompt
small and its failure modes narrow.

Two independent origins, kept distinct on purpose:

- normalize_parentheses / strip_leading_dates come from the
  skills-section-locator notebook. They deal with PDF-layout noise:
  "AWS (ECS, S3, IAM)" style grouping, stray bullet/(cid:127) artifacts,
  and employment dates that ride along on the same visual row as a
  skill line in a narrow column.

- strip_structural_labels / postprocess_skills come from run-test.py,
  the harness used to iterate on skills_extraction_prompt.txt against
  resume-blocks.json (see score.py for how they're evaluated). They
  deal with prompt-input hygiene (removing "languages:" style category
  headers before the model ever sees them) and output hygiene (dropping
  anything the model invented or duplicated).

Three-source extraction (skills section + work experience + projects)
adds build_skill_blocks / reroute_leaks / merge_source_skills below: the
same deterministic-before, deterministic-after wrapping, applied per
source block.

Both are ported close to verbatim -- this is validated logic, not a
rewrite -- with normalize_parentheses and strip_leading_dates adapted to
drop the Colab-only unused-var noise, and the docstrings kept so the
"why" travels with the code.
"""

import re

# ---------------------------------------------------------------------
# Parenthetical expansion + date stripping (from the section-locator
# notebook, cell 22).
# ---------------------------------------------------------------------

# Words that are usually a category label when they appear as the first
# word of a multi-word parenthetical base and are NOT followed by a
# colon (colon-terminated labels are already excluded by the regex
# below).
STRUCTURAL_LEADERS = {
    "cloud",
    "languages",
    "backend",
    "frontend",
    "databases",
    "database",
    "devops",
    "frameworks",
    "libraries",
    "tools",
}

# If the word after the leader is one of these, the two words form a
# real skill name (e.g. "cloud computing"), so nothing is stripped.
GENERIC_HEADS = {
    "computing",
    "development",
    "infrastructure",
    "native",
    "platform",
    "platforms",
    "services",
    "engineering",
    "architecture",
    "systems",
}


def remove_structural_prefix(base: str) -> str:
    """
    Remove an accidental category prefix from a parenthetical base.

    Examples:
        cloud azure            -> azure
        cloud computing        -> cloud computing
        frontend development   -> frontend development
        redis                  -> redis
    """
    words = base.split()

    if len(words) < 2:
        return base

    if words[0] in STRUCTURAL_LEADERS and words[1] not in GENERIC_HEADS:
        return " ".join(words[1:])

    return base


# Longest parenthetical base (in words) that is still treated as a skill name.
_MAX_EXPANSION_BASE_WORDS = 4

_PAREN_GROUP_RE = re.compile(r"([^()\n,:|]+?)\s*\(([^()]*)\)")


def normalize_parentheses(raw_text: str) -> str:
    """
    Lowercase the Skills section and expand parenthetical groups.

    Examples:

        AWS (ECS, S3, IAM, CloudWatch)
        ->
        aws, aws ecs, aws s3, aws iam, aws cloudwatch

        JavaScript (ES6+)
        ->
        javascript, javascript es6+

        Cloud Azure (basic)
        ->
        azure, azure basic
    """

    text = raw_text.lower()

    # ------------------------------------------------------------
    # 1. Fix common PDF extraction artifacts.
    # ------------------------------------------------------------

    text = re.sub(r"\(\s*cid:127\s*\)", ", ", text)

    text = text.replace("•", ", ")

    # ------------------------------------------------------------
    # 2. Expand genuine parenthetical groups.
    # ------------------------------------------------------------

    def expand_match(match: re.Match) -> str:
        raw_base = match.group(1)
        original_base = raw_base.strip()
        contents = match.group(2).strip()

        # Keep whatever whitespace preceded the base (for example the
        # space after "languages:") so neighbouring text is not glued
        # together.
        leading = raw_base[: len(raw_base) - len(raw_base.lstrip())]

        if not original_base or not contents:
            return match.group(0)

        # Expansion is for short skill-list entries ("AWS (ECS, S3)"). In a
        # prose sentence the regex's "base" swallows everything back to the
        # previous comma/newline, so expanding would duplicate that whole
        # run of text and corrupt the model's input. Leave long or
        # multi-sentence bases untouched; the prompt already tells the
        # model how to read "category (examples)" on its own.
        if len(original_base.split()) > _MAX_EXPANSION_BASE_WORDS or re.search(r"[.!?]\s", original_base):
            return match.group(0)

        base = remove_structural_prefix(original_base)

        if not base:
            return match.group(0)

        items = [item.strip() for item in re.split(r"[,;|]", contents) if item.strip()]

        if not items:
            return match.group(0)

        expanded = [base]

        for item in items:
            expanded.append(f"{base} {item}")

        return leading + ", ".join(expanded)

    previous = None

    while text != previous:
        previous = text
        text = _PAREN_GROUP_RE.sub(expand_match, text)

    return text


# Employment-date text such as "2023 - present" or "Jan 2020 - Mar 2022"
# occasionally rides along on the same visual row as the first word of a
# skills line when the column gutter is narrow. Skills lines never
# legitimately start with a date, so strip it.
_MONTH = (
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"[a-z]*\.?\s+)?"
)
_DATE = rf"{_MONTH}(?:19|20)\d{{2}}"
_DATE_END = rf"(?:present|current|now|{_DATE})"

LEADING_DATE_RE = re.compile(
    rf"^\s*{_DATE}(?:\s*(?:[\u2013\u2014-]|to)\s*{_DATE_END})?\s*",
    re.IGNORECASE,
)


def strip_leading_dates(section: str) -> str:
    """
    Remove leading date ranges from every line of the extracted section.
    Lines that contained only a date are dropped.
    """
    cleaned = []

    for line in section.split("\n"):
        line = LEADING_DATE_RE.sub("", line, count=1).strip()

        if line:
            cleaned.append(line)

    return "\n".join(cleaned)


# ---------------------------------------------------------------------
# Prompt-input and model-output hygiene (from run-test.py).
# ---------------------------------------------------------------------

_HEADER_WORDS = {
    "languages", "language", "frontend", "front-end", "backend",
    "back-end", "cloud", "devops", "databases", "database", "tools",
    "framework", "frameworks", "libraries", "skills", "technologies",
    "stack", "platforms",
}


def _is_bare_header(line: str, next_line: str) -> bool:
    if any(ch in line for ch in (",", "|", "/", ":")):
        return False

    words = re.split(r"\s*&\s*|\s+", line.strip())

    if not words or len(words) > 4:
        return False

    if not all(w.lower() in _HEADER_WORDS for w in words):
        return False

    # Only strip if what follows actually looks like a skill list --
    # i.e. not another bare short header line (which would suggest THIS
    # line is really a wrap continuation, not a header).
    next_stripped = next_line.strip()

    if not next_stripped:
        return False

    looks_like_skills = (
        "," in next_stripped
        or "|" in next_stripped
        or len(next_stripped.split()) > 1
    )

    return looks_like_skills


def strip_structural_labels(text: str) -> str:
    """
    Remove obvious category-label lines from the input, so the model's
    only job is splitting/joining actual skills -- not also deciding
    what counts as a label.

    - "languages:" alone on a line        -> line dropped
    - "cloud & devops: aws, docker"       -> "aws, docker"
    - "cloud" alone on a line, no colon,
      immediately followed by a real
      skill line                          -> line dropped

    Labels with a colon are handled generically (anything before the
    colon is structural, not a skill). Labels WITHOUT a colon are
    ambiguous in general -- a bare word on its own line could be a
    section header ("cloud", "devops") or the tail end of a wrapped
    skill name ("multi-tenant" / "saas"). Asking a small model to make
    that call reliably (on top of everything else in the prompt) turned
    out to cost more in dropped sections than it gained, so we only
    strip a bare line here when it's a near-certain header: no
    comma/pipe/slash of its own, a handful of words at most, made up of
    common section-header vocabulary, and followed by a line that
    actually looks like a skill list. Anything that doesn't clearly
    match stays untouched and is left for the prompt's own wrap-joining
    rule to handle.
    """

    raw_lines = [ln.strip() for ln in text.splitlines()]
    cleaned_lines = []

    for i, line in enumerate(raw_lines):
        if not line:
            continue

        next_line = raw_lines[i + 1] if i + 1 < len(raw_lines) else ""

        if _is_bare_header(line, next_line):
            continue

        if ":" in line:
            prefix, remainder = line.split(":", 1)

            if not remainder.strip():
                # Label-only line such as "languages:".
                continue

            if prefix.strip():
                line = remainder.strip()

        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def postprocess_skills(
    skills: list[str],
    source_text: str,
) -> tuple[list[str], list[str], int]:
    """
    Deterministic safety net applied AFTER the model responds, so it
    can't be undermined by the model ignoring the prompt's "copy
    exactly" / "no duplicates" rules.

    - Drop exact duplicates, keeping first-appearance order.
    - Drop any skill that isn't actually a substring of source_text
      once whitespace is collapsed. This catches character-level slips
      like the model writing "ukit" for "uikit" -- if a skill wasn't
      really in the text, it shouldn't be in the output.

    IMPORTANT: source_text must be the exact text the model was shown
    (i.e. after strip_leading_dates -> normalize_parentheses ->
    strip_structural_labels), not the original PDF-layout text. A
    legitimately expanded compound such as "aws ecs" only exists after
    normalize_parentheses runs, so checking against anything earlier
    would wrongly flag every expansion as hallucinated.

    Returns (cleaned_skills, dropped_hallucinated, num_dupes_removed).
    """

    text_norm = _normalize(source_text.replace("\n", " "))

    seen: set[str] = set()
    cleaned = []
    dropped = []
    dupes = 0

    for skill in skills:
        norm = _normalize(skill)

        if norm in seen:
            dupes += 1
            continue

        if norm not in text_norm:
            dropped.append(skill)
            continue

        seen.add(norm)
        cleaned.append(skill)

    return cleaned, dropped, dupes


# ---------------------------------------------------------------------
# Three-source extraction: skills section + work experience + projects.
# ---------------------------------------------------------------------

# One list per source comes back from the model, under these keys.
SOURCE_KEYS = ("skills_section", "work_experience", "projects")

_BULLET_PREFIX_RE = re.compile(r"^\s*(\(cid:\d+\)|[-*\u2022\u25cf\u2013>])\s*")


def clean_prose(text: str | None) -> str:
    """Experience / projects text is prose: drop bullet glyphs and blank
    lines, keep the sentences exactly as written."""
    return "\n".join(
        _BULLET_PREFIX_RE.sub("", line).strip()
        for line in (text or "").splitlines()
        if line.strip()
    )


def build_skill_blocks(located: dict) -> dict[str, str]:
    """
    Turn locate_resume_sections()' output into the three text blocks the
    model reads. A section that wasn't located becomes "".

    The skills block gets the full cleanup chain, and order matters:
    dates are stripped from the still-cased, still-grouped section text;
    normalize_parentheses then lowercases and expands any "AWS (ECS, S3)"
    style grouping; only after that do we strip bare category-label
    lines, since a label can itself sit inside a now-expanded line.
    Experience and projects are prose and only lose bullet glyphs.
    """
    skills = located["skills"]
    skills_text = ""

    if skills["found"] and skills["section_text"].strip():
        skills_text = strip_structural_labels(
            normalize_parentheses(strip_leading_dates(skills["section_text"]))
        ).strip()

    return {
        "skills_section": skills_text,
        "work_experience": clean_prose(located["experience"]["section_text"]),
        "projects": clean_prose(located["projects"]["section_text"]),
    }


def reroute_leaks(
    raw: dict[str, list[str]], blocks: dict[str, str]
) -> dict[str, list[str]]:
    """
    A skill the model put in the wrong list but that literally appears in
    another block's text moves there. A skill found in no block stays put
    and is dropped afterwards by postprocess_skills as hallucinated.
    """
    text = {k: _normalize(blocks[k].replace("\n", " ")) for k in blocks}
    routed: dict[str, list[str]] = {k: [] for k in blocks}

    for key in blocks:
        for skill in raw.get(key, []):
            norm = _normalize(skill)

            if norm in text[key]:
                routed[key].append(skill)
                continue

            for other in blocks:
                if other != key and norm in text[other]:
                    routed[other].append(skill)
                    break
            else:
                routed[key].append(skill)

    return routed


def fill_source_occurrences(
    by_source: dict[str, list[str]], blocks: dict[str, str]
) -> dict[str, list[str]]:
    """
    Make each source list complete: a skill the model listed under one
    source is also added to every other source whose text literally
    contains it (whole-word match). The model works block by block and can
    miss the second or third place a skill shows up; scoring needs to know
    every place, because a skill used in work or a project counts for more
    than one that is only listed.

    Only skills already in the lists are looked for, so nothing is invented.
    Existing order is kept; additions go at the end of that source's list.
    """
    text = {k: _normalize(blocks.get(k, "").replace("\n", " ")) for k in by_source}

    universe: dict[str, str] = {}
    for key in SOURCE_KEYS:
        for skill in by_source.get(key, []):
            universe.setdefault(_normalize(skill), skill)

    filled: dict[str, list[str]] = {}
    for key in by_source:
        have = {_normalize(s) for s in by_source[key]}
        extra = [
            skill
            for norm, skill in universe.items()
            if norm not in have and _contains_word(text[key], norm)
        ]
        filled[key] = list(by_source[key]) + extra

    return filled


def _contains_word(text_norm: str, skill_norm: str) -> bool:
    """Whole-word containment that survives skills like c++, c#, node.js:
    the skill must not be glued to a letter, digit, + or # on either side."""
    if not skill_norm:
        return False
    pattern = r"(?<![a-z0-9+#])" + re.escape(skill_norm) + r"(?![a-z0-9+#])"
    return re.search(pattern, text_norm) is not None


def merge_source_skills(by_source: dict[str, list[str]]) -> list[str]:
    """One flat, de-duplicated list (first appearance wins, source order
    follows SOURCE_KEYS) for consumers that match on skills alone."""
    seen: set[str] = set()
    merged: list[str] = []

    for key in SOURCE_KEYS:
        for skill in by_source.get(key, []):
            norm = _normalize(skill)

            if norm not in seen:
                seen.add(norm)
                merged.append(skill)

    return merged
