"""
Deterministic experience-years calculation from extracted work_history
date ranges and job description (JD) requirement text.

This exists because asking the LLM to compute experience_years itself
(sum date ranges, resolve "Present", dedupe overlaps) is unreliable —
small local models are bad at multi-step date arithmetic, and the model
has no ground truth for "today". We still let the LLM extract the raw
start_date/end_date strings (it's good at reading text), but the actual
math happens here in code, against the real current date, so results are
reproducible and correct.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from app.schemas.extraction import WorkHistoryEntry

logger = logging.getLogger(__name__)

_CURRENT_MARKERS = {"present", "current", "currently", "now", "ongoing", "till date", "to date"}

# dateutil fills any missing year from `default` (1900 below). A string with
# no 4-digit year -- "Jan '20", "06/21", "20" -- therefore comes back as
# 1900 and would add ~125 phantom years. Anything before this is rejected.
_MIN_VALID_YEAR = 1970


def _parse_month(text: str | None, *, is_end: bool, today: date | None = None) -> date | None:
    """Parses a free-text date like 'Jun 2021', '2021-06', '2021' into a
    date. Ambiguous/unparseable text returns None rather than raising —
    a bad single entry shouldn't blow up the whole calculation.
    default=date(1900,1,1) lets partial dates like a bare year fill in a
    month deterministically instead of defaulting to today's month
    (dateutil's own default), which would silently bias every bare-year
    entry toward whatever month happens to be current."""
    if not text or not text.strip():
        return None
    today = today or date.today()
    normalized = text.strip().lower()
    if normalized in _CURRENT_MARKERS:
        return today if is_end else None
    try:
        parsed = date_parser.parse(text, default=date(1900, 1, 1), fuzzy=True)
    except (ValueError, OverflowError):
        logger.warning("Could not parse work_history date %r", text)
        return None
    if parsed.year < _MIN_VALID_YEAR:
        logger.warning("Ignoring work_history date %r (no usable year)", text)
        return None
    return date(parsed.year, parsed.month, 1)


def compute_experience_months(
    work_history: list[WorkHistoryEntry], today: date | None = None
) -> int | None:
    """Total distinct months of experience, merging overlapping ranges so
    concurrent jobs aren't double-counted. Returns None if there's no
    usable date range at all (matches the "no work history -> null, not 0"
    contract). `today` is injectable so tests don't depend on the clock.
    Months are kept (not rounded to years) so a matcher can compare 1.4
    years against a "1.5+ years" requirement."""
    intervals: list[tuple[date, date]] = []
    today = today or date.today()

    for entry in work_history:
        start = _parse_month(entry.start_date, is_end=False, today=today)
        end = _parse_month(entry.end_date, is_end=True, today=today)
        if start is None:
            continue
        if end is None:
            if entry.end_date and entry.end_date.strip():
                # end_date present but unparseable -> skip rather than guess.
                # (Treating it as "Present" used to inflate the total.)
                continue
            # No end_date at all is treated the same as "Present" — an
            # open-ended entry with a real start date is still a real job.
            end = today
        if end < start:
            continue
        intervals.append((start, min(end, today)))

    if not intervals:
        return None

    intervals.sort(key=lambda iv: iv[0])
    merged: list[tuple[date, date]] = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return sum(
        relativedelta(end, start).years * 12 + relativedelta(end, start).months
        for start, end in merged
    )


def compute_experience_years(
    work_history: list[WorkHistoryEntry], today: date | None = None
) -> int | None:
    """Whole years, rounded to nearest (same contract as before)."""
    months = compute_experience_months(work_history, today=today)
    return None if months is None else round(months / 12)


# ---------------------------------------------------------------------
# JD side: minimum experience REQUIRED by a job description
# ---------------------------------------------------------------------

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
    "fifteen": 15, "twenty": 20,
}
_QTY = r"\d+(?:\.\d+)?|" + "|".join(_NUM_WORDS)
_UNIT = r"(?:years?|yrs?|months?|mos?)"

# "5 years", "5+ years", "3-5 years", "3 to 5 yrs", "6 months - 1 year",
# "at least 1.5 years", "two years". Case-insensitive because the PDF path
# hands us lowercased text.
_EXPERIENCE_RE = re.compile(
    rf"\b(?P<lo>{_QTY})\s*(?P<lo_unit>{_UNIT})?\s*(?:\+|plus)?\s*"
    rf"(?:(?:-|\u2013|\u2014|to)\s*(?P<hi>{_QTY})\s*(?:\+|plus)?\s*)?"
    rf"(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)

# A duration only counts if experience-ish wording is nearby. This is what
# keeps "founded 10 years ago" / "4 weeks of PTO" style text out.
_EXPERIENCE_CUE_RE = re.compile(
    r"experience|\bexp\b|background|track record|hands-on|proven", re.IGNORECASE
)
_NOT_A_REQUIREMENT_BEFORE_RE = re.compile(r"(?:last|past)\s*$", re.IGNORECASE)
_NOT_A_REQUIREMENT_AFTER_RE = re.compile(
    r"^\s*(?:ago|in business|of history)", re.IGNORECASE
)
_PREFERRED_CUE_RE = re.compile(
    r"preferred|nice to have|good to have|bonus|a plus|desirable|ideally|"
    r"added advantage|advantage",
    re.IGNORECASE,
)
_ENTRY_LEVEL_RE = re.compile(
    r"\bfreshers?\b|entry[- ]level|no (?:prior |previous )?experience "
    r"(?:is )?(?:required|needed|necessary)",
    re.IGNORECASE,
)

_MAX_PLAUSIBLE_MONTHS = 40 * 12


@dataclass(frozen=True)
class ExperienceMention:
    min_months: int
    max_months: int | None  # None for "5+" / "5 years" (open-ended)
    text: str               # the matched snippet, for logging/debugging
    preferred: bool         # True if it sits on a nice-to-have line


@dataclass(frozen=True)
class ExperienceRequirement:
    min_months: int | None            # None = JD states no experience requirement
    mentions: tuple[ExperienceMention, ...]
    source: str | None                # "requirements_section" | "full_text" | "entry_level_marker" | None

    @property
    def min_years(self) -> float | None:
        return None if self.min_months is None else round(self.min_months / 12, 1)


def _to_number(token: str) -> float:
    token = token.lower()
    return float(_NUM_WORDS[token]) if token in _NUM_WORDS else float(token)


def _to_months(value: float, unit: str) -> int:
    return round(value * (12 if unit.lower().startswith("y") else 1))


def _line_context(text: str, start: int, end: int) -> str:
    """The matched line, plus the previous line if it is short enough to be
    a sub-heading like 'Preferred:' -- so a bullet under a nice-to-have
    heading is still recognised as preferred."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    context = text[line_start:line_end]

    if line_start > 0:
        prev_start = text.rfind("\n", 0, line_start - 1) + 1
        prev = text[prev_start:line_start - 1].strip()
        if prev and len(prev) <= 40:
            context = prev + " " + context
    return context


def _find_mentions(text: str) -> list[ExperienceMention]:
    mentions: list[ExperienceMention] = []

    for m in _EXPERIENCE_RE.finditer(text):
        before = text[max(0, m.start() - 50):m.start()]
        after = text[m.end():m.end() + 80].split("\n\n")[0]
        window = (before + " " + m.group(0) + " " + after).replace("\n", " ")

        if not _EXPERIENCE_CUE_RE.search(window):
            continue
        if _NOT_A_REQUIREMENT_BEFORE_RE.search(before):
            continue
        if _NOT_A_REQUIREMENT_AFTER_RE.search(after):
            continue

        unit = m.group("unit")
        lo_months = _to_months(_to_number(m.group("lo")), m.group("lo_unit") or unit)
        hi_months = (
            _to_months(_to_number(m.group("hi")), unit) if m.group("hi") else None
        )

        if lo_months > _MAX_PLAUSIBLE_MONTHS:
            continue
        if hi_months is not None and hi_months < lo_months:
            hi_months = None  # malformed range like "5 to 2"; keep the low end

        mentions.append(
            ExperienceMention(
                min_months=lo_months,
                max_months=hi_months,
                text=m.group(0).strip(),
                preferred=bool(
                    _PREFERRED_CUE_RE.search(_line_context(text, m.start(), m.end()))
                ),
            )
        )

    return mentions


def extract_min_experience(
    section_text: str | None,
    full_text: str | None = None,
) -> ExperienceRequirement:
    """Minimum experience a JD demands, in months.

    Tries the located requirements section first, then the full JD text.
    Among non-preferred mentions the LARGEST lower bound wins: for
    "5+ years overall, 2+ years with AWS" the overall bar is 5. All mentions
    are returned so a matcher can look at per-skill durations later.

    Known limits: "2 years Python OR 4 years any language" resolves to 4;
    degree-equivalence clauses ("or Master's + 2 years") aren't modelled.
    Returns min_months=None (not 0) when the JD states nothing, mirroring
    the "no work history -> null" contract on the resume side.
    """
    for source, text in (
        ("requirements_section", section_text),
        ("full_text", full_text),
    ):
        if not text or not text.strip():
            continue

        mentions = _find_mentions(text)
        required = [mn for mn in mentions if not mn.preferred]

        if required:
            return ExperienceRequirement(
                min_months=max(mn.min_months for mn in required),
                mentions=tuple(mentions),
                source=source,
            )

    for text in (section_text, full_text):
        if text and _ENTRY_LEVEL_RE.search(text):
            return ExperienceRequirement(0, (), "entry_level_marker")

    return ExperienceRequirement(None, (), None)


def meets_experience_requirement(
    candidate_months: int | None, required_months: int | None
) -> bool | None:
    """True/False when both sides are known; None means 'can't tell' so the
    matcher can show 'unknown' instead of silently failing or passing."""
    if required_months is None or candidate_months is None:
        return None
    return candidate_months >= required_months