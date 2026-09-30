"""
Try the JD requirements locator on local files, without the DB, Redis,
Celery or an LLM.

Run from the backend/ folder:

    python scripts/try_jd_locator.py path/to/jd.pdf other.docx some_folder/
    python scripts/try_jd_locator.py jd.pdf --json          # machine-readable
    python scripts/try_jd_locator.py jd.pdf --llm           # also call the LLM

For every file it runs exactly what run_jd_skills_extraction_task runs, in
the same order, and prints each stage:

  1. locate_jd_requirements(bytes, filename)   -> heading + section text
  2. normalize_parentheses -> strip_structural_labels
                                                -> "LLM input"
  3. (--llm only) extract_jd_skills_only -> postprocess_skills

Stage 2's output is the literal text the LLM receives, so this is the
place to check whether a JD's requirements were isolated cleanly.

--llm needs everything the worker needs (DATABASE_URL reachable, an
llm_configs row for task "jd_skills", HF_TOKEN / OPENAI_API_KEY).

Exit code is 1 if any file's section was not found or the pipeline
errored, so this also works in a shell loop / CI step.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.jd_skills_locator import locate_jd_requirements  # noqa: E402
from app.core.skills_text_prep import (  # noqa: E402
    normalize_parentheses,
    strip_structural_labels,
)

_SUFFIXES = {".pdf", ".docx", ".txt"}


def _expand(paths: list[str]) -> list[Path]:
    files: list[Path] = []

    for raw in paths:
        path = Path(raw)

        if path.is_dir():
            files.extend(
                sorted(p for p in path.rglob("*") if p.suffix.lower() in _SUFFIXES)
            )
        else:
            files.append(path)

    return files


def _run_one(path: Path, use_llm: bool) -> dict:
    result: dict = {"file": str(path), "ok": False}

    if not path.exists():
        result["error"] = "file not found"
        return result

    raw = path.read_bytes()
    started = time.perf_counter()

    try:
        located = locate_jd_requirements(raw, path.name)
    except Exception as exc:  # corrupt file, unsupported type, ...
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["locate_seconds"] = round(time.perf_counter() - started, 3)
    result["found"] = located["found"]
    result["heading"] = located["heading"]
    result["section_text"] = located["section_text"]

    if not located["found"] or not located["section_text"].strip():
        result["error"] = "no required-skills section located"
        return result

    prepared = strip_structural_labels(normalize_parentheses(located["section_text"]))
    result["llm_input"] = prepared

    if not prepared.strip():
        result["error"] = "section located but empty after cleaning"
        return result

    if use_llm:
        from app.core.jd_skills_llm_extract import extract_jd_skills_only
        from app.core.skills_text_prep import postprocess_skills

        try:
            raw_skills = extract_jd_skills_only(prepared)
            skills, hallucinated, dupes = postprocess_skills(
                raw_skills, source_text=prepared
            )
        except Exception as exc:
            result["error"] = f"LLM stage: {type(exc).__name__}: {exc}"
            return result

        result["skills"] = skills
        result["dropped_hallucinated"] = hallucinated
        result["duplicates_removed"] = dupes

    result["ok"] = True
    return result


def _print_human(result: dict) -> None:
    print("=" * 78)
    print(result["file"])

    if "locate_seconds" in result:
        print(f"located in {result['locate_seconds']}s")

    print(f"found:   {result.get('found')}")
    print(f"heading: {result.get('heading')!r}")

    if result.get("section_text"):
        print("-" * 30, "located section", "-" * 30)
        print(result["section_text"])

    if result.get("llm_input") is not None:
        print("-" * 30, "LLM input (after cleaning)", "-" * 30)
        print(result["llm_input"])

    if "skills" in result:
        print("-" * 30, "skills after validation", "-" * 30)
        print(result["skills"])

        if result["dropped_hallucinated"]:
            print("dropped as hallucinated:", result["dropped_hallucinated"])

    if result.get("error"):
        print(f"!! {result['error']}")

    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="+", help="JD files and/or folders")
    parser.add_argument("--json", action="store_true", help="print JSON, not text")
    parser.add_argument("--llm", action="store_true", help="also run the LLM stage")
    args = parser.parse_args()

    files = _expand(args.paths)

    if not files:
        print("no .pdf/.docx/.txt files found", file=sys.stderr)
        return 1

    results = [_run_one(path, args.llm) for path in files]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            _print_human(result)

        passed = sum(1 for r in results if r["ok"])
        print(f"{passed}/{len(results)} files produced a usable section")

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())