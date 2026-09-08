"""
Storage backend facade. routes/resumes.py imports from here only — never
from storage.azure_blob or storage.local_disk directly — so swapping
STORAGE_BACKEND is a config change, not a code change.
"""
import uuid

from app.core.config import settings

if settings.STORAGE_BACKEND == "azure":
    from app.core.storage.azure_blob import (
        delete_blob as delete_resume_blob,
        download_url as get_resume_download_url,
        upload_blob as upload_resume_blob,
    )
else:
    from app.core.storage.local_disk import (
        delete_blob as delete_resume_blob,
        download_url as get_resume_download_url,
        upload_blob as upload_resume_blob,
    )


def build_blob_name(owner_id: uuid.UUID | None, original_filename: str) -> str:
    """Namespaced, collision-proof blob key. Prefixing with the owner id
    (or 'unowned' for recruiter-sourced files with no account yet) keeps a
    container browsable by candidate without needing a DB lookup, while the
    uuid4 segment guarantees two uploads of 'resume.pdf' never collide.
    Same scheme regardless of which backend is active."""
    prefix = str(owner_id) if owner_id else "unowned"
    ext = ("." + original_filename.rsplit(".", 1)[-1]) if "." in original_filename else ""
    return f"{prefix}/{uuid.uuid4()}{ext}"