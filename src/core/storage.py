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
        pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>'

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


class S3BackendService:
    """S3 backend operations."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.config = config
        self.endpoint = config["endpoint"]
        self.bucket = config["bucket"]

    def supports_write(self) -> bool:
        return True

    async def test_connection(self) -> tuple[bool, str]:
        """Test S3 connectivity."""
        url = f"{self.endpoint}/{self.bucket}?list-type=2&max-keys=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status < 400:
                        return True, f"S3 bucket accessible"
                    return False, f"S3 error: {resp.status}"
        except aiohttp.ClientError as e:
            return False, f"S3 connection failed: {str(e)}"

    async def mount(self) -> str | None:
        return None

    async def unmount(self) -> None:
        pass

    async def get_stats(self) -> dict:
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}

    async def list_files(self, path: str) -> list[FileInfo]:
        """List files in S3 bucket."""
        if ".." in path:
            raise ValueError("Path traversal not allowed")

        prefix = path.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        if prefix == "/":
            prefix = ""

        url = f"{self.endpoint}/{self.bucket}?list-type=2&prefix={prefix}&delimiter=/"

        try:
            async with aiohttp.ClientSession() as session:
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
        for match in re.finditer(r'<Contents>.*?<Key>([^<]+)</Key>.*?<Size>([^<]+)</Size>.*?</Contents>', xml_content, re.DOTALL):
            key = match.group(1)
            size = int(match.group(2))

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

        key = path.lstrip("/")
        url = f"{self.endpoint}/{self.bucket}/{key}"

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

        # Build key
        base = path.lstrip("/").rstrip("/")
        key = f"{base}/{filename}" if base else filename
        url = f"{self.endpoint}/{self.bucket}/{key}"

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
        deleted = 0

        for path in paths:
            if ".." in path:
                continue
            key = path.lstrip("/")
            url = f"{self.endpoint}/{self.bucket}/{key}"

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

        key = path.lstrip("/").rstrip("/") + "/"
        url = f"{self.endpoint}/{self.bucket}/{key}"

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

        src_key = source.lstrip("/")
        dst_key = destination.lstrip("/")

        # Copy
        copy_url = f"{self.endpoint}/{self.bucket}/{dst_key}"
        copy_source = f"/{self.bucket}/{src_key}"

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
                delete_url = f"{self.endpoint}/{self.bucket}/{src_key}"
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
