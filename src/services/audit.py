"""Audit logging service with database, file, and SIEM support."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Service for writing audit logs to multiple destinations."""

    def __init__(self):
        self.file_path: Path | None = None
        self.siem_webhook_url: str | None = None

    def configure(
        self, file_path: str | None = None, siem_webhook_url: str | None = None
    ):
        """Configure optional destinations.

        Args:
            file_path: Path to audit log file (directory will be created if needed)
            siem_webhook_url: URL for SIEM webhook integration
        """
        if file_path:
            self.file_path = Path(file_path)
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if siem_webhook_url:
            self.siem_webhook_url = siem_webhook_url

    async def log(
        self,
        db: AsyncSession,
        *,
        actor_id: str | None,
        actor_type: str,
        actor_username: str,
        actor_ip: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        resource_name: str | None = None,
        details: dict[str, Any] | None = None,
        result: str,
        error_message: str | None = None,
        session_id: str | None = None,
        auth_method: str | None = None,
    ) -> AuditLog:
        """Log an audit event to all configured destinations.

        Args:
            db: Database session
            actor_id: ID of the user or service account performing the action
            actor_type: Type of actor (user, service_account, system)
            actor_username: Username of the actor
            actor_ip: IP address of the actor
            action: Action being performed (login, create, update, delete, etc.)
            resource_type: Type of resource being acted upon (node, user, role, etc.)
            resource_id: ID of the resource (optional)
            resource_name: Human-readable name of the resource (optional)
            details: Additional action-specific details as dict
            result: Result of the action (success, failure, denied)
            error_message: Error message if action failed
            session_id: Session ID for tracking
            auth_method: Authentication method used (jwt, api_key, ldap)

        Returns:
            The created AuditLog entry
        """
        # Create DB record
        audit_entry = AuditLog(
            actor_id=actor_id,
            actor_type=actor_type,
            actor_username=actor_username,
            actor_ip=actor_ip,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details_json=json.dumps(details) if details else None,
            result=result,
            error_message=error_message,
            session_id=session_id,
            auth_method=auth_method,
        )
        db.add(audit_entry)
        await db.flush()

        # Prepare log dict for file/SIEM
        log_dict = self._to_dict(audit_entry, details)

        # Write to file (non-blocking best effort)
        if self.file_path:
            await self._write_to_file(log_dict)

        # Send to SIEM (non-blocking best effort)
        if self.siem_webhook_url:
            await self._send_to_siem(log_dict)

        return audit_entry

    def _to_dict(self, entry: AuditLog, details: dict | None) -> dict:
        """Convert audit entry to dictionary for external destinations.

        Args:
            entry: The AuditLog database entry
            details: Original details dict (avoids re-parsing JSON)

        Returns:
            Dictionary representation of the audit entry
        """
        return {
            "id": entry.id,
            "timestamp": (
                entry.timestamp.isoformat()
                if entry.timestamp
                else datetime.utcnow().isoformat()
            ),
            "actor": {
                "id": entry.actor_id,
                "type": entry.actor_type,
                "username": entry.actor_username,
                "ip": entry.actor_ip,
            },
            "action": entry.action,
            "resource": {
                "type": entry.resource_type,
                "id": entry.resource_id,
                "name": entry.resource_name,
            },
            "details": details,
            "result": entry.result,
            "error_message": entry.error_message,
            "session_id": entry.session_id,
            "auth_method": entry.auth_method,
        }

    async def _write_to_file(self, log_dict: dict):
        """Write audit log entry to file.

        Uses aiofiles if available, falls back to sync write.
        Errors are logged but do not propagate.

        Args:
            log_dict: Dictionary representation of audit entry
        """
        try:
            import aiofiles

            async with aiofiles.open(self.file_path, mode="a") as f:
                await f.write(json.dumps(log_dict) + "\n")
        except ImportError:
            # aiofiles not installed, use sync write
            try:
                with open(self.file_path, "a") as f:
                    f.write(json.dumps(log_dict) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log to file: {e}")
        except Exception as e:
            logger.error(f"Failed to write audit log to file: {e}")

    async def _send_to_siem(self, log_dict: dict):
        """Send audit log entry to SIEM webhook.

        Uses httpx for async HTTP requests.
        Errors are logged but do not propagate.

        Args:
            log_dict: Dictionary representation of audit entry
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.siem_webhook_url, json=log_dict)
        except ImportError:
            logger.warning("httpx not installed, SIEM webhook disabled")
        except Exception as e:
            logger.error(f"Failed to send audit log to SIEM: {e}")


# Global singleton
audit_service = AuditService()


async def audit_action(
    db: AsyncSession,
    request,  # FastAPI Request
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    resource_name: str | None = None,
    details: dict[str, Any] | None = None,
    result: str = "success",
    error_message: str | None = None,
) -> AuditLog:
    """Convenience function to log using request context for actor info.

    Extracts actor information from the FastAPI request state
    (set by auth middleware) and delegates to the audit service.

    Args:
        db: Database session
        request: FastAPI Request object with auth state
        action: Action being performed
        resource_type: Type of resource being acted upon
        resource_id: ID of the resource (optional)
        resource_name: Human-readable name of the resource (optional)
        details: Additional action-specific details
        result: Result of the action (default: "success")
        error_message: Error message if action failed

    Returns:
        The created AuditLog entry
    """
    # Extract actor info from request state (set by auth middleware)
    user = getattr(request.state, "user", None)
    auth_method = getattr(request.state, "auth_method", None)

    actor_id = user.id if user else None
    actor_type = (
        "service_account"
        if (user and getattr(user, "is_service_account", False))
        else "user" if user else "anonymous"
    )
    actor_username = user.username if user else "anonymous"

    # Get client IP
    actor_ip = request.client.host if request.client else None

    return await audit_service.log(
        db,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_username=actor_username,
        actor_ip=actor_ip,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        details=details,
        result=result,
        error_message=error_message,
        auth_method=auth_method,
    )
