"""
Extracts raw text from a resume or JD file (PDF, DOCX, TXT).

Core logic (extract_text_from_bytes) works on raw bytes, not UploadFile,
so it can run both at upload time (from a FastAPI UploadFile, via
extract_text_from_upload) and inside a Celery worker (from bytes fetched
off blob storage, where there's no UploadFile / request context at all).
"""
import io
from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MIN_TEXT_LENGTH = 50  # chars; below this, treat extraction as failed rather
                       # than silently handing an LLM step ~nothing to work with


class UnsupportedFileTypeError(Exception):
    pass


class EmptyExtractionError(Exception):
    """Mechanically succeeded but yielded ~no text — e.g. a scanned/
    image-only PDF with no embedded text layer."""
    pass


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


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
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
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