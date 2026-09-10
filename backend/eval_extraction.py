"""
Manual eval harness for Phase 4 extraction — step 3 of the plan: check
accuracy on real documents *before* wiring up Celery.

Usage:
    python eval_extraction.py resume path/to/resume.pdf
    python eval_extraction.py resume storage/resumes/<owner>/<file>.pdf
    python eval_extraction.py job path/to/jd.txt

Requires Ollama running locally with OLLAMA_EXTRACTION_MODEL pulled
(see app/core/config.py — defaults to qwen2.5:7b-instruct).
"""
import json
import sys
from pathlib import Path

from app.core.text_extract import extract_text_from_bytes
from app.core.llm_extract import extract_candidate_profile, extract_job_requirements


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    kind, path_str = sys.argv[1], sys.argv[2]
    path = Path(path_str)
    raw_bytes = path.read_bytes()
    text = extract_text_from_bytes(raw_bytes, path.name)

    print(f"--- extracted text ({len(text)} chars) ---")
    print(text[:500] + ("..." if len(text) > 500 else ""))
    print()

    if kind == "resume":
        result = extract_candidate_profile(text)
    elif kind == "job":
        result = extract_job_requirements(text)
    else:
        print(f"Unknown kind '{kind}' — use 'resume' or 'job'")
        sys.exit(1)

    print("--- structured extraction ---")
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()