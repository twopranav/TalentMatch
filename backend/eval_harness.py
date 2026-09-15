"""
Standalone extraction test harness. No FastAPI, no Postgres, no Redis, no
Celery worker, no blob storage — this calls text_extract.py/llm_extract.py/
experience_calc.py exactly as they'd run in production, just with the
inputs and outputs printed straight to your terminal instead of flowing
through a request, a queue, and a DB row.

Usage (run from inside backend/, so `app.*` imports resolve):
    python3 eval_harness.py path/to/resume.pdf
    python3 eval_harness.py path/to/resume.pdf --models Qwen/Qwen3-32B:cerebras openai/gpt-oss-120b:groq

Each --models entry is "model:provider". Loop as many as you want in one
run; each prints its own timing + JSON output so you can eyeball
correctness and cost side by side before touching a single endpoint.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from huggingface_hub import InferenceClient

from app.core.config import settings
from app.core.llm_extract import (
    _CANDIDATE_SYSTEM_PROMPT,
    _strict_json_schema,
    ExtractionError,
)
from app.core.text_extract import extract_text_from_bytes
from app.core.experience_calc import compute_experience_years
from app.schemas.extraction import CandidateProfileExtraction
from pydantic import ValidationError


def run_one(file_bytes: bytes, filename: str, model: str, provider: str) -> None:
    print(f"\n{'=' * 60}\nmodel={model}  provider={provider}\n{'=' * 60}")

    text = extract_text_from_bytes(file_bytes, filename)
    print(f"[extracted {len(text)} chars of resume text after trim/cap]")

    client = InferenceClient(provider=provider, api_key=settings.HF_TOKEN)
    schema = _strict_json_schema(CandidateProfileExtraction.model_json_schema())

    start = time.monotonic()
    try:
        response = client.chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": _CANDIDATE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": True},
            },
            temperature=0.1,
        )
        elapsed = time.monotonic() - start
        raw = json.loads(response.choices[0].message.content)
        profile = CandidateProfileExtraction.model_validate(raw)
        profile.experience_years = compute_experience_years(profile.work_history)

        # Token usage, if the provider reports it — useful for eyeballing
        # free-tier credit burn per model before committing to one.
        usage = getattr(response, "usage", None)
        if usage:
            print(f"[tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens}]")
        print(f"[took {elapsed:.2f}s]")
        print(json.dumps(profile.model_dump(), indent=2))
    except (json.JSONDecodeError, ValidationError, ExtractionError) as e:
        elapsed = time.monotonic() - start
        print(f"[FAILED after {elapsed:.2f}s]: {e}")
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"[PROVIDER/NETWORK ERROR after {elapsed:.2f}s]: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to a sample resume (.pdf/.docx/.txt)")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[f"{settings.HF_EXTRACTION_MODEL}:{settings.HF_INFERENCE_PROVIDER}"],
        help="One or more 'model:provider' pairs to test against the same file, "
             "e.g. Qwen/Qwen3-32B:cerebras openai/gpt-oss-120b:groq",
    )
    args = parser.parse_args()

    path = Path(args.file)
    file_bytes = path.read_bytes()

    for entry in args.models:
        model, _, provider = entry.partition(":")
        if not provider:
            print(f"Skipping '{entry}': expected 'model:provider' format")
            continue
        run_one(file_bytes, path.name, model, provider)


if __name__ == "__main__":
    sys.exit(main())