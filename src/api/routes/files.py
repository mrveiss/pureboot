"""File browser API endpoints."""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiResponse,
    FileListResponse,
    FolderCreate,
    FileMove,
    FileDelete,
    StorageFile,
)
from src.core.storage import get_backend_service
from src.db.database import get_db
from src.db.models import FileChecksum, StorageBackend

router = APIRouter()


async def get_backend_and_service(backend_id: str, db: AsyncSession):
    """Helper to get backend and its file service."""
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")

    config = json.loads(backend.config_json)
    service = get_backend_service(backend.id, backend.type, config)

    return backend, service


@router.get("/storage/backends/{backend_id}/files", response_model=ApiResponse[FileListResponse])
async def list_files(
    backend_id: str,
    path: str = Query(default="/", description="Directory path to list"),
    db: AsyncSession = Depends(get_db),
):
    """List files in a storage backend directory."""
    backend, service = await get_backend_and_service(backend_id, db)

    try:
        files = await service.list_files(path)
        file_list = [
            StorageFile(
                name=f.name,
                path=f.path,
                type=f.type,
                size=f.size,
                mime_type=f.mime_type,
                modified_at=f.modified_at,
                item_count=f.item_count,
            )
            for f in files
        ]

        return ApiResponse(
            data=FileListResponse(
                path=path,
                files=file_list,
                total=len(file_list),
            )
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/storage/backends/{backend_id}/files/download")
async def download_file(
    backend_id: str,
    path: str = Query(..., description="File path to download"),
    db: AsyncSession = Depends(get_db),
):
    """Download a file from storage backend."""
    backend, service = await get_backend_and_service(backend_id, db)

    try:
        content_iterator, mime_type, size = await service.download_file(path)

        filename = path.split("/")[-1]
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if size > 0:
            headers["Content-Length"] = str(size)

        return StreamingResponse(
            content_iterator,
            media_type=mime_type,
            headers=headers,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/storage/backends/{backend_id}/files", response_model=ApiResponse[StorageFile])
async def upload_file(
    backend_id: str,
    path: str = Query(default="/", description="Directory path to upload to"),
    file: UploadFile = File(...),
    expected_checksum: str | None = Header(
        default=None,
        alias="X-Expected-Checksum-SHA256",
        description="Expected SHA256 checksum for verification",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file to storage backend.

    Computes SHA256 checksum during upload and stores it for later retrieval.
    If X-Expected-Checksum-SHA256 header is provided, verifies the checksum
    matches (returns 422 on mismatch).
    """
    backend, service = await get_backend_and_service(backend_id, db)

    if not service.supports_write():
        raise HTTPException(status_code=400, detail="Backend is read-only")

    try:
        # Read entire file content to compute checksum
        content = await file.read()
        computed_checksum = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # Verify checksum if expected
        if expected_checksum and computed_checksum != expected_checksum.lower():
            raise HTTPException(
                status_code=422,
                detail=f"Checksum mismatch: expected {expected_checksum}, got {computed_checksum}",
            )

        # Create iterator from content for upload
        async def content_iterator():
            chunk_size = 8192
            for i in range(0, len(content), chunk_size):
                yield content[i : i + chunk_size]

        result = await service.upload_file(path, file.filename, content_iterator())

        # Normalize file path for checksum storage
        file_path = path.rstrip("/") + "/" + file.filename
        if not file_path.startswith("/"):
            file_path = "/" + file_path

        # Store/update checksum record
        checksum_result = await db.execute(
            select(FileChecksum).where(
                FileChecksum.backend_id == backend_id,
                FileChecksum.file_path == file_path,
            )
        )
        checksum_record = checksum_result.scalar_one_or_none()

        if checksum_record:
            checksum_record.checksum_sha256 = computed_checksum
            checksum_record.size_bytes = file_size
        else:
            checksum_record = FileChecksum(
                backend_id=backend_id,
                file_path=file_path,
                checksum_sha256=computed_checksum,
                size_bytes=file_size,
            )
            db.add(checksum_record)

        await db.commit()

        return ApiResponse(
            data=StorageFile(
                name=result.name,
                path=result.path,
                type=result.type,
                size=result.size,
                mime_type=result.mime_type,
                modified_at=result.modified_at,
                item_count=result.item_count,
                checksum_sha256=computed_checksum,
            ),
            message="File uploaded successfully",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/storage/backends/{backend_id}/files", response_model=ApiResponse[dict])
async def delete_files(
    backend_id: str,
    body: FileDelete,
    db: AsyncSession = Depends(get_db),
):
    """Delete files from storage backend."""
    backend, service = await get_backend_and_service(backend_id, db)

    if not service.supports_write():
        raise HTTPException(status_code=400, detail="Backend is read-only")

    try:
        deleted = await service.delete_files(body.paths)

        return ApiResponse(
            data={"deleted": deleted},
            message=f"Deleted {deleted} item(s)",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/storage/backends/{backend_id}/files/delete", response_model=ApiResponse[dict])
async def delete_files_post(
    backend_id: str,
    body: FileDelete,
    db: AsyncSession = Depends(get_db),
):
    """Delete files - POST variant for bulk operations."""
    return await delete_files(backend_id, body, db)


@router.post("/storage/backends/{backend_id}/folders", response_model=ApiResponse[StorageFile])
async def create_folder(
    backend_id: str,
    body: FolderCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a folder in storage backend."""
    backend, service = await get_backend_and_service(backend_id, db)

    if not service.supports_write():
        raise HTTPException(status_code=400, detail="Backend is read-only")

    try:
        result = await service.create_folder(body.path)

        return ApiResponse(
            data=StorageFile(
                name=result.name,
                path=result.path,
                type=result.type,
                size=result.size,
                mime_type=result.mime_type,
                modified_at=result.modified_at,
                item_count=result.item_count,
            ),
            message="Folder created successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/storage/backends/{backend_id}/files/move", response_model=ApiResponse[StorageFile])
async def move_file(
    backend_id: str,
    body: FileMove,
    db: AsyncSession = Depends(get_db),
):
    """Move a file in storage backend."""
    backend, service = await get_backend_and_service(backend_id, db)

    if not service.supports_write():
        raise HTTPException(status_code=400, detail="Backend is read-only")

    try:
        result = await service.move_file(body.source_path, body.destination_path)

        return ApiResponse(
            data=StorageFile(
                name=result.name,
                path=result.path,
                type=result.type,
                size=result.size,
                mime_type=result.mime_type,
                modified_at=result.modified_at,
                item_count=result.item_count,
            ),
            message="File moved successfully",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
