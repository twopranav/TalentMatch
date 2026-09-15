"""
Text extraction for resume and JD files.

Supported:
- PDF
- DOCX
- TXT

The core function operates on bytes so it can be used both:
- during an HTTP upload
- later inside a Celery worker after the stored file is downloaded
"""

import io
import logging
import re
from collections import Counter

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".docx",
}

MIN_TEXT_LENGTH = 50

_PDF_PAGE_CAP = 3
_DOCX_CHAR_CAP = 20_000

_BOILERPLATE_MAX_LINE_LEN = 60
_BOILERPLATE_REPEAT_RATIO = 0.5


class UnsupportedFileTypeError(Exception):
    pass


class EmptyExtractionError(Exception):
    """
    Extraction technically succeeded but yielded too little text.

    Typical cause:
    - scanned/image-only PDF
    - damaged document
    - unsupported embedded text layer
    """

    pass


def _get_extension(filename: str) -> str:
    return (
        "." + filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )


def _clean_extracted_text(text: str) -> str:
    """
    Clean common PDF/DOCX extraction artifacts without trying to
    semantically rewrite the document.

    Deliberately conservative:
    we normalize known encoding artifacts but do not make broad
    replacements that could alter legitimate words.
    """
    replacements = {
        "(cid:127)": " ",
        "â†’": "→",
        "â€“": "–",
        "â€”": "—",
        "â€˜": "‘",
        "â€™": "’",
        "â€œ": "“",
        "â€": "”",
        "â€¢": "•",
        "\ufeff": "",
        "\u00a0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Collapse pathological horizontal whitespace without destroying
    # line boundaries.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _strip_pdf_boilerplate(pages_text: list[str]) -> str:
    """
    Remove short lines that repeat across most PDF pages.

    Useful for:
    - running headers
    - running footers
    - repeated page labels
    - repeated candidate-name banners
    """

    if len(pages_text) <= 1:
        return pages_text[0] if pages_text else ""

    page_lines = [
        [
            line.strip()
            for line in page.split("\n")
            if line.strip()
        ]
        for page in pages_text
    ]

    line_page_counts: Counter[str] = Counter()

    for lines in page_lines:
        line_page_counts.update(set(lines))

    threshold = max(
        2,
        round(len(pages_text) * _BOILERPLATE_REPEAT_RATIO),
    )

    boilerplate = {
        line
        for line, count in line_page_counts.items()
        if count >= threshold
        and len(line) <= _BOILERPLATE_MAX_LINE_LEN
    }

    if boilerplate:
        logger.info(
            "Stripped %d repeated PDF boilerplate line(s)",
            len(boilerplate),
        )

    cleaned_pages = [
        "\n".join(
            line
            for line in lines
            if line not in boilerplate
        )
        for lines in page_lines
    ]

    return "\n".join(cleaned_pages)


def extract_text_from_bytes(
    raw: bytes,
    filename: str,
) -> str:
    if not raw:
        raise EmptyExtractionError(
            f"File '{filename}' is empty."
        )

    ext = _get_extension(filename)

    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if ext == ".txt":
        text = raw.decode(
            "utf-8",
            errors="ignore",
        )

    elif ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(
            io.BytesIO(raw)
        )

        total_pages = len(reader.pages)

        pages = reader.pages[:_PDF_PAGE_CAP]

        if total_pages > _PDF_PAGE_CAP:
            logger.info(
                "'%s' has %d pages; only reading first %d",
                filename,
                total_pages,
                _PDF_PAGE_CAP,
            )

        pages_text = [
            page.extract_text() or ""
            for page in pages
        ]

        text = _strip_pdf_boilerplate(
            pages_text
        )

    else:
        import docx

        document = docx.Document(
            io.BytesIO(raw)
        )

        paragraph_text = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        text = "\n".join(paragraph_text)

        if len(text) > _DOCX_CHAR_CAP:
            logger.info(
                "'%s' extracted to %d chars; "
                "truncating to first %d",
                filename,
                len(text),
                _DOCX_CHAR_CAP,
            )

            text = text[:_DOCX_CHAR_CAP]

    text = _clean_extracted_text(text)

    if len(text.strip()) < MIN_TEXT_LENGTH:
        raise EmptyExtractionError(
            f"Extracted only {len(text.strip())} chars from "
            f"'{filename}' — likely a scanned/image-only file "
            "or otherwise unusable document."
        )

    return text


async def extract_text_from_upload(
    file: UploadFile,
) -> str:
    """
    Upload-time entry point.

    Converts parser-level failures into appropriate FastAPI errors.
    """

    filename = file.filename or ""

    raw = await file.read()

    try:
        return extract_text_from_bytes(
            raw,
            filename,
        )

    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except EmptyExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc