"""
Deterministic experience-years calculation from extracted work_history
date ranges.

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
from datetime import date

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from app.schemas.extraction import WorkHistoryEntry

logger = logging.getLogger(__name__)

_CURRENT_MARKERS = {"present", "current", "currently", "now", "ongoing", "till date", "to date"}


def _parse_month(text: str | None, *, is_end: bool) -> date | None:
    """Parses a free-text date like 'Jun 2021', '2021-06', '2021' into a
    date. Ambiguous/unparseable text returns None rather than raising —
    a bad single entry shouldn't blow up the whole calculation.
    default=date(1900,1,1) lets partial dates like a bare year fill in a
    month deterministically instead of defaulting to today's month
    (dateutil's own default), which would silently bias every bare-year
    entry toward whatever month happens to be current."""
    if not text or not text.strip():
        return None
    normalized = text.strip().lower()
    if normalized in _CURRENT_MARKERS:
        return date.today() if is_end else None
    try:
        parsed = date_parser.parse(text, default=date(1900, 1, 1), fuzzy=True)
        return date(parsed.year, parsed.month, 1)
    except (ValueError, OverflowError):
        logger.warning("Could not parse work_history date %r", text)
        return None


def compute_experience_years(work_history: list[WorkHistoryEntry]) -> int | None:
    """Returns total distinct months of experience (as whole years,
    rounded to nearest), merging overlapping ranges so concurrent jobs
    aren't double-counted. Returns None if there's no usable date range
    at all (matches the "no work history -> null, not 0" contract)."""
    intervals: list[tuple[date, date]] = []
    today = date.today()

    for entry in work_history:
        start = _parse_month(entry.start_date, is_end=False)
        end = _parse_month(entry.end_date, is_end=True)
        if end is None and entry.end_date and entry.end_date.strip().lower() not in _CURRENT_MARKERS:
            # end_date present but unparseable -> skip rather than guess
            end = None
        if start is None:
            continue
        if end is None:
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

    total_months = sum(
        relativedelta(end, start).years * 12 + relativedelta(end, start).months
        for start, end in merged
    )
    return round(total_months / 12)