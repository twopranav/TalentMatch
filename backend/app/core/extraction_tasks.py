"""
Celery task for asynchronous resume extraction.

The task handles:
- database state transitions
- downloading the stored resume
- text extraction
- Hugging Face structured extraction
- persistence of the extraction result

The actual extraction logic remains in llm_extract.py and text_extract.py.
"""

import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.llm_extract import ExtractionError, extract_candidate_profile
from app.core.resume_storage import download_resume_blob
from app.core.text_extract import (
    EmptyExtractionError,
    UnsupportedFileTypeError,
    extract_text_from_bytes,
)
from app.db.session import SessionLocal
from app.models.resume import Resume, ResumeExtractionStatus

logger = logging.getLogger(__name__)


@celery_app.task(
    name="extraction.run",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_extraction_task(self, resume_id: str) -> None:
    db = SessionLocal()

    try:
        resume = db.get(Resume, resume_id)

        if resume is None:
            logger.warning(
                "run_extraction_task: resume %s no longer exists",
                resume_id,
            )
            return

        resume.extraction_status = ResumeExtractionStatus.PROCESSING
        resume.extraction_error = None
        db.commit()

        try:
            file_bytes = download_resume_blob(resume.blob_path)

            text = extract_text_from_bytes(
                file_bytes,
                resume.original_filename,
            )

            profile = extract_candidate_profile(text)

        except (
            UnsupportedFileTypeError,
            EmptyExtractionError,
            ExtractionError,
        ) as exc:
            resume.extraction_status = ResumeExtractionStatus.FAILED
            resume.extraction_error = str(exc)
            db.commit()
            return

        except Exception as exc:
            logger.warning(
                "Resume extraction failed for %s: %s",
                resume_id,
                exc,
            )

            try:
                raise self.retry(exc=exc)

            except self.MaxRetriesExceededError:
                resume.extraction_status = ResumeExtractionStatus.FAILED
                resume.extraction_error = (
                    f"Extraction failed after retries: {exc}"
                )
                db.commit()

            return

        # -------------------------
        # Persist extraction
        # -------------------------

        resume.raw_text = text

        resume.extracted_skills = list(profile.skills)

        resume.extracted_stated_experience = (
            profile.stated_experience
        )

        resume.extracted_experience_years = (
            profile.experience_years
        )

        resume.extracted_education = [
            education.model_dump()
            for education in profile.education
        ]

        # IMPORTANT:
        # Certifications are Pydantic objects during extraction.
        # JSONB needs plain Python dictionaries.
        resume.extracted_certifications = [
            certification.model_dump()
            for certification in profile.certifications
        ]

        # Store the complete extraction as the source of truth.
        resume.extracted_profile = profile.model_dump()

        resume.extraction_status = ResumeExtractionStatus.DONE
        resume.extraction_error = None
        resume.extracted_at = datetime.now(timezone.utc)

        if resume.owner_id is None:
            resume.candidate_name = profile.candidate_name
            resume.candidate_email = profile.candidate_email

        db.commit()

    finally:
        db.close()