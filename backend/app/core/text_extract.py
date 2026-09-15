"""
Extracts raw text from a resume or JD file (PDF, DOCX, TXT).

Core logic (extract_text_from_bytes) works on raw bytes, not UploadFile,
so it can run both at upload time (from a FastAPI UploadFile, via
extract_text_from_upload) and inside a Celery worker (from bytes fetched
off blob storage, where there's no UploadFile / request context at all).
"""
import io
import logging
from collections import Counter

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MIN_TEXT_LENGTH = 50  # chars; below this, treat extraction as failed rather
                       # than silently handing an LLM step ~nothing to work with

_PDF_PAGE_CAP = 3  # resumes rarely run longer than this; also guards
                    # against a degenerate 40-page upload burning tokens
_BOILERPLATE_MAX_LINE_LEN = 60  # header/footer lines are short; a repeated
                                 # 60+ char line is more likely real content
                                 # (e.g. a bullet copy-pasted across two
                                 # jobs) than a page header or footer
_BOILERPLATE_REPEAT_RATIO = 0.5  # a line counts as boilerplate once it
                                  # shows up verbatim on at least half the
                                  # (capped) pages


class UnsupportedFileTypeError(Exception):
    pass


class EmptyExtractionError(Exception):
    """Mechanically succeeded but yielded ~no text — e.g. a scanned/
    image-only PDF with no embedded text layer."""
    pass


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _strip_pdf_boilerplate(pages_text: list[str]) -> str:
    """Removes lines that repeat verbatim across most pages (running
    headers/footers, "Page X of Y", a repeated name banner) — these cost
    tokens on every page without giving the LLM any information it
    doesn't already have from page 1.

    Approach: split every page into its own lines, count how many pages
    each distinct line shows up on (a line counted once per page even if
    it appears twice on that page, so a genuinely repeated bullet inside
    a single page isn't penalized), then drop any short line that clears
    the repeat threshold. With a single page there's nothing to compare
    against, so nothing is stripped.
    """
    if len(pages_text) <= 1:
        return pages_text[0] if pages_text else ""

    page_lines = [[line.strip() for line in p.split("\n") if line.strip()] for p in pages_text]

    line_page_counts: Counter[str] = Counter()
    for lines in page_lines:
        line_page_counts.update(set(lines))  # set() -> counted once per page

    threshold = max(2, round(len(pages_text) * _BOILERPLATE_REPEAT_RATIO))
    boilerplate = {
        line for line, count in line_page_counts.items()
        if count >= threshold and len(line) <= _BOILERPLATE_MAX_LINE_LEN
    }

    if boilerplate:
        logger.info("Stripped %d repeated boilerplate line(s) from PDF", len(boilerplate))

    cleaned_pages = ["\n".join(line for line in lines if line not in boilerplate) for lines in page_lines]
    return "\n".join(cleaned_pages)


def extract_text_from_bytes(raw: bytes, filename: str) -> str:
    ext = _get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if ext == ".txt":
        text = raw.decode("utf-8", errors="ignore")
    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        total_pages = len(reader.pages)
        pages = reader.pages[:_PDF_PAGE_CAP]
        if total_pages > _PDF_PAGE_CAP:
            logger.info(
                "'%s' has %d pages; only reading the first %d",
                filename, total_pages, _PDF_PAGE_CAP,
            )
        pages_text = [page.extract_text() or "" for page in pages]
        text = _strip_pdf_boilerplate(pages_text)
    else:  # .docx
        import docx
        document = docx.Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in document.paragraphs)

    if len(text.strip()) < MIN_TEXT_LENGTH:
        raise EmptyExtractionError(
            f"Extracted only {len(text.strip())} chars from '{filename}' — "
            "likely a scanned/image-only file with no text layer."
        )
    return text


async def extract_text_from_upload(file: UploadFile) -> str:
    """Upload-time entry point — called synchronously from a route handler,
    so failures surface immediately as HTTP errors rather than being
    discovered later via a status field."""
    filename = file.filename or ""
    raw = await file.read()
    try:
        return extract_text_from_bytes(raw, filename)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except EmptyExtractionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))