"""Upload hardening helpers shared by resumes, JDs and avatars."""
import io
import re
import zipfile
from urllib.parse import quote

from fastapi import HTTPException, UploadFile, status

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"

# The stored extension comes from the *verified* content type, never from
# the client-supplied filename.
_EXT_BY_TYPE = {PDF: ".pdf", DOCX: ".docx", PNG: ".png", JPEG: ".jpg", WEBP: ".webp"}
_SAFE_EXT = re.compile(r"^\.[a-z0-9]{1,5}$")
_MAX_DOCX_UNCOMPRESSED = 100 * 1024 * 1024  # zip-bomb guard


async def read_capped(file: UploadFile, limit: int, what: str = "File") -> bytes:
    """Reads at most limit+1 bytes, so an oversized upload is rejected
    without ever being pulled fully into memory."""
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{what} must be under {limit // (1024 * 1024)} MB.",
        )
    return data


def _valid_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                return False
            return sum(i.file_size for i in zf.infolist()) <= _MAX_DOCX_UNCOMPRESSED
    except zipfile.BadZipFile:
        return False


def check_magic(content_type: str, data: bytes) -> None:
    """Confirms the bytes really are what the Content-Type header claims."""
    if content_type == PDF:
        ok = b"%PDF-" in data[:1024]
    elif content_type == DOCX:
        ok = _valid_docx(data)
    elif content_type == PNG:
        ok = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == JPEG:
        ok = data.startswith(b"\xff\xd8\xff")
    elif content_type == WEBP:
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        ok = False
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File contents do not match its declared type.",
        )


def safe_extension(original_filename: str | None, content_type: str | None) -> str:
    if content_type in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[content_type]
    name = original_filename or ""
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    return ext if _SAFE_EXT.match(ext) and ext in set(_EXT_BY_TYPE.values()) else ""


def content_disposition(filename: str | None, disposition: str = "inline") -> str:
    """RFC 6266/5987 header: quotes and CR/LF can't break out of the value."""
    name = (filename or "file").replace("\r", "").replace("\n", "")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "file"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"