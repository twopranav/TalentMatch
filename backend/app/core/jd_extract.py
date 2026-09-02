"""
Extracts raw text from an uploaded JD file. Phase 2 scope only: get words
into Job.jd_raw_text. Structured requirement extraction is Phase 4.
"""
import io
from fastapi import HTTPException, UploadFile, status


ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}

async def extract_text_from_upload(file: UploadFile) -> str:
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    raw = await file.read()

    if ext == ".txt":
        return raw.decode("utf-8", errors="ignore")

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    # .docx
    import docx
    document = docx.Document(io.BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs)