"""Service for managing node state transitions with audit logging."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.state_machine import InvalidStateTransition, NodeStateMachine
from src.db.models import Node, NodeStateLog

logger = logging.getLogger(__name__)

MAX_INSTALL_ATTEMPTS = 3


class StateTransitionService:
    """Handles node state transitions with validation and audit logging."""

    @staticmethod
    async def transition(
        db: AsyncSession,
        node: Node,
        to_state: str,
        triggered_by: str = "admin",
        user_id: str | None = None,
        comment: str | None = None,
        metadata: dict | None = None,
        force: bool = False,
    ) -> Node:
        """
        Transition a node to a new state with audit logging.

        Args:
            db: Database session
            node: Node to transition
            to_state: Target state
            triggered_by: Who triggered (admin, system, node_report)
            user_id: User ID if admin triggered
            comment: Optional comment
            metadata: Optional metadata dict
            force: Bypass retry limits and reset counters

        Returns:
            Updated node

        Raises:
            InvalidStateTransition: If transition is not valid
            ValueError: If max retries exceeded without force
        """
        from_state = node.state

        # Check retry limit for install_failed -> pending (unless forcing)
        if (
            from_state == "install_failed"
            and to_state == "pending"
            and not force
            and node.install_attempts >= MAX_INSTALL_ATTEMPTS
        ):
            raise ValueError(
                f"Max install attempts ({MAX_INSTALL_ATTEMPTS}) exceeded. "
                "Use force=true to reset and retry."
            )

        # Validate transition (skip if force=True to allow any state change)
        if not force and not NodeStateMachine.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state)

        # Apply transition
        node.state = to_state
        node.state_changed_at = datetime.now(timezone.utc)

        # Reset counters if force or successful install
        if force or to_state == "installed":
            node.install_attempts = 0
            node.last_install_error = None

        # Create audit log
        log_entry = NodeStateLog(
            node_id=node.id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            user_id=user_id,
            comment=comment,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        db.add(log_entry)

        # Application logging
        logger.info(
            f"Node {node.id} ({node.mac_address}) transitioned: "  # nosec - MAC needed for ops
            f"{from_state} -> {to_state} (triggered_by={triggered_by})"
        )

        return node

    @staticmethod
    async def handle_install_failure(
        db: AsyncSession,
        node: Node,
        error: str | None = None,
    ) -> Node:
        """
        Handle installation failure with retry logic.

        Args:
            db: Database session
            node: Node that failed installation
            error: Error message

        Returns:
            Updated node (either still installing or install_failed)
        """
        node.install_attempts += 1
        node.last_install_error = error

        if node.install_attempts >= MAX_INSTALL_ATTEMPTS:
            # Max retries exceeded - transition to install_failed
            return await StateTransitionService.transition(
                db=db,
                node=node,
                to_state="install_failed",
                triggered_by="node_report",
                metadata={"error": error, "attempt": node.install_attempts},
            )
        else:
            # Still have retries - stay in installing, just log
            logger.warning(
                f"Node {node.id} install failed (attempt {node.install_attempts}/{MAX_INSTALL_ATTEMPTS}): {error}"
            )
            return node
