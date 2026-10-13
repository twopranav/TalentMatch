"""
Thin wrapper around Azure Blob Storage for resume files, mirroring why
jd_extract.py is its own module: routes never touch the Azure SDK directly,
so the storage backend can change later without touching route code.

Requires AZURE_STORAGE_SAS_URL to be set (see app/core/config.py /
.env.example) — a container-scoped SAS URL, not an account connection
string, so there is no account key available for minting fresh per-download
tokens (see download_url()).
"""
from azure.storage.blob import ContainerClient
from app.core.config import settings

def _get_container_client() -> ContainerClient:
    if not settings.AZURE_STORAGE_SAS_URL:
        raise RuntimeError(
            "AZURE_STORAGE_SAS_URL is not set. Add the real SAS URL to "
            ".env before uploading resumes."
        )
    return ContainerClient.from_container_url(settings.AZURE_STORAGE_SAS_URL)

def upload_blob(contents: bytes, blob_name: str, content_type: str) -> str:
    """Uploads raw bytes to the resumes container. Returns the blob_path to
    store on the Resume row (not a URL — see model docstring for why).
    Requires the SAS URL's permission string (sp=) to include write (w)."""
    container = _get_container_client()
    container.upload_blob(
        name=blob_name,
        data=contents,
        content_type=content_type,
        overwrite=False,  # blob_name always contains a fresh uuid4, so a
                           # collision here means something is wrong upstream
    )
    return blob_name

def delete_blob(blob_path: str) -> None:
    """Best-effort delete. Missing blobs (e.g. re-running a cleanup job)
    are not an error. Requires the SAS URL's permission string to include
    delete (d)."""
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_path)
    blob_client.delete_blob(delete_snapshots="include")

def download_blob(blob_path: str) -> bytes:
    """Fetches the raw bytes for a stored resume/JD file. Needed for the
    Phase 4 extraction worker, which runs in a separate Celery process
    with no request/UploadFile to read from — it has only whatever's on
    the Resume/Job row (blob_path), so it has to pull bytes itself rather
    than being handed them."""
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_path)
    return blob_client.download_blob().readall()

def download_url(blob_path: str, expiry_minutes: int | None = None) -> str:
    """Reuses the existing container-scoped SAS token rather than minting a
    fresh one — a SAS URL (vs. a connection string + account key) carries
    no account key, so generate_blob_sas() isn't available here. This means
    every download link has whatever expiry the original SAS was signed
    with, not a tight per-download window; expiry_minutes is accepted for
    interface parity with the account-key version but has no effect.
    If per-download expiry matters, proxy downloads through your own API
    route instead of calling this directly from the frontend."""
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_path)
    sas_query = settings.AZURE_STORAGE_SAS_URL.split("?", 1)[1]
    return f"{blob_client.url}?{sas_query}"