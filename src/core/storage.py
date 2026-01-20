"""Storage backend service layer."""
import asyncio
import json
import logging
import mimetypes
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Protocol

import aiohttp

logger = logging.getLogger(__name__)


class StorageBackendService(Protocol):
    """Protocol for storage backend operations."""

    async def test_connection(self) -> tuple[bool, str]:
        """Test connection to the backend. Returns (success, message)."""
        ...

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        ...

    async def mount(self) -> str | None:
        """Mount the backend (if applicable). Returns mount point."""
        ...

    async def unmount(self) -> None:
        """Unmount the backend (if applicable)."""
        ...


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


class NfsBackendService:
    """NFS backend operations."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.server = config["server"]
        self.export_path = config["export_path"]
        self.mount_options = config.get("mount_options", "vers=4.1")
        self._mount_base = Path("/tmp/pureboot/nfs")

    @property
    def mount_point(self) -> Path:
        return self._mount_base / self.backend_id

    async def test_connection(self) -> tuple[bool, str]:
        """Test NFS connectivity using showmount."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "showmount", "-e", self.server,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                return False, "Connection test timed out"

            if proc.returncode != 0:
                return False, f"Cannot reach NFS server: {stderr.decode().strip()}"

            exports = stdout.decode()
            if self.export_path not in exports:
                return False, f"Export {self.export_path} not found on {self.server}"

            return True, f"NFS server reachable, export {self.export_path} available"
        except FileNotFoundError:
            return False, "showmount command not found (nfs-common not installed)"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    async def mount(self) -> str | None:
        """Mount the NFS share."""
        self.mount_point.mkdir(parents=True, exist_ok=True)

        # Check if already mounted
        if os.path.ismount(str(self.mount_point)):
            return str(self.mount_point)

        source = f"{self.server}:{self.export_path}"
        cmd = ["mount", "-t", "nfs"]
        if self.mount_options:
            cmd.extend(["-o", self.mount_options])
        cmd.extend([source, str(self.mount_point)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                logger.error("NFS mount timed out")
                return None

            if proc.returncode != 0:
                logger.error(f"NFS mount failed: {stderr.decode()}")
                return None

            return str(self.mount_point)
        except Exception as e:
            logger.error(f"NFS mount error: {e}")
            return None

    async def unmount(self) -> None:
        """Unmount the NFS share."""
        if os.path.ismount(str(self.mount_point)):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "umount", str(self.mount_point),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=10)
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.error("NFS unmount timed out")
            except Exception as e:
                logger.error(f"NFS unmount error: {e}")

    async def get_stats(self) -> dict:
        """Get NFS storage statistics."""
        if not os.path.ismount(str(self.mount_point)):
            mount_result = await self.mount()
            if not mount_result:
                return {"used_bytes": 0, "total_bytes": None, "file_count": 0}

        try:
            stat = shutil.disk_usage(str(self.mount_point))

            # Count files
            file_count = sum(1 for _ in self.mount_point.rglob("*") if _.is_file())

            return {
                "used_bytes": stat.used,
                "total_bytes": stat.total,
                "file_count": file_count,
            }
        except Exception as e:
            logger.error(f"Failed to get NFS stats: {e}")
            return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class HttpBackendService:
    """HTTP backend operations."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.base_url = config["base_url"]
        self.auth_method = config.get("auth_method", "none")
        self.username = config.get("username")
        self.password = config.get("password")

    def _get_auth(self) -> aiohttp.BasicAuth | None:
        """Get auth for requests."""
        if self.auth_method == "basic" and self.username:
            return aiohttp.BasicAuth(self.username, self.password or "")
        return None

    def _get_headers(self) -> dict:
        """Get headers for requests."""
        headers = {}
        if self.auth_method == "bearer" and self.password:
            headers["Authorization"] = f"Bearer {self.password}"
        return headers

    async def test_connection(self) -> tuple[bool, str]:
        """Test HTTP connectivity."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    self.base_url,
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 400:
                        return True, f"HTTP endpoint reachable (status {resp.status})"
                    return False, f"HTTP endpoint returned status {resp.status}"
        except aiohttp.ClientError as e:
            return False, f"HTTP connection failed: {str(e)}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    async def mount(self) -> str | None:
        """HTTP backends don't need mounting."""
        return None

    async def unmount(self) -> None:
        """HTTP backends don't need unmounting."""
        pass

    async def get_stats(self) -> dict:
        """Get HTTP storage statistics (limited info available)."""
        # HTTP backends can't easily report disk usage
        # We'd need to crawl the directory listing
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class S3BackendService:
    """S3 backend operations (stub)."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.config = config

    async def test_connection(self) -> tuple[bool, str]:
        return False, "S3 backend not yet implemented"

    async def mount(self) -> str | None:
        return None

    async def unmount(self) -> None:
        pass

    async def get_stats(self) -> dict:
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class IscsiBackendService:
    """iSCSI backend operations (stub)."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.config = config

    async def test_connection(self) -> tuple[bool, str]:
        return False, "iSCSI backend not yet implemented"

    async def mount(self) -> str | None:
        return None

    async def unmount(self) -> None:
        pass

    async def get_stats(self) -> dict:
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


def get_backend_service(backend_id: str, backend_type: str, config: dict):
    """Factory to get the appropriate backend service."""
    services = {
        "nfs": NfsBackendService,
        "http": HttpBackendService,
        "s3": S3BackendService,
        "iscsi": IscsiBackendService,
    }
    service_class = services.get(backend_type)
    if not service_class:
        raise ValueError(f"Unknown backend type: {backend_type}")
    return service_class(backend_id, config)
