"""
Standalone smoke test for the JD required-skills extraction pipeline.

Runs locate_required_skills -> normalize_parentheses ->
strip_structural_labels -> extract_jd_skills_only -> postprocess_skills
directly against a file or folder of JDs, printing every stage's output.
No DB, no Celery, no API route involved -- isolates the pipeline itself
from the async plumbing around it (upload route, task dispatch, the
frontend's polling), so a bug in one doesn't get mistaken for a bug in
the other.

Run from inside backend/, so `app.*` imports resolve:
    python test_jd_extraction.py "../testing files/test jds/"
    python test_jd_extraction.py "../testing files/test jds/some_jd.pdf"
"""

import sys
import time
from pathlib import Path

from app.core.jd_skills_llm_extract import JDSkillsExtractionError, extract_jd_skills_only
from app.core.jd_skills_locator import locate_required_skills
from app.core.skills_text_prep import (
    normalize_parentheses,
    postprocess_skills,
    strip_structural_labels,
)
from app.core.text_extract import (
    ALLOWED_EXTENSIONS,
    EmptyExtractionError,
    UnsupportedFileTypeError,
    extract_text_from_bytes,
)

_PREVIEW_CHARS = 400
_RETRIES = 2
_BACKOFF_BASE_SECONDS = 2


def _call_with_retry(prepared_text: str) -> list[str]:
    """HF calls can hit transient network/provider errors -- retry those
    with backoff, same rationale as eval_harness.py had. A real
    JDSkillsExtractionError (bad content, provider rejected the request)
    is not transient, so it's not retried."""
    last_error: Exception | None = None

    for attempt in range(_RETRIES + 1):
        try:
            return extract_jd_skills_only(prepared_text)
        except JDSkillsExtractionError:
            raise
        except Exception as e:
            last_error = e
            if attempt < _RETRIES:
                wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                print(f"  [retrying in {wait}s after error: {e}]")
                time.sleep(wait)

    raise last_error


def run_one(path: Path) -> None:
    print(f"\n{'#' * 60}\nfile={path.name}\n{'#' * 60}")

    try:
        jd_text = extract_text_from_bytes(path.read_bytes(), path.name)
    except (UnsupportedFileTypeError, EmptyExtractionError) as e:
        print(f"[SKIPPED -- text extraction]: {e}")
        return

    print(f"--- raw text ({len(jd_text)} chars) ---")
    print(jd_text[:_PREVIEW_CHARS] + ("..." if len(jd_text) > _PREVIEW_CHARS else ""))

    # Stage 1: locator
    located = locate_required_skills(jd_text)

    if not located["found"] or not located["section_text"].strip():
        print("[STOPPED -- locator]: no required-skills section found.")
        return

    print(f"\n--- located section (heading: {located['heading']!r}) ---")
    print(located["section_text"][:_PREVIEW_CHARS] + (
        "..." if len(located["section_text"]) > _PREVIEW_CHARS else ""
    ))

    # Stage 2: deterministic prep (same order jd_skills_extraction_tasks.py
    # uses -- normalize_parentheses -> strip_structural_labels, no
    # strip_leading_dates on the JD side)
    prepared = normalize_parentheses(located["section_text"])
    prepared = strip_structural_labels(prepared)

    if not prepared.strip():
        print("[STOPPED -- prep]: section located but no usable text after cleanup.")
        return

    print(f"\n--- prepared text (what the model sees) ---")
    print(prepared[:_PREVIEW_CHARS] + ("..." if len(prepared) > _PREVIEW_CHARS else ""))

    # Stage 3: LLM normalizer
    try:
        raw_skills = _call_with_retry(prepared)
    except JDSkillsExtractionError as e:
        print(f"\n[FAILED -- LLM extraction]: {e}")
        return

    print(f"\n--- raw model output ({len(raw_skills)} items) ---")
    print(raw_skills)

    # Stage 4: postprocess (validate against `prepared`, not the
    # original JD text -- see postprocess_skills' docstring for why)
    skills, hallucinated, dupes_removed = postprocess_skills(raw_skills, source_text=prepared)

    print(f"\n--- final skills ({len(skills)}) ---")
    print(skills)

    if hallucinated:
        print(f"[dropped {len(hallucinated)} hallucinated]: {hallucinated}")

    if dupes_removed:
        print(f"[removed {dupes_removed} exact duplicate(s)]")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])

    if path.is_dir():
        files = sorted(
            p for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
        )
        if not files:
            print(f"No {sorted(ALLOWED_EXTENSIONS)} files found directly in '{path}'")
            return
        print(f"Found {len(files)} file(s) in '{path}':")
        for f in files:
            print(f"  {f.name}")
        for f in files:
            run_one(f)
    else:
        run_one(path)


if __name__ == "__main__":
    main()