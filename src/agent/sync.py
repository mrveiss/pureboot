"""Cache sync service for synchronizing content with central controller.

The sync service:
- Downloads bootloaders and essential files
- Syncs content based on cache policy
- Handles scheduled and on-demand syncs
- Tracks sync status for heartbeat reporting
"""
import asyncio
import fnmatch
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import aiohttp
from pydantic import BaseModel

from src.agent.cache.content_cache import ContentCache
from src.agent.cache.state_cache import NodeStateCache
from src.agent.central_client import CentralClient

logger = logging.getLogger(__name__)


class SyncResult(BaseModel):
    """Result of a sync operation."""
    files_synced: int = 0
    bytes_transferred: int = 0
    errors: list[str] = []
    duration_seconds: float = 0.0
    status: Literal["success", "partial", "failed"] = "success"


class CacheSyncService:
    """Synchronizes cache with central controller."""

    # Essential bootloader files that should always be synced
    ESSENTIAL_BOOTLOADERS = [
        "ipxe.efi",
        "undionly.kpxe",
        "snponly.efi",
        "grub/grubx64.efi",
        "grub/grub.cfg",
    ]

    def __init__(
        self,
        central_url: str,
        site_id: str,
        content_cache: ContentCache,
        state_cache: NodeStateCache,
        timeout: float = 300.0,
    ):
        """Initialize sync service.

        Args:
            central_url: Base URL of central controller
            site_id: This agent's site ID
            content_cache: Content cache instance
            state_cache: Node state cache instance
            timeout: Request timeout in seconds
        """
        self.central_url = central_url.rstrip("/")
        self.site_id = site_id
        self.content_cache = content_cache
        self.state_cache = state_cache
        self.timeout = timeout

        self._session: aiohttp.ClientSession | None = None
        self._last_sync_at: datetime | None = None
        self._last_sync_result: SyncResult | None = None
        self._sync_lock = asyncio.Lock()

    async def start(self):
        """Start the sync service."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        logger.info("Cache sync service started")

    async def stop(self):
        """Stop the sync service."""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Cache sync service stopped")

    @property
    def last_sync_at(self) -> datetime | None:
        """Get timestamp of last sync."""
        return self._last_sync_at

    @property
    def last_sync_result(self) -> SyncResult | None:
        """Get result of last sync."""
        return self._last_sync_result

    async def _download_file(self, url: str) -> bytes | None:
        """Download file from URL.

        Returns:
            File content or None on error
        """
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                elif resp.status == 404:
                    logger.debug(f"File not found: {url}")
                    return None
                else:
                    logger.warning(f"Failed to download {url}: {resp.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Download error for {url}: {e}")
            return None

    async def _sync_file(
        self,
        category: str,
        path: str,
        result: SyncResult,
    ) -> bool:
        """Sync a single file.

        Returns:
            True if synced successfully
        """
        # Check if already cached
        cached = await self.content_cache.get(category, path)
        if cached:
            return True

        # Download from central
        url = f"{self.central_url}/tftp/{path}" if category == "bootloaders" else \
              f"{self.central_url}/api/v1/files/{category}/{path}"

        content = await self._download_file(url)
        if content is None:
            result.errors.append(f"Failed to download: {category}/{path}")
            return False

        # Cache the file
        try:
            await self.content_cache.put(category, path, content)
            result.files_synced += 1
            result.bytes_transferred += len(content)
            return True
        except Exception as e:
            result.errors.append(f"Failed to cache {category}/{path}: {e}")
            return False

    async def sync_bootloaders(self) -> SyncResult:
        """Sync essential bootloader files.

        Returns:
            SyncResult with operation details
        """
        result = SyncResult()
        start_time = datetime.now(timezone.utc)

        for bootloader in self.ESSENTIAL_BOOTLOADERS:
            await self._sync_file("bootloaders", bootloader, result)

        result.duration_seconds = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        if result.errors:
            result.status = "partial" if result.files_synced > 0 else "failed"

        logger.info(
            f"Bootloader sync: {result.files_synced} files, "
            f"{result.bytes_transferred} bytes, {len(result.errors)} errors"
        )
        return result

    async def sync_assigned_content(self) -> SyncResult:
        """Sync content assigned to this site.

        Fetches list of assigned content from central and syncs.

        Returns:
            SyncResult with operation details
        """
        result = SyncResult()
        start_time = datetime.now(timezone.utc)

        # Get assigned content list from central
        try:
            url = f"{self.central_url}/api/v1/sites/{self.site_id}/assigned-content"
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    assigned_files = data.get("files", [])
                else:
                    result.errors.append(f"Failed to get assigned content: {resp.status}")
                    result.status = "failed"
                    return result
        except aiohttp.ClientError as e:
            result.errors.append(f"Failed to get assigned content: {e}")
            result.status = "failed"
            return result

        # Sync each assigned file
        for item in assigned_files:
            category = item.get("category", "templates")
            path = item.get("path", "")
            if path:
                await self._sync_file(category, path, result)

        result.duration_seconds = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        if result.errors:
            result.status = "partial" if result.files_synced > 0 else "failed"

        logger.info(
            f"Assigned content sync: {result.files_synced} files, "
            f"{result.bytes_transferred} bytes"
        )
        return result

    async def sync_patterns(self, patterns: list[str]) -> SyncResult:
        """Sync content matching glob patterns.

        Args:
            patterns: Glob patterns to match (e.g., "templates/kickstart/*")

        Returns:
            SyncResult with operation details
        """
        result = SyncResult()
        start_time = datetime.now(timezone.utc)

        # Get file list from central
        try:
            url = f"{self.central_url}/api/v1/files"
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    all_files = data.get("files", [])
                else:
                    result.errors.append(f"Failed to list files: {resp.status}")
                    result.status = "failed"
                    return result
        except aiohttp.ClientError as e:
            result.errors.append(f"Failed to list files: {e}")
            result.status = "failed"
            return result

        # Filter by patterns and sync
        for file_info in all_files:
            file_path = f"{file_info.get('category', '')}/{file_info.get('path', '')}"
            for pattern in patterns:
                if fnmatch.fnmatch(file_path, pattern):
                    await self._sync_file(
                        file_info.get("category", "templates"),
                        file_info.get("path", ""),
                        result,
                    )
                    break

        result.duration_seconds = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        if result.errors:
            result.status = "partial" if result.files_synced > 0 else "failed"

        return result

    async def full_sync(self) -> SyncResult:
        """Full mirror sync of all content.

        Returns:
            SyncResult with operation details
        """
        result = SyncResult()
        start_time = datetime.now(timezone.utc)

        # Sync bootloaders first
        bootloader_result = await self.sync_bootloaders()
        result.files_synced += bootloader_result.files_synced
        result.bytes_transferred += bootloader_result.bytes_transferred
        result.errors.extend(bootloader_result.errors)

        # Get all files from central
        try:
            url = f"{self.central_url}/api/v1/files"
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    all_files = data.get("files", [])
                else:
                    result.errors.append(f"Failed to list files: {resp.status}")
                    result.status = "partial"
                    return result
        except aiohttp.ClientError as e:
            result.errors.append(f"Failed to list files: {e}")
            result.status = "partial"
            return result

        # Sync all files
        for file_info in all_files:
            await self._sync_file(
                file_info.get("category", "templates"),
                file_info.get("path", ""),
                result,
            )

        result.duration_seconds = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        if result.errors:
            result.status = "partial" if result.files_synced > 0 else "failed"

        logger.info(
            f"Full sync: {result.files_synced} files, "
            f"{result.bytes_transferred} bytes, {len(result.errors)} errors"
        )
        return result

    async def run_scheduled_sync(self) -> SyncResult:
        """Run sync based on cache policy.

        Returns:
            SyncResult with operation details
        """
        async with self._sync_lock:
            policy = self.content_cache.policy

            logger.info(f"Running scheduled sync (policy={policy})")

            if policy == "minimal":
                result = await self.sync_bootloaders()
            elif policy == "assigned":
                bootloader_result = await self.sync_bootloaders()
                assigned_result = await self.sync_assigned_content()
                result = SyncResult(
                    files_synced=bootloader_result.files_synced + assigned_result.files_synced,
                    bytes_transferred=bootloader_result.bytes_transferred + assigned_result.bytes_transferred,
                    errors=bootloader_result.errors + assigned_result.errors,
                    duration_seconds=bootloader_result.duration_seconds + assigned_result.duration_seconds,
                )
                if result.errors:
                    result.status = "partial" if result.files_synced > 0 else "failed"
            elif policy == "mirror":
                result = await self.full_sync()
            elif policy == "pattern":
                bootloader_result = await self.sync_bootloaders()
                pattern_result = await self.sync_patterns(self.content_cache.patterns)
                result = SyncResult(
                    files_synced=bootloader_result.files_synced + pattern_result.files_synced,
                    bytes_transferred=bootloader_result.bytes_transferred + pattern_result.bytes_transferred,
                    errors=bootloader_result.errors + pattern_result.errors,
                    duration_seconds=bootloader_result.duration_seconds + pattern_result.duration_seconds,
                )
                if result.errors:
                    result.status = "partial" if result.files_synced > 0 else "failed"
            else:
                result = await self.sync_bootloaders()

            self._last_sync_at = datetime.now(timezone.utc)
            self._last_sync_result = result
            return result

    async def run_manual_sync(
        self,
        force: bool = False,
        categories: list[str] | None = None,
    ) -> SyncResult:
        """Run manual sync.

        Args:
            force: Force re-download even if cached
            categories: Optional list of categories to sync

        Returns:
            SyncResult with operation details
        """
        async with self._sync_lock:
            logger.info(f"Running manual sync (force={force}, categories={categories})")

            if force:
                # Clear cache before sync
                if categories:
                    for cat in categories:
                        await self.content_cache.clear(cat)
                else:
                    await self.content_cache.clear()

            # Run full sync based on policy
            result = await self.run_scheduled_sync()
            return result
