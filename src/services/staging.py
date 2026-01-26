"""Staging provisioning service for staged mode cloning."""
import json
import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CloneSession, StorageBackend

logger = logging.getLogger(__name__)

# Valid staging status values
StagingStatus = Literal[
    "pending",
    "provisioning",
    "provisioned",
    "uploading",
    "ready",
    "downloading",
    "cleanup",
    "deleted",
]


class StagingService:
    """Service for managing staging storage for clone sessions."""

    async def provision_staging(
        self, session: CloneSession, db: AsyncSession
    ) -> dict:
        """
        Provision staging storage for a clone session.

        Args:
            session: The clone session requiring staging storage
            db: Database session

        Returns:
            Mount info dict with instructions for nodes containing:
            - type: "nfs" or "iscsi"
            - Connection parameters specific to the backend type

        Raises:
            ValueError: If no backend assigned, backend not found,
                       or unsupported backend type
        """
        if not session.staging_backend_id:
            raise ValueError("No storage backend assigned to session")

        # Get backend
        result = await db.execute(
            select(StorageBackend).where(
                StorageBackend.id == session.staging_backend_id
            )
        )
        backend = result.scalar_one_or_none()
        if not backend:
            raise ValueError("Storage backend not found")

        config = json.loads(backend.config_json)

        if backend.type == "nfs":
            return await self._provision_nfs(session, backend, config)
        elif backend.type == "iscsi":
            return await self._provision_iscsi(session, backend, config)
        else:
            raise ValueError(f"Unsupported backend type: {backend.type}")

    async def _provision_nfs(
        self, session: CloneSession, backend: StorageBackend, config: dict
    ) -> dict:
        """
        Provision NFS directory for staging.

        Creates a staging path within the NFS export for storing
        the compressed disk image.

        Args:
            session: The clone session
            backend: The NFS storage backend
            config: Backend configuration dict

        Returns:
            NFS mount info dict with server, export, path, and options
        """
        # Create staging path within NFS export
        staging_dir = f"clone-{session.id}"
        export_path = config.get("export_path", config.get("export", "/data"))
        staging_path = f"{export_path}/{staging_dir}"

        session.staging_path = staging_path
        session.staging_status = "provisioned"

        logger.info(
            f"Provisioned NFS staging for session {session.id}: {staging_path}"
        )

        return {
            "type": "nfs",
            "server": config.get("server"),
            "export": export_path,
            "path": staging_dir,
            "options": config.get("mount_options", config.get("options", "rw,sync")),
            "image_filename": "disk.raw.gz",
        }

    async def _provision_iscsi(
        self, session: CloneSession, backend: StorageBackend, config: dict
    ) -> dict:
        """
        Provision iSCSI LUN for staging.

        For iSCSI staging, the disk size must be known upfront as
        block storage requires pre-allocation.

        Args:
            session: The clone session
            backend: The iSCSI storage backend
            config: Backend configuration dict

        Returns:
            iSCSI connection info dict with target, portal, and auth

        Raises:
            ValueError: If source disk size is not known
        """
        # For iSCSI, we need to know the size upfront
        if not session.bytes_total:
            raise ValueError("Source disk size must be known for iSCSI staging")

        # iSCSI target info - the LUN should be pre-configured
        session.staging_path = f"clone-{session.id}"
        session.staging_size_bytes = session.bytes_total
        session.staging_status = "provisioned"

        logger.info(
            f"Provisioned iSCSI staging for session {session.id}: "
            f"{session.staging_size_bytes} bytes"
        )

        return {
            "type": "iscsi",
            "target": config.get("target"),
            "portal": config.get("portal"),
            "username": config.get("username"),
            "password": config.get("password"),
            "lun": 0,  # Usually LUN 0 for single-disk staging
        }

    async def get_staging_mount_info(
        self, session: CloneSession, db: AsyncSession
    ) -> dict:
        """
        Get mount information for a clone session's staging storage.

        This is used by both source and target nodes to access the
        staging storage location.

        Args:
            session: The clone session
            db: Database session

        Returns:
            Mount info dict appropriate for the backend type

        Raises:
            ValueError: If no backend assigned, backend not found,
                       or unsupported backend type
        """
        if not session.staging_backend_id:
            raise ValueError("No storage backend assigned to session")

        result = await db.execute(
            select(StorageBackend).where(
                StorageBackend.id == session.staging_backend_id
            )
        )
        backend = result.scalar_one_or_none()
        if not backend:
            raise ValueError("Storage backend not found")

        config = json.loads(backend.config_json)

        if backend.type == "nfs":
            export_path = config.get("export_path", config.get("export", "/data"))
            # Extract just the staging directory name from the full path
            if session.staging_path:
                path = session.staging_path.split("/")[-1]
            else:
                path = f"clone-{session.id}"

            return {
                "type": "nfs",
                "server": config.get("server"),
                "export": export_path,
                "path": path,
                "options": config.get(
                    "mount_options", config.get("options", "rw,sync")
                ),
                "image_filename": "disk.raw.gz",
            }
        elif backend.type == "iscsi":
            return {
                "type": "iscsi",
                "target": config.get("target"),
                "portal": config.get("portal"),
                "username": config.get("username"),
                "password": config.get("password"),
                "lun": 0,
            }
        else:
            raise ValueError(f"Unsupported backend type: {backend.type}")

    async def cleanup_staging(
        self, session: CloneSession, db: AsyncSession
    ) -> bool:
        """
        Clean up staging storage after clone completion.

        For NFS: Marks for directory removal (actual deletion by cleanup job)
        For iSCSI: Marks for LUN release (if dynamically provisioned)

        Note: Actual file/LUN deletion is typically performed by a
        background cleanup job or administrator action, not directly
        by this method.

        Args:
            session: The clone session to clean up
            db: Database session

        Returns:
            True if cleanup was initiated successfully, False otherwise
        """
        if not session.staging_backend_id or not session.staging_path:
            logger.debug(f"No staging to clean up for session {session.id}")
            return True  # Nothing to clean up

        result = await db.execute(
            select(StorageBackend).where(
                StorageBackend.id == session.staging_backend_id
            )
        )
        backend = result.scalar_one_or_none()
        if not backend:
            logger.warning(
                f"Storage backend {session.staging_backend_id} not found "
                f"for session {session.id} cleanup"
            )
            return False

        # Mark staging as cleanup in progress
        session.staging_status = "cleanup"

        logger.info(
            f"Initiating staging cleanup for session {session.id} "
            f"at {session.staging_path}"
        )

        # Note: Actual file deletion would happen on the storage server
        # For NFS, we could mount and delete, but that's typically
        # done by a cleanup cron job or admin action
        # For iSCSI, LUN deprovisioning requires storage array API calls

        session.staging_status = "deleted"

        logger.info(f"Staging cleanup completed for session {session.id}")
        return True

    async def update_staging_status(
        self, session: CloneSession, new_status: StagingStatus
    ) -> None:
        """
        Update the staging status of a clone session.

        Status progression:
        - pending: Staging not yet provisioned
        - provisioning: Provisioning in progress
        - provisioned: Storage ready, awaiting upload
        - uploading: Source node uploading disk image
        - ready: Image uploaded, ready for download
        - downloading: Target node downloading image
        - cleanup: Cleanup in progress
        - deleted: Storage released

        Args:
            session: The clone session to update
            new_status: The new staging status

        Raises:
            ValueError: If the status is not a valid staging status
        """
        valid_statuses = {
            "pending",
            "provisioning",
            "provisioned",
            "uploading",
            "ready",
            "downloading",
            "cleanup",
            "deleted",
        }
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid staging status: {new_status}")

        old_status = session.staging_status
        session.staging_status = new_status

        logger.debug(
            f"Session {session.id} staging status: {old_status} -> {new_status}"
        )

    async def validate_backend_for_staging(
        self, backend_id: str, db: AsyncSession
    ) -> tuple[bool, str]:
        """
        Validate that a storage backend is suitable for staging.

        Checks:
        - Backend exists
        - Backend type supports staging (NFS or iSCSI)
        - Backend is online

        Args:
            backend_id: The storage backend ID to validate
            db: Database session

        Returns:
            Tuple of (is_valid, message)
        """
        result = await db.execute(
            select(StorageBackend).where(StorageBackend.id == backend_id)
        )
        backend = result.scalar_one_or_none()

        if not backend:
            return False, "Storage backend not found"

        if backend.type not in ("nfs", "iscsi"):
            return False, (
                f"Backend type '{backend.type}' not supported for staging. "
                "Use NFS or iSCSI."
            )

        if backend.status != "online":
            return False, (
                f"Storage backend is {backend.status}. Must be online for staging."
            )

        return True, "Backend is valid for staging"


# Global service instance
staging_service = StagingService()
