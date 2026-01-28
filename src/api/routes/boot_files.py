"""Boot files serving endpoint with checksums and throttling."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.storage import get_backend_service
from src.core.system_settings import get_default_boot_backend_id
from src.db.database import get_db
from src.db.models import FileChecksum, StorageBackend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["boot-files"])


async def get_default_backend(db: AsyncSession) -> tuple[StorageBackend, object]:
    """Get the default boot backend and its service."""
    backend_id = await get_default_boot_backend_id(db)
    if not backend_id:
        raise HTTPException(
            status_code=503,
            detail="No default boot backend configured. Set default_boot_backend_id in system settings.",
        )

    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(
            status_code=503,
            detail=f"Default boot backend '{backend_id}' not found.",
        )

    config = json.loads(backend.config_json)
    service = get_backend_service(backend.id, backend.type, config)

    return backend, service


async def get_file_checksum(
    db: AsyncSession, backend_id: str, file_path: str
) -> str | None:
    """Look up checksum for a file."""
    result = await db.execute(
        select(FileChecksum).where(
            FileChecksum.backend_id == backend_id,
            FileChecksum.file_path == file_path,
        )
    )
    checksum_record = result.scalar_one_or_none()
    return checksum_record.checksum_sha256 if checksum_record else None


@router.get("/{path:path}")
async def serve_boot_file(
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Serve a file from the default boot backend.

    This endpoint serves files for PXE boot operations (kernels, initrds, etc.)
    from the configured default boot storage backend.

    Returns:
        StreamingResponse with checksum headers:
        - ETag: "sha256:<checksum>"
        - X-Checksum-SHA256: <checksum>
    """
    # Normalize path
    file_path = "/" + path.lstrip("/")

    backend, service = await get_default_backend(db)

    try:
        content_iterator, mime_type, size = await service.download_file(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Look up checksum
    checksum = await get_file_checksum(db, backend.id, file_path)

    # Build response headers
    headers = {}
    if size > 0:
        headers["Content-Length"] = str(size)

    if checksum:
        headers["ETag"] = f'"sha256:{checksum}"'
        headers["X-Checksum-SHA256"] = checksum

    filename = file_path.split("/")[-1]
    headers["Content-Disposition"] = f'inline; filename="{filename}"'

    logger.debug(f"Serving boot file: {file_path} (checksum: {checksum or 'unknown'})")

    return StreamingResponse(
        content_iterator,
        media_type=mime_type,
        headers=headers,
    )
