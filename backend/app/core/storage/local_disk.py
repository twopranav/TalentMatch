"""
Local filesystem storage backend for resume files. Mirrors azure_blob.py's
interface exactly (upload_blob, delete_blob, download_url) so resume_storage.py
can swap between them via STORAGE_BACKEND with no other code changes.

Files land under settings.LOCAL_STORAGE_ROOT, gitignored, namespaced by the
same owner_id/uuid scheme build_blob_name() uses for Azure.
"""
from pathlib import Path

from app.core.config import settings


def _root() -> Path:
    root = Path(settings.LOCAL_STORAGE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_blob(contents: bytes, blob_name: str, content_type: str) -> str:
    """content_type is accepted for interface parity with azure_blob.py but
    unused here — local disk doesn't track content-type metadata itself;
    it's re-derived from the Resume row's content_type column on read."""
    path = _root() / blob_name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Mirrors azure_blob.py's overwrite=False: blob_name always carries
        # a fresh uuid4, so an existing file here means something upstream
        # is wrong, not a legitimate overwrite.
        raise FileExistsError(f"Blob already exists at {blob_name}")
    path.write_bytes(contents)
    return blob_name


def delete_blob(blob_path: str) -> None:
    """Best-effort delete — matches azure_blob.py: a missing file is not
    an error, the end state (file gone) is already satisfied."""
    path = _root() / blob_path
    path.unlink(missing_ok=True)


def read_blob(blob_path: str) -> bytes:
    return (_root() / blob_path).read_bytes()

def download_url(blob_path: str, expiry_minutes: int | None = None) -> str:
    """No native 'signed URL' concept on local disk, so this returns a path
    to your own download route instead — resumes.py's get_resume()
    plugs this straight into ResumeReadWithUrl.download_url unchanged.
    expiry_minutes is accepted for interface parity but ignored."""
    return f"/api/resumes/{blob_path.split('/')[-1]}/file"