"""
Thin wrapper around Azure Blob Storage for resume files, mirroring why
jd_extract.py is its own module: routes never touch the Azure SDK directly,
so the storage backend can change later without touching route code.

Requires AZURE_STORAGE_CONNECTION_STRING and AZURE_STORAGE_CONTAINER to be
set (see app/core/config.py / .env.example) — both are placeholders until
real Azure credentials are supplied.
"""
import uuid
from datetime import datetime, timedelta, timezone
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    generate_blob_sas,
)
from app.core.config import settings

_DEFAULT_SAS_EXPIRY_MINUTES = 15


def _get_service_client() -> BlobServiceClient:
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is not set. Add real Azure "
            "credentials to .env before uploading resumes."
        )
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)


def _get_container_client():
    client = _get_service_client()
    return client.get_container_client(settings.AZURE_STORAGE_CONTAINER)


def build_blob_name(owner_id: uuid.UUID | None, original_filename: str) -> str:
    """Namespaced, collision-proof blob key. Prefixing with the owner id
    (or 'unowned' for recruiter-sourced files with no account yet) keeps a
    container browsable by candidate without needing a DB lookup, while the
    uuid4 segment guarantees two uploads of 'resume.pdf' never collide."""
    prefix = str(owner_id) if owner_id else "unowned"
    ext = ("." + original_filename.rsplit(".", 1)[-1]) if "." in original_filename else ""
    return f"{prefix}/{uuid.uuid4()}{ext}"


def upload_resume_blob(contents: bytes, blob_name: str, content_type: str) -> str:
    """Uploads raw bytes to the resumes container. Returns the blob_path to
    store on the Resume row (not a URL — see model docstring for why)."""
    container = _get_container_client()
    container.upload_blob(
        name=blob_name,
        data=contents,
        content_type=content_type,
        overwrite=False,  # blob_name always contains a fresh uuid4, so a
                           # collision here means something is wrong upstream
    )
    return blob_name


def delete_resume_blob(blob_path: str) -> None:
    """Best-effort delete. Missing blobs (e.g. re-running a cleanup job)
    are not an error — the end state (blob gone) is already satisfied."""
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_path)
    blob_client.delete_blob(delete_snapshots="include")


def get_resume_download_url(blob_path: str, expiry_minutes: int = _DEFAULT_SAS_EXPIRY_MINUTES) -> str:
    """Generates a time-limited, read-only SAS URL on demand rather than
    storing one — so a leaked DB row never leaks a permanent download link,
    and rotating the storage account key doesn't require touching any data."""
    service_client = _get_service_client()
    account_key = service_client.credential.account_key
    sas_token = generate_blob_sas(
        account_name=service_client.account_name,
        container_name=settings.AZURE_STORAGE_CONTAINER,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes),
    )
    blob_client = service_client.get_blob_client(
        container=settings.AZURE_STORAGE_CONTAINER, blob=blob_path
    )
    return f"{blob_client.url}?{sas_token}"
