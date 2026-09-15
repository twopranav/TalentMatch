"""
Unified extraction eval harness — the only place model/provider choices
get compared side by side. llm_extract.py's public functions
(extract_candidate_profile/extract_job_requirements) stay fixed to
settings.HF_EXTRACTION_MODEL/HF_INFERENCE_PROVIDER, as production
expects; this harness is a throwaway tool for arriving at that
configuration, not a permanent code path.

Usage (run from inside backend/, so `app.*` imports resolve):
    python3 eval_harness.py resume path/to/resume.pdf
    python3 eval_harness.py job path/to/jd.txt
    python3 eval_harness.py job path/to/jds/            # every JD in a folder
    python3 eval_harness.py resume path/to/resume.pdf --models Qwen/Qwen3-32B:cerebras openai/gpt-oss-120b:groq
"""
import argparse
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.core.llm_extract import (
    _extract_candidate_profile_for_eval,
    _extract_job_requirements_for_eval,
    ExtractionError,
)
from app.core.text_extract import ALLOWED_EXTENSIONS, EmptyExtractionError, UnsupportedFileTypeError, extract_text_from_bytes

_TEXT_PREVIEW_CHARS = 500
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2  # 2s, 4s, 8s

def _call_with_retry(fn, *args):
    """Retries on transient provider errors (429, network blips) with
    exponential backoff. Doesn't retry on ValidationError/ExtractionError
    (bad content, not a transient failure) or on HTTP 402 (billing —
    credits are either present or not; retrying won't make more appear)."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args)
        except (ValidationError, ExtractionError):
            raise  # not transient, don't retry
        except Exception as e:
            if "402" in str(e) or "Payment Required" in str(e):
                raise  # billing exhausted — retrying won't fix this
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                print(f"[retrying in {wait}s after error: {e}]")
                time.sleep(wait)
    raise last_error

def run_one(kind: str, text: str, model: str, provider: str) -> None:
    print(f"\n{'=' * 60}\nkind={kind}  model={model}  provider={provider}\n{'=' * 60}")
    try:
        if kind == "resume":
            result, meta = _call_with_retry(_extract_candidate_profile_for_eval, text, model, provider)
        else:
            result, meta = _call_with_retry(_extract_job_requirements_for_eval, text, model, provider)
    except (json.JSONDecodeError, ValidationError, ExtractionError) as e:
        print(f"[FAILED]: {e}")
        return
    except Exception as e:
        print(f"[PROVIDER/NETWORK ERROR after {_MAX_RETRIES} attempts]: {e}")
        return

    if meta.get("prompt_tokens") is not None:
        print(f"[tokens: prompt={meta['prompt_tokens']} completion={meta['completion_tokens']}]")
    print(f"[took {meta['elapsed']:.2f}s]")
    print(json.dumps(result.model_dump(), indent=2))

def run_file(kind: str, path: Path, models: list[str]) -> None:
    """Extracts text from one file and runs every requested model/provider
    against it. Pulled out of main() so --dir can call this per-file
    without duplicating the text-extraction/preview logic."""
    print(f"\n{'#' * 60}\nfile={path.name}\n{'#' * 60}")
    try:
        text = extract_text_from_bytes(path.read_bytes(), path.name)
    except (UnsupportedFileTypeError, EmptyExtractionError) as e:
        print(f"[SKIPPED]: {e}")
        return
    print(f"--- extracted text ({len(text)} chars) ---")
    print(text[:_TEXT_PREVIEW_CHARS] + ("..." if len(text) > _TEXT_PREVIEW_CHARS else ""))

    for entry in models:
        model, _, provider = entry.partition(":")
        if not provider:
            print(f"Skipping '{entry}': expected 'model:provider' format")
            continue
        run_one(kind, text, model, provider)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["resume", "job"])
    parser.add_argument(
        "file",
        help="Path to a single sample document (.pdf/.docx/.txt), OR a "
             "directory — every supported file directly inside it is run "
             "in turn (not recursive).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[f"{settings.HF_EXTRACTION_MODEL}:{settings.HF_INFERENCE_PROVIDER}"],
        help="One or more 'model:provider' pairs, e.g. Qwen/Qwen3-32B:cerebras openai/gpt-oss-120b:groq",
    )
    args = parser.parse_args()

    path = Path(args.file)
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
            run_file(args.kind, f, args.models)
    else:
        run_file(args.kind, path, args.models)


if __name__ == "__main__":
    sys.exit(main())