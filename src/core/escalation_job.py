"""Background job for processing expired approvals."""
import logging

from src.db.database import async_session_factory
from src.services.approvals import process_expired_approvals

logger = logging.getLogger(__name__)

MAX_ESCALATIONS = 3


async def process_escalations() -> None:
    """
    Check for and process expired approvals.

    This job runs periodically to:
    1. Find approvals that have passed their expiration time
    2. Escalate approvals that haven't reached max_escalations
    3. Auto-reject approvals that have reached max_escalations

    The escalation resets the expiration timer, giving the escalation
    role members time to review and vote on the request.
    """
    if not async_session_factory:
        logger.warning("Database not initialized, skipping escalation check")
        return

    async with async_session_factory() as db:
        try:
            escalated, rejected = await process_expired_approvals(db, MAX_ESCALATIONS)
            if escalated > 0 or rejected > 0:
                logger.info(
                    f"Processed expired approvals: {escalated} escalated, {rejected} auto-rejected"
                )
            await db.commit()
        except Exception as e:
            logger.error(f"Error processing escalations: {e}")
            await db.rollback()
