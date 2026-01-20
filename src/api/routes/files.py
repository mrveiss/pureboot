"""File browser API endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
from src.db.models import StorageBackend

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
    db: AsyncSession = Depends(get_db),
):
    """Upload a file to storage backend."""
    backend, service = await get_backend_and_service(backend_id, db)

    if not service.supports_write():
        raise HTTPException(status_code=400, detail="Backend is read-only")

    try:
        async def content_iterator():
            while chunk := await file.read(8192):
                yield chunk

        result = await service.upload_file(path, file.filename, content_iterator())

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
