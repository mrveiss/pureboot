# File Browser API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement File Browser API endpoints for browsing and managing files on storage backends.

**Architecture:** Extend storage service layer with file operations protocol, add file-specific schemas, create new routes under `/api/v1/storage/backends/{id}/files`. NFS gets full CRUD via filesystem ops, HTTP gets read-only via directory index parsing, S3 gets full implementation via S3-compatible API, iSCSI returns "not applicable" (block storage).

**Tech Stack:** FastAPI, aiohttp, pathlib, mimetypes, aiofiles (for async file I/O)

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-file-browser`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run pip install, pytest, python, or any execution commands. Only create/edit files and make git commits.

---

## Task 1: Add File Browser Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add file browser schemas**

Add after the `StorageTestResult` class at the end of the file:

```python
# ============== File Browser Schemas ==============


class StorageFile(BaseModel):
    """File or directory in storage backend."""
    name: str
    path: str
    type: str  # "file" or "directory"
    size: int | None = None
    mime_type: str | None = None
    modified_at: datetime | None = None
    item_count: int | None = None  # For directories


class FileListResponse(BaseModel):
    """Response for file listing."""
    path: str
    files: list[StorageFile]
    total: int


class FolderCreate(BaseModel):
    """Schema for creating a folder."""
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v or not v.startswith("/"):
            raise ValueError("Path must start with /")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v.rstrip("/") or "/"


class FileMove(BaseModel):
    """Schema for moving files."""
    source_path: str
    destination_path: str

    @field_validator("source_path", "destination_path")
    @classmethod
    def validate_paths(cls, v: str) -> str:
        if not v or not v.startswith("/"):
            raise ValueError("Path must start with /")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class FileDelete(BaseModel):
    """Schema for deleting files."""
    paths: list[str]

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, v: list[str]) -> list[str]:
        for path in v:
            if not path or not path.startswith("/"):
                raise ValueError(f"Path must start with /: {path}")
            if ".." in path:
                raise ValueError("Path traversal not allowed")
        return v
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add file browser schemas"
```

---

## Task 2: Create File Browser Service Protocol

**Files:**
- Modify: `src/core/storage.py`

**Step 1: Add file browser protocol and helper**

Add after the `StorageBackendService` protocol class:

```python
class FileInfo:
    """File information data class."""
    def __init__(
        self,
        name: str,
        path: str,
        file_type: str,
        size: int | None = None,
        mime_type: str | None = None,
        modified_at: datetime | None = None,
        item_count: int | None = None,
    ):
        self.name = name
        self.path = path
        self.type = file_type
        self.size = size
        self.mime_type = mime_type
        self.modified_at = modified_at
        self.item_count = item_count

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "size": self.size,
            "mime_type": self.mime_type,
            "modified_at": self.modified_at,
            "item_count": self.item_count,
        }


class FileBrowserService(Protocol):
    """Protocol for file browser operations."""

    async def list_files(self, path: str) -> list[FileInfo]:
        """List files at the given path."""
        ...

    async def download_file(self, path: str) -> tuple[AsyncIterator[bytes], str, int]:
        """Download file. Returns (content_iterator, mime_type, size)."""
        ...

    async def upload_file(self, path: str, filename: str, content: AsyncIterator[bytes]) -> FileInfo:
        """Upload file to the given path."""
        ...

    async def delete_files(self, paths: list[str]) -> int:
        """Delete files/folders. Returns count of deleted items."""
        ...

    async def create_folder(self, path: str) -> FileInfo:
        """Create a folder at the given path."""
        ...

    async def move_file(self, source: str, destination: str) -> FileInfo:
        """Move file from source to destination."""
        ...

    def supports_write(self) -> bool:
        """Return True if backend supports write operations."""
        ...
```

Also add import at top:
```python
from datetime import datetime
from typing import Protocol, AsyncIterator
import mimetypes
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): add file browser protocol"
```

---

## Task 3: Implement NFS File Browser

**Files:**
- Modify: `src/core/storage.py`

**Step 1: Add file browser methods to NfsBackendService**

Add these methods to the `NfsBackendService` class:

```python
    def supports_write(self) -> bool:
        return True

    def _validate_path(self, path: str) -> Path:
        """Validate and resolve path within mount point."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")
        clean_path = path.lstrip("/")
        full_path = self.mount_point / clean_path
        # Ensure path is within mount point
        try:
            full_path.resolve().relative_to(self.mount_point.resolve())
        except ValueError:
            raise ValueError("Path outside storage root")
        return full_path

    async def list_files(self, path: str) -> list[FileInfo]:
        """List files at the given path."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        target = self._validate_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        if not target.is_dir():
            raise ValueError(f"Not a directory: {path}")

        files = []
        for item in target.iterdir():
            stat = item.stat()
            rel_path = "/" + str(item.relative_to(self.mount_point))

            if item.is_dir():
                item_count = sum(1 for _ in item.iterdir())
                files.append(FileInfo(
                    name=item.name,
                    path=rel_path,
                    file_type="directory",
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    item_count=item_count,
                ))
            else:
                mime_type, _ = mimetypes.guess_type(item.name)
                files.append(FileInfo(
                    name=item.name,
                    path=rel_path,
                    file_type="file",
                    size=stat.st_size,
                    mime_type=mime_type,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                ))

        return sorted(files, key=lambda f: (f.type != "directory", f.name.lower()))

    async def download_file(self, path: str) -> tuple[AsyncIterator[bytes], str, int]:
        """Download file."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        target = self._validate_path(path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not target.is_file():
            raise ValueError(f"Not a file: {path}")

        mime_type, _ = mimetypes.guess_type(target.name)
        size = target.stat().st_size

        async def file_iterator():
            with open(target, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        return file_iterator(), mime_type or "application/octet-stream", size

    async def upload_file(self, path: str, filename: str, content: AsyncIterator[bytes]) -> FileInfo:
        """Upload file."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        target_dir = self._validate_path(path)
        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        # Validate filename
        if "/" in filename or ".." in filename:
            raise ValueError("Invalid filename")

        target_file = target_dir / filename

        with open(target_file, "wb") as f:
            async for chunk in content:
                f.write(chunk)

        stat = target_file.stat()
        mime_type, _ = mimetypes.guess_type(filename)
        rel_path = "/" + str(target_file.relative_to(self.mount_point))

        return FileInfo(
            name=filename,
            path=rel_path,
            file_type="file",
            size=stat.st_size,
            mime_type=mime_type,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )

    async def delete_files(self, paths: list[str]) -> int:
        """Delete files/folders recursively."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        deleted = 0
        for path in paths:
            target = self._validate_path(path)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                deleted += 1

        return deleted

    async def create_folder(self, path: str) -> FileInfo:
        """Create a folder."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        target = self._validate_path(path)
        if target.exists():
            raise ValueError(f"Path already exists: {path}")

        target.mkdir(parents=True)
        stat = target.stat()

        return FileInfo(
            name=target.name,
            path=path,
            file_type="directory",
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            item_count=0,
        )

    async def move_file(self, source: str, destination: str) -> FileInfo:
        """Move file or folder."""
        if not os.path.ismount(str(self.mount_point)):
            await self.mount()

        src = self._validate_path(source)
        dst = self._validate_path(destination)

        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        if dst.exists():
            raise ValueError(f"Destination already exists: {destination}")

        shutil.move(str(src), str(dst))
        stat = dst.stat()

        if dst.is_dir():
            item_count = sum(1 for _ in dst.iterdir())
            return FileInfo(
                name=dst.name,
                path=destination,
                file_type="directory",
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                item_count=item_count,
            )
        else:
            mime_type, _ = mimetypes.guess_type(dst.name)
            return FileInfo(
                name=dst.name,
                path=destination,
                file_type="file",
                size=stat.st_size,
                mime_type=mime_type,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): implement NFS file browser operations"
```

---

## Task 4: Implement HTTP File Browser (Read-Only)

**Files:**
- Modify: `src/core/storage.py`

**Step 1: Add file browser methods to HttpBackendService**

Add these methods to the `HttpBackendService` class:

```python
    def supports_write(self) -> bool:
        return False

    async def list_files(self, path: str) -> list[FileInfo]:
        """List files by parsing HTTP directory index."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        url = f"{self.base_url}{path}"
        if not url.endswith("/"):
            url += "/"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 404:
                        raise FileNotFoundError(f"Path not found: {path}")
                    if resp.status >= 400:
                        raise ValueError(f"HTTP error: {resp.status}")

                    html = await resp.text()
                    return self._parse_directory_listing(html, path)
        except aiohttp.ClientError as e:
            raise ValueError(f"HTTP request failed: {str(e)}")

    def _parse_directory_listing(self, html: str, base_path: str) -> list[FileInfo]:
        """Parse Apache/nginx style directory listing."""
        import re
        files = []

        # Match common directory listing patterns
        # Apache: <a href="filename">filename</a>
        # nginx: <a href="filename">filename</a>  date  size
        pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>(?:\s*</td><td[^>]*>([^<]*)</td><td[^>]*>([^<]*)</td>)?'

        for match in re.finditer(pattern, html, re.IGNORECASE):
            href = match.group(1)
            name = match.group(2).strip()

            # Skip parent directory and special links
            if name in ("../", "..", "Parent Directory", "Name", ""):
                continue
            if href.startswith("?") or href.startswith("/"):
                continue

            # Determine if directory
            is_dir = href.endswith("/")
            clean_name = name.rstrip("/")

            # Build path
            if base_path == "/":
                file_path = f"/{clean_name}"
            else:
                file_path = f"{base_path.rstrip('/')}/{clean_name}"

            if is_dir:
                files.append(FileInfo(
                    name=clean_name,
                    path=file_path,
                    file_type="directory",
                ))
            else:
                mime_type, _ = mimetypes.guess_type(clean_name)
                files.append(FileInfo(
                    name=clean_name,
                    path=file_path,
                    file_type="file",
                    mime_type=mime_type,
                ))

        return sorted(files, key=lambda f: (f.type != "directory", f.name.lower()))

    async def download_file(self, path: str) -> tuple[AsyncIterator[bytes], str, int]:
        """Download file from HTTP backend."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        url = f"{self.base_url}{path}"

        try:
            session = aiohttp.ClientSession()
            resp = await session.get(
                url,
                auth=self._get_auth(),
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=300),
            )

            if resp.status == 404:
                await session.close()
                raise FileNotFoundError(f"File not found: {path}")
            if resp.status >= 400:
                await session.close()
                raise ValueError(f"HTTP error: {resp.status}")

            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content_length = int(resp.headers.get("Content-Length", 0))

            async def content_iterator():
                try:
                    async for chunk in resp.content.iter_chunked(8192):
                        yield chunk
                finally:
                    await resp.release()
                    await session.close()

            return content_iterator(), content_type, content_length
        except aiohttp.ClientError as e:
            raise ValueError(f"HTTP download failed: {str(e)}")

    async def upload_file(self, path: str, filename: str, content: AsyncIterator[bytes]) -> FileInfo:
        """HTTP backends are read-only."""
        raise ValueError("HTTP backends are read-only")

    async def delete_files(self, paths: list[str]) -> int:
        """HTTP backends are read-only."""
        raise ValueError("HTTP backends are read-only")

    async def create_folder(self, path: str) -> FileInfo:
        """HTTP backends are read-only."""
        raise ValueError("HTTP backends are read-only")

    async def move_file(self, source: str, destination: str) -> FileInfo:
        """HTTP backends are read-only."""
        raise ValueError("HTTP backends are read-only")
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): implement HTTP file browser (read-only)"
```

---

## Task 5: Implement S3 File Browser

**Files:**
- Modify: `src/core/storage.py`

**Step 1: Add file browser methods to S3BackendService**

Add these methods to the `S3BackendService` class:

```python
    def supports_write(self) -> bool:
        return True

    def _get_s3_client_params(self) -> tuple[str, dict]:
        """Get S3 endpoint URL and auth headers."""
        endpoint = self.config["endpoint"]
        bucket = self.config["bucket"]
        access_key = self.config.get("access_key_id", "")
        secret_key = self.config.get("secret_access_key", "")
        region = self.config.get("region", "us-east-1")

        # For S3-compatible APIs, we use basic auth or AWS signature
        # This is a simplified implementation
        return endpoint, bucket, access_key, secret_key, region

    async def list_files(self, path: str) -> list[FileInfo]:
        """List files in S3 bucket."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()
        prefix = path.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        if prefix == "/":
            prefix = ""

        url = f"{endpoint}/{bucket}?list-type=2&prefix={prefix}&delimiter=/"

        try:
            async with aiohttp.ClientSession() as session:
                # Simple unsigned request for public buckets
                # For authenticated access, AWS signature v4 would be needed
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status >= 400:
                        raise ValueError(f"S3 error: {resp.status}")

                    xml_content = await resp.text()
                    return self._parse_s3_listing(xml_content, path)
        except aiohttp.ClientError as e:
            raise ValueError(f"S3 request failed: {str(e)}")

    def _parse_s3_listing(self, xml_content: str, base_path: str) -> list[FileInfo]:
        """Parse S3 ListObjectsV2 XML response."""
        import re
        files = []

        # Parse common prefixes (directories)
        for match in re.finditer(r'<CommonPrefixes><Prefix>([^<]+)</Prefix></CommonPrefixes>', xml_content):
            prefix = match.group(1)
            name = prefix.rstrip("/").split("/")[-1]
            if name:
                files.append(FileInfo(
                    name=name,
                    path=f"/{prefix.rstrip('/')}",
                    file_type="directory",
                ))

        # Parse contents (files)
        for match in re.finditer(r'<Contents>.*?<Key>([^<]+)</Key>.*?<Size>([^<]+)</Size>.*?<LastModified>([^<]+)</LastModified>.*?</Contents>', xml_content, re.DOTALL):
            key = match.group(1)
            size = int(match.group(2))
            modified = match.group(3)

            # Skip directory markers
            if key.endswith("/"):
                continue

            name = key.split("/")[-1]
            mime_type, _ = mimetypes.guess_type(name)

            files.append(FileInfo(
                name=name,
                path=f"/{key}",
                file_type="file",
                size=size,
                mime_type=mime_type,
            ))

        return sorted(files, key=lambda f: (f.type != "directory", f.name.lower()))

    async def download_file(self, path: str) -> tuple[AsyncIterator[bytes], str, int]:
        """Download file from S3."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()
        key = path.lstrip("/")
        url = f"{endpoint}/{bucket}/{key}"

        try:
            session = aiohttp.ClientSession()
            resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=300))

            if resp.status == 404:
                await session.close()
                raise FileNotFoundError(f"File not found: {path}")
            if resp.status >= 400:
                await session.close()
                raise ValueError(f"S3 error: {resp.status}")

            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content_length = int(resp.headers.get("Content-Length", 0))

            async def content_iterator():
                try:
                    async for chunk in resp.content.iter_chunked(8192):
                        yield chunk
                finally:
                    await resp.release()
                    await session.close()

            return content_iterator(), content_type, content_length
        except aiohttp.ClientError as e:
            raise ValueError(f"S3 download failed: {str(e)}")

    async def upload_file(self, path: str, filename: str, content: AsyncIterator[bytes]) -> FileInfo:
        """Upload file to S3."""
        if ".." in path or ".." in filename:
            raise ValueError("Path traversal not allowed")

        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()

        # Build key
        base = path.lstrip("/").rstrip("/")
        key = f"{base}/{filename}" if base else filename
        url = f"{endpoint}/{bucket}/{key}"

        # Collect content
        data = b""
        async for chunk in content:
            data += chunk

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status >= 400:
                        raise ValueError(f"S3 upload error: {resp.status}")
        except aiohttp.ClientError as e:
            raise ValueError(f"S3 upload failed: {str(e)}")

        mime_type, _ = mimetypes.guess_type(filename)
        return FileInfo(
            name=filename,
            path=f"/{key}",
            file_type="file",
            size=len(data),
            mime_type=mime_type,
        )

    async def delete_files(self, paths: list[str]) -> int:
        """Delete files from S3."""
        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()
        deleted = 0

        for path in paths:
            if ".." in path:
                continue
            key = path.lstrip("/")
            url = f"{endpoint}/{bucket}/{key}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.delete(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status < 400:
                            deleted += 1
            except aiohttp.ClientError:
                pass

        return deleted

    async def create_folder(self, path: str) -> FileInfo:
        """Create folder in S3 (creates empty object with trailing /)."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()
        key = path.lstrip("/").rstrip("/") + "/"
        url = f"{endpoint}/{bucket}/{key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    data=b"",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status >= 400:
                        raise ValueError(f"S3 create folder error: {resp.status}")
        except aiohttp.ClientError as e:
            raise ValueError(f"S3 create folder failed: {str(e)}")

        name = path.rstrip("/").split("/")[-1]
        return FileInfo(
            name=name,
            path=path,
            file_type="directory",
            item_count=0,
        )

    async def move_file(self, source: str, destination: str) -> FileInfo:
        """Move file in S3 (copy + delete)."""
        if ".." in source or ".." in destination:
            raise ValueError("Path traversal not allowed")

        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()

        src_key = source.lstrip("/")
        dst_key = destination.lstrip("/")

        # Copy
        copy_url = f"{endpoint}/{bucket}/{dst_key}"
        copy_source = f"/{bucket}/{src_key}"

        try:
            async with aiohttp.ClientSession() as session:
                # Copy object
                async with session.put(
                    copy_url,
                    headers={"x-amz-copy-source": copy_source},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status >= 400:
                        raise ValueError(f"S3 copy error: {resp.status}")

                # Delete source
                delete_url = f"{endpoint}/{bucket}/{src_key}"
                await session.delete(delete_url, timeout=aiohttp.ClientTimeout(total=30))
        except aiohttp.ClientError as e:
            raise ValueError(f"S3 move failed: {str(e)}")

        name = destination.rstrip("/").split("/")[-1]
        mime_type, _ = mimetypes.guess_type(name)
        return FileInfo(
            name=name,
            path=destination,
            file_type="file",
            mime_type=mime_type,
        )
```

Also update the test_connection method:

```python
    async def test_connection(self) -> tuple[bool, str]:
        """Test S3 connectivity."""
        endpoint, bucket, access_key, secret_key, region = self._get_s3_client_params()
        url = f"{endpoint}/{bucket}?list-type=2&max-keys=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status < 400:
                        return True, f"S3 bucket accessible"
                    return False, f"S3 error: {resp.status}"
        except aiohttp.ClientError as e:
            return False, f"S3 connection failed: {str(e)}"
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): implement S3 file browser operations"
```

---

## Task 6: Implement iSCSI File Browser (Not Applicable)

**Files:**
- Modify: `src/core/storage.py`

**Step 1: Add file browser methods to IscsiBackendService**

Add these methods to return "not applicable" errors:

```python
    def supports_write(self) -> bool:
        return False

    async def list_files(self, path: str) -> list[FileInfo]:
        raise ValueError("iSCSI is block storage - file browsing not applicable")

    async def download_file(self, path: str) -> tuple[AsyncIterator[bytes], str, int]:
        raise ValueError("iSCSI is block storage - file operations not applicable")

    async def upload_file(self, path: str, filename: str, content: AsyncIterator[bytes]) -> FileInfo:
        raise ValueError("iSCSI is block storage - file operations not applicable")

    async def delete_files(self, paths: list[str]) -> int:
        raise ValueError("iSCSI is block storage - file operations not applicable")

    async def create_folder(self, path: str) -> FileInfo:
        raise ValueError("iSCSI is block storage - file operations not applicable")

    async def move_file(self, source: str, destination: str) -> FileInfo:
        raise ValueError("iSCSI is block storage - file operations not applicable")
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): add iSCSI file browser stubs (not applicable)"
```

---

## Task 7: Create File Browser Routes

**Files:**
- Create: `src/api/routes/files.py`

**Step 1: Create file browser router**

```python
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
```

**Step 2: Commit**

```bash
git add src/api/routes/files.py
git commit -m "feat(api): add file browser routes"
```

---

## Task 8: Register File Browser Router

**Files:**
- Modify: `src/main.py`

**Step 1: Update imports and register router**

Add to imports:
```python
from src.api.routes import boot, ipxe, nodes, groups, storage, files
```

Add router registration after storage router:
```python
app.include_router(files.router, prefix="/api/v1", tags=["files"])
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat(api): register file browser router"
```

---

## Task 9: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feature/file-browser
```

**Step 2: Create PR**

Create PR referencing issue #15.

---

## Summary

**Files created:**
- `src/api/routes/files.py` - File browser endpoints

**Files modified:**
- `src/api/schemas.py` - Added file browser schemas
- `src/core/storage.py` - Added file browser protocol and implementations for all backends
- `src/main.py` - Registered file browser router

**Endpoints implemented:**
- `GET /api/v1/storage/backends/{id}/files` - List files
- `GET /api/v1/storage/backends/{id}/files/download` - Download file
- `POST /api/v1/storage/backends/{id}/files` - Upload file
- `DELETE /api/v1/storage/backends/{id}/files` - Delete files
- `POST /api/v1/storage/backends/{id}/folders` - Create folder
- `POST /api/v1/storage/backends/{id}/files/move` - Move file

**Backend support:**
- NFS - Full CRUD (list, download, upload, delete, create folder, move)
- HTTP - Read-only (list, download)
- S3 - Full CRUD (list, download, upload, delete, create folder, move)
- iSCSI - Not applicable (block storage)
