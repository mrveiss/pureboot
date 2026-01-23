"""Service layer for approval workflow business logic.

This module provides functions for managing the approval workflow including:
- Finding matching approval rules based on operation context
- Creating approval requests with proper expiration
- Casting votes with four-eye principle enforcement
- Escalation and expiration handling
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    Approval,
    ApprovalRule,
    ApprovalVote,
    User,
    UserGroup,
    UserGroupMember,
)

logger = logging.getLogger(__name__)


class ApprovalError(Exception):
    """Base exception for approval-related errors."""

    pass


class UserCannotVoteError(ApprovalError):
    """Raised when a user is not allowed to vote on an approval."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval is not found."""

    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval not found: {approval_id}")


class RuleNotFoundError(ApprovalError):
    """Raised when no matching approval rule is found."""

    pass


async def find_matching_rule(
    db: AsyncSession,
    operation_type: str,
    user_id: str,
    device_group_id: str | None = None,
) -> ApprovalRule | None:
    """
    Find the highest priority active rule matching the operation and context.

    Rules are evaluated in priority order (highest first):
    1. Device group scope - rules matching the specific device_group_id
    2. User group scope - rules matching one of the user's groups
    3. Global scope - rules with no scope restriction

    Args:
        db: Database session
        operation_type: The operation being performed (e.g., "node.provision")
        user_id: The user requesting the operation
        device_group_id: Optional device group context for the operation

    Returns:
        The highest priority matching ApprovalRule, or None if no rule matches
    """
    # Get user's group IDs for user_group scope matching
    user_groups_query = select(UserGroupMember.user_group_id).where(
        UserGroupMember.user_id == user_id
    )
    result = await db.execute(user_groups_query)
    user_group_ids = [row[0] for row in result.fetchall()]

    # Build query for active rules ordered by priority (descending)
    query = (
        select(ApprovalRule)
        .where(ApprovalRule.is_active == True)  # noqa: E712
        .order_by(ApprovalRule.priority.desc())
    )

    result = await db.execute(query)
    rules = result.scalars().all()

    # Check each rule in priority order
    for rule in rules:
        # Parse operations from JSON
        try:
            operations = json.loads(rule.operations_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid operations_json in rule {rule.id}")
            continue

        # Check if operation_type matches any pattern in the rule
        if not _operation_matches(operation_type, operations):
            continue

        # Check scope matching
        if rule.scope_type == "device_group":
            # Device group scope: must match the device_group_id
            if device_group_id and rule.scope_id == device_group_id:
                logger.debug(
                    f"Found matching device_group rule {rule.id} for operation {operation_type}"
                )
                return rule
        elif rule.scope_type == "user_group":
            # User group scope: user must be a member of the scope group
            if rule.scope_id in user_group_ids:
                logger.debug(
                    f"Found matching user_group rule {rule.id} for operation {operation_type}"
                )
                return rule
        elif rule.scope_type == "global":
            # Global scope: matches any context
            logger.debug(
                f"Found matching global rule {rule.id} for operation {operation_type}"
            )
            return rule

    logger.debug(f"No matching approval rule found for operation {operation_type}")
    return None


def _operation_matches(operation_type: str, operations: list[str]) -> bool:
    """
    Check if an operation type matches any pattern in the operations list.

    Supports exact matches and wildcard patterns:
    - "node.provision" matches "node.provision"
    - "node.*" matches "node.provision", "node.delete", etc.
    - "*" matches everything

    Args:
        operation_type: The operation being performed
        operations: List of operation patterns to match against

    Returns:
        True if operation_type matches any pattern
    """
    for pattern in operations:
        if pattern == "*":
            return True
        if pattern == operation_type:
            return True
        # Handle wildcard patterns like "node.*"
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if operation_type.startswith(prefix + "."):
                return True
    return False


async def create_approval_request(
    db: AsyncSession,
    rule: ApprovalRule,
    operation_type: str,
    requester_id: str,
    requester_name: str,
    target_type: str,
    target_id: str,
    description: str,
    action_data: dict | None = None,
    metadata: dict | None = None,
) -> Approval:
    """
    Create a new approval request based on a rule.

    Args:
        db: Database session
        rule: The approval rule governing this request
        operation_type: Type of operation requiring approval
        requester_id: ID of the user requesting approval
        requester_name: Display name of the requester
        target_type: Type of target resource (e.g., "node", "workflow")
        target_id: ID of the target resource
        description: Human-readable description of the request
        action_data: Data needed to execute the action when approved
        metadata: Additional context about the request

    Returns:
        The created Approval object
    """
    # Calculate expiration time from rule timeout
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=rule.escalation_timeout_hours
    )

    # Build action data JSON
    action_data_dict = action_data or {}
    action_data_dict.update(
        {
            "target_type": target_type,
            "target_id": target_id,
            "description": description,
        }
    )

    approval = Approval(
        rule_id=rule.id,
        operation_type=operation_type,
        action_type=operation_type,  # Legacy field compatibility
        action_data_json=json.dumps(action_data_dict),
        requester_id=requester_id,
        requester_name=requester_name,
        required_approvers=rule.required_approvers,
        expires_at=expires_at,
        metadata_json=json.dumps(metadata) if metadata else None,
    )

    db.add(approval)
    await db.flush()
    await db.refresh(approval, ["votes", "rule"])

    logger.info(
        f"Created approval request {approval.id} for {operation_type} "
        f"by {requester_name} (rule: {rule.name})"
    )

    return approval


async def cast_vote(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
    user_name: str,
    vote: str,
    comment: str | None = None,
    is_escalation_vote: bool = False,
) -> tuple[ApprovalVote, bool]:
    """
    Cast a vote on an approval request.

    Enforces the four-eye principle: the requester cannot vote on their own request.

    Args:
        db: Database session
        approval_id: ID of the approval to vote on
        user_id: ID of the user casting the vote
        user_name: Display name of the voter
        vote: Vote type ("approve" or "reject")
        comment: Optional comment explaining the vote
        is_escalation_vote: Whether this vote is from an escalation role member

    Returns:
        Tuple of (ApprovalVote, is_complete) where is_complete indicates
        if the approval is now resolved (approved or rejected)

    Raises:
        ApprovalNotFoundError: If the approval doesn't exist
        UserCannotVoteError: If the user is not allowed to vote
        ValueError: If vote is not "approve" or "reject"
    """
    if vote not in ("approve", "reject"):
        raise ValueError(f"Vote must be 'approve' or 'reject', got: {vote}")

    # Load approval with votes
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise ApprovalNotFoundError(approval_id)

    # Check if approval is still pending
    if approval.status != "pending":
        raise UserCannotVoteError(f"Approval is not pending (status: {approval.status})")

    # Check expiration
    if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at.replace(
        tzinfo=timezone.utc
    ):
        approval.status = "expired"
        approval.resolved_at = datetime.now(timezone.utc)
        await db.flush()
        raise UserCannotVoteError("Approval has expired")

    # Enforce four-eye principle: requester cannot vote on their own request
    if user_id and approval.requester_id == user_id:
        raise UserCannotVoteError("You cannot vote on your own request (four-eye principle)")

    if user_name == approval.requester_name:
        raise UserCannotVoteError("You cannot vote on your own request (four-eye principle)")

    # Check if user has already voted
    for existing_vote in approval.votes:
        if existing_vote.user_id == user_id or existing_vote.user_name == user_name:
            raise UserCannotVoteError("You have already voted on this request")

    # Create the vote
    approval_vote = ApprovalVote(
        approval_id=approval_id,
        user_id=user_id,
        user_name=user_name,
        vote=vote,
        comment=comment,
        is_escalation_vote=is_escalation_vote,
    )
    db.add(approval_vote)
    await db.flush()

    # Refresh to get updated votes list
    await db.refresh(approval, ["votes"])

    # Check if approval threshold is met
    approve_count = sum(1 for v in approval.votes if v.vote == "approve")
    reject_count = sum(1 for v in approval.votes if v.vote == "reject")

    is_complete = False

    if approve_count >= approval.required_approvers:
        approval.status = "approved"
        approval.resolved_at = datetime.now(timezone.utc)
        is_complete = True
        logger.info(f"Approval {approval_id} approved with {approve_count} votes")
    elif reject_count >= approval.required_approvers:
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        is_complete = True
        logger.info(f"Approval {approval_id} rejected with {reject_count} votes")
    else:
        logger.debug(
            f"Vote recorded on approval {approval_id}: "
            f"{approve_count} approvals, {reject_count} rejections "
            f"(need {approval.required_approvers})"
        )

    await db.flush()

    return approval_vote, is_complete


async def check_user_can_approve(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
) -> tuple[bool, str]:
    """
    Check if a user can approve/vote on a request.

    A user can vote if:
    - They are not the requester (four-eye principle)
    - They have not already voted
    - The approval is still pending
    - The approval has not expired

    Args:
        db: Database session
        approval_id: ID of the approval to check
        user_id: ID of the user to check

    Returns:
        Tuple of (can_approve, reason) where reason explains why if can_approve is False
    """
    # Load approval with votes
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        return False, "Approval not found"

    # Check if approval is still pending
    if approval.status != "pending":
        return False, f"Approval is not pending (status: {approval.status})"

    # Check expiration
    if approval.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return False, "Approval has expired"

    # Check four-eye principle
    if approval.requester_id == user_id:
        return False, "You cannot vote on your own request"

    # Check if already voted
    for vote in approval.votes:
        if vote.user_id == user_id:
            return False, "You have already voted on this request"

    return True, "User can vote"


async def get_pending_approvals_for_user(
    db: AsyncSession,
    user_id: str,
) -> list[Approval]:
    """
    Get approvals pending this user's vote.

    Returns approvals where:
    - Status is pending
    - User is not the requester
    - User has not already voted
    - Approval has not expired

    Args:
        db: Database session
        user_id: ID of the user

    Returns:
        List of Approval objects the user can vote on
    """
    # Get all pending approvals with their votes
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.status == "pending")
        .order_by(Approval.created_at.desc())
    )
    all_pending = result.scalars().all()

    # Filter to approvals user can vote on
    now = datetime.now(timezone.utc)
    pending_for_user = []

    for approval in all_pending:
        # Skip if user is the requester
        if approval.requester_id == user_id:
            continue

        # Skip if expired
        if approval.expires_at:
            expires_at = approval.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                continue

        # Skip if user already voted
        user_voted = any(v.user_id == user_id for v in approval.votes)
        if user_voted:
            continue

        pending_for_user.append(approval)

    return pending_for_user


async def escalate_approval(
    db: AsyncSession,
    approval: Approval,
) -> None:
    """
    Escalate an approval to the escalation role.

    Updates the escalation tracking fields and resets the expiration timer
    for a new timeout period.

    Args:
        db: Database session
        approval: The approval to escalate
    """
    now = datetime.now(timezone.utc)

    # Update escalation tracking
    approval.escalated_at = now
    approval.escalation_count += 1

    # Get the rule to determine new timeout
    if approval.rule_id:
        result = await db.execute(
            select(ApprovalRule).where(ApprovalRule.id == approval.rule_id)
        )
        rule = result.scalar_one_or_none()
        if rule:
            # Reset expires_at for new timeout period
            approval.expires_at = now + timedelta(hours=rule.escalation_timeout_hours)

    await db.flush()

    logger.info(
        f"Escalated approval {approval.id} (escalation count: {approval.escalation_count})"
    )


async def get_expired_approvals(
    db: AsyncSession,
) -> list[Approval]:
    """
    Get approvals that have expired and need escalation or auto-rejection.

    Returns approvals where:
    - Status is pending
    - expires_at has passed

    Args:
        db: Database session

    Returns:
        List of expired Approval objects
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes), selectinload(Approval.rule))
        .where(Approval.status == "pending")
        .where(Approval.expires_at < now)
    )

    return list(result.scalars().all())


async def process_expired_approvals(
    db: AsyncSession,
    max_escalations: int = 3,
) -> tuple[int, int]:
    """
    Process expired approvals by escalating or rejecting them.

    Approvals that have not reached max_escalations will be escalated.
    Approvals that have reached max_escalations will be auto-rejected.

    Args:
        db: Database session
        max_escalations: Maximum number of escalations before auto-rejection

    Returns:
        Tuple of (escalated_count, rejected_count)
    """
    expired = await get_expired_approvals(db)

    escalated_count = 0
    rejected_count = 0

    for approval in expired:
        if approval.escalation_count < max_escalations:
            # Escalate the approval
            await escalate_approval(db, approval)
            escalated_count += 1
        else:
            # Auto-reject after max escalations
            approval.status = "expired"
            approval.resolved_at = datetime.now(timezone.utc)
            rejected_count += 1
            logger.info(
                f"Auto-rejected approval {approval.id} after {approval.escalation_count} escalations"
            )

    await db.flush()

    return escalated_count, rejected_count


async def get_approval_with_details(
    db: AsyncSession,
    approval_id: str,
) -> Approval | None:
    """
    Get an approval with all related data loaded.

    Args:
        db: Database session
        approval_id: ID of the approval to retrieve

    Returns:
        Approval with votes and rule loaded, or None if not found
    """
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes), selectinload(Approval.rule))
        .where(Approval.id == approval_id)
    )
    return result.scalar_one_or_none()


async def cancel_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
) -> Approval:
    """
    Cancel an approval request (only the requester can cancel).

    Args:
        db: Database session
        approval_id: ID of the approval to cancel
        user_id: ID of the user attempting to cancel

    Returns:
        The cancelled Approval

    Raises:
        ApprovalNotFoundError: If approval doesn't exist
        UserCannotVoteError: If user is not the requester or approval is not pending
    """
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise ApprovalNotFoundError(approval_id)

    if approval.status != "pending":
        raise UserCannotVoteError(f"Only pending approvals can be cancelled (status: {approval.status})")

    if approval.requester_id != user_id:
        raise UserCannotVoteError("Only the requester can cancel an approval")

    approval.status = "cancelled"
    approval.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Approval {approval_id} cancelled by requester {user_id}")

    return approval
