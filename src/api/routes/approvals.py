"""Approvals API endpoints for four-eye principle."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import Approval, ApprovalVote
from src.services.approvals import (
    ApprovalNotFoundError,
    UserCannotVoteError,
    cancel_approval as service_cancel_approval,
    cast_vote as service_cast_vote,
    get_approval_with_details,
    get_pending_approvals_for_user,
)
from src.services.audit import audit_action

router = APIRouter()

# Default expiration time
APPROVAL_EXPIRY_HOURS = 24


# --- Schemas ---

class ApprovalCreate(BaseModel):
    """Request to create an approval."""
    action_type: str  # bulk_wipe, bulk_retire, delete_template, etc.
    action_data: dict
    requester_name: str
    requester_id: str | None = None
    required_approvers: int = 2


class VoteCreate(BaseModel):
    """Request to vote on an approval."""
    vote: str  # "approve" or "reject"
    comment: str | None = None


class LegacyVoteCreate(BaseModel):
    """Legacy request to vote on an approval (for backwards compatibility)."""
    user_name: str
    user_id: str | None = None
    comment: str | None = None


class VoteResponse(BaseModel):
    """Single vote response."""
    id: str
    user_id: str | None
    user_name: str
    vote: str
    comment: str | None
    is_escalation_vote: bool = False
    created_at: str


class ApprovalResponse(BaseModel):
    """Approval response."""
    id: str
    action_type: str
    action_data: dict
    requester_id: str | None
    requester_name: str
    status: str
    required_approvers: int
    current_approvals: int
    current_rejections: int
    expires_at: str
    resolved_at: str | None
    created_at: str
    votes: list[VoteResponse]

    @classmethod
    def from_approval(cls, approval: Approval) -> "ApprovalResponse":
        votes = [
            VoteResponse(
                id=v.id,
                user_id=v.user_id,
                user_name=v.user_name,
                vote=v.vote,
                comment=v.comment,
                is_escalation_vote=v.is_escalation_vote,
                created_at=v.created_at.isoformat() if v.created_at else "",
            )
            for v in approval.votes
        ]
        current_approvals = sum(1 for v in approval.votes if v.vote == "approve")
        current_rejections = sum(1 for v in approval.votes if v.vote == "reject")

        return cls(
            id=approval.id,
            action_type=approval.action_type,
            action_data=json.loads(approval.action_data_json),
            requester_id=approval.requester_id,
            requester_name=approval.requester_name,
            status=approval.status,
            required_approvers=approval.required_approvers,
            current_approvals=current_approvals,
            current_rejections=current_rejections,
            expires_at=approval.expires_at.isoformat() if approval.expires_at else "",
            resolved_at=approval.resolved_at.isoformat() if approval.resolved_at else None,
            created_at=approval.created_at.isoformat() if approval.created_at else "",
            votes=votes,
        )


class ApprovalListResponse(BaseModel):
    """Response for approval list."""
    data: list[ApprovalResponse]
    total: int


class ApprovalStatsResponse(BaseModel):
    """Approval statistics."""
    pending_count: int


class ApprovalDetailResponse(BaseModel):
    """Detailed approval response with additional context."""
    id: str
    requester_id: str | None
    requester_username: str
    target_type: str | None
    target_id: str | None
    description: str | None
    status: str
    operation_type: str
    required_approvers: int
    escalation_count: int
    expires_at: str | None
    votes: list[VoteResponse]
    created_at: str
    updated_at: str | None

    @classmethod
    def from_approval(cls, approval: Approval) -> "ApprovalDetailResponse":
        """Create detail response from approval model."""
        votes = [
            VoteResponse(
                id=v.id,
                user_id=v.user_id,
                user_name=v.user_name,
                vote=v.vote,
                comment=v.comment,
                is_escalation_vote=v.is_escalation_vote,
                created_at=v.created_at.isoformat() if v.created_at else "",
            )
            for v in approval.votes
        ]

        # Parse action_data for target info
        try:
            action_data = json.loads(approval.action_data_json)
        except (json.JSONDecodeError, TypeError):
            action_data = {}

        return cls(
            id=approval.id,
            requester_id=approval.requester_id,
            requester_username=approval.requester_name,
            target_type=action_data.get("target_type"),
            target_id=action_data.get("target_id"),
            description=action_data.get("description"),
            status=approval.status,
            operation_type=approval.operation_type,
            required_approvers=approval.required_approvers,
            escalation_count=approval.escalation_count,
            expires_at=approval.expires_at.isoformat() if approval.expires_at else None,
            votes=votes,
            created_at=approval.created_at.isoformat() if approval.created_at else "",
            updated_at=None,  # Model doesn't have updated_at
        )


class VoteResultResponse(BaseModel):
    """Response for voting on an approval."""
    success: bool = True
    message: str
    vote: VoteResponse
    is_complete: bool
    approval_status: str


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: ApprovalResponse | None = None


# --- Endpoints ---

VALID_ACTION_TYPES = {
    "bulk_wipe",
    "bulk_retire",
    "delete_template",
    "production_state_change",
}


@router.get("/approvals/stats", response_model=ApprovalStatsResponse)
async def get_approval_stats(db: AsyncSession = Depends(get_db)):
    """Get approval statistics (pending count for sidebar badge)."""
    # Expire old approvals first
    await _expire_old_approvals(db)

    result = await db.execute(
        select(func.count()).select_from(Approval).where(Approval.status == "pending")
    )
    pending_count = result.scalar() or 0

    return ApprovalStatsResponse(pending_count=pending_count)


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    status: str | None = Query(None, description="Filter by status (pending, approved, rejected)"),
    requester_name: str | None = Query(None, description="Filter by requester"),
    my_pending: bool = Query(False, description="Only show approvals awaiting my vote"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """List approval requests.

    Args:
        status: Filter by approval status (pending, approved, rejected, expired, cancelled)
        requester_name: Filter by requester username
        my_pending: If True, only show pending approvals that the current user can vote on
        limit: Maximum number of results to return
        offset: Number of results to skip
    """
    # Expire old approvals first
    await _expire_old_approvals(db)

    # Handle my_pending filter using service layer
    if my_pending:
        # Try to get user_id from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None) if request else None
        if not user_id:
            # Fallback: require authentication for this filter
            raise HTTPException(
                status_code=401,
                detail="Authentication required for my_pending filter"
            )

        pending_approvals = await get_pending_approvals_for_user(db, user_id)
        # Apply pagination
        total = len(pending_approvals)
        paginated = pending_approvals[offset:offset + limit]

        return ApprovalListResponse(
            data=[ApprovalResponse.from_approval(a) for a in paginated],
            total=total,
        )

    query = select(Approval).options(selectinload(Approval.votes))

    if status:
        query = query.where(Approval.status == status)
    if requester_name:
        query = query.where(Approval.requester_name == requester_name)

    # Count total
    count_query = select(func.count()).select_from(Approval)
    if status:
        count_query = count_query.where(Approval.status == status)
    if requester_name:
        count_query = count_query.where(Approval.requester_name == requester_name)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get paginated results
    query = query.order_by(Approval.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    approvals = result.scalars().all()

    return ApprovalListResponse(
        data=[ApprovalResponse.from_approval(a) for a in approvals],
        total=total,
    )


@router.get("/approvals/history", response_model=ApprovalListResponse)
async def get_approval_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get completed/expired/rejected approvals."""
    query = (
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.status.in_(["approved", "rejected", "expired", "cancelled"]))
        .order_by(Approval.resolved_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    approvals = result.scalars().all()

    count_result = await db.execute(
        select(func.count())
        .select_from(Approval)
        .where(Approval.status.in_(["approved", "rejected", "expired", "cancelled"]))
    )
    total = count_result.scalar() or 0

    return ApprovalListResponse(
        data=[ApprovalResponse.from_approval(a) for a in approvals],
        total=total,
    )


@router.get("/approvals/{approval_id}", response_model=ApiResponse)
async def get_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get approval details."""
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    return ApiResponse(data=ApprovalResponse.from_approval(approval))


@router.post("/approvals", response_model=ApiResponse, status_code=201)
async def create_approval(
    data: ApprovalCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new approval request."""
    if data.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action type. Must be one of: {', '.join(VALID_ACTION_TYPES)}",
        )

    if data.required_approvers < 1 or data.required_approvers > 5:
        raise HTTPException(
            status_code=400,
            detail="Required approvers must be between 1 and 5",
        )

    expires_at = datetime.now(timezone.utc) + timedelta(hours=APPROVAL_EXPIRY_HOURS)

    approval = Approval(
        action_type=data.action_type,
        operation_type=data.action_type,  # Use action_type as operation_type for legacy compatibility
        action_data_json=json.dumps(data.action_data),
        requester_id=data.requester_id,
        requester_name=data.requester_name,
        required_approvers=data.required_approvers,
        expires_at=expires_at,
    )
    db.add(approval)
    await db.flush()
    await db.refresh(approval, ["votes"])

    return ApiResponse(
        data=ApprovalResponse.from_approval(approval),
        message="Approval request created",
    )


@router.post("/approvals/{approval_id}/vote", response_model=VoteResultResponse)
async def vote_on_approval(
    approval_id: str,
    data: VoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Cast a vote on an approval request.

    Uses the authenticated user from the request context. The vote type
    (approve or reject) is specified in the request body.
    """
    # Validate vote type
    if data.vote not in ("approve", "reject"):
        raise HTTPException(
            status_code=400,
            detail="Vote must be 'approve' or 'reject'"
        )

    # Get current user from auth middleware
    user_id = getattr(request.state, "user_id", None)
    user_name = getattr(request.state, "username", None)

    if not user_id or not user_name:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        vote_obj, is_complete = await service_cast_vote(
            db=db,
            approval_id=approval_id,
            user_id=user_id,
            user_name=user_name,
            vote=data.vote,
            comment=data.comment,
            is_escalation_vote=False,
        )

        # Get the updated approval for status
        approval = await get_approval_with_details(db, approval_id)
        approval_status = approval.status if approval else "unknown"

        # Audit vote
        await audit_action(
            db, request,
            action="vote",
            resource_type="approval",
            resource_id=approval_id,
            details={"vote": data.vote, "comment": data.comment},
            result="success",
        )

        return VoteResultResponse(
            success=True,
            message=f"Vote recorded: {data.vote}",
            vote=VoteResponse(
                id=vote_obj.id,
                user_id=vote_obj.user_id,
                user_name=vote_obj.user_name,
                vote=vote_obj.vote,
                comment=vote_obj.comment,
                is_escalation_vote=vote_obj.is_escalation_vote,
                created_at=vote_obj.created_at.isoformat() if vote_obj.created_at else "",
            ),
            is_complete=is_complete,
            approval_status=approval_status,
        )

    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="Approval not found")
    except UserCannotVoteError as e:
        raise HTTPException(status_code=400, detail=e.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/approvals/{approval_id}/approve", response_model=ApiResponse)
async def approve_request(
    approval_id: str,
    data: LegacyVoteCreate,
    db: AsyncSession = Depends(get_db),
):
    """Vote to approve a request (legacy endpoint - use /vote instead)."""
    return await _cast_vote(approval_id, data, "approve", db)


@router.post("/approvals/{approval_id}/reject", response_model=ApiResponse)
async def reject_request(
    approval_id: str,
    data: LegacyVoteCreate,
    db: AsyncSession = Depends(get_db),
):
    """Vote to reject a request (legacy endpoint - use /vote instead)."""
    return await _cast_vote(approval_id, data, "reject", db)


@router.post("/approvals/{approval_id}/cancel", response_model=ApiResponse)
async def cancel_approval_post(
    approval_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Cancel an approval request (requester only).

    Uses authenticated user from request context. Only the requester
    can cancel their own pending approval.
    """
    # Get current user from auth middleware
    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        approval = await service_cancel_approval(db, approval_id, user_id)
        return ApiResponse(
            data=ApprovalResponse.from_approval(approval),
            message="Approval request cancelled",
        )
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="Approval not found")
    except UserCannotVoteError as e:
        raise HTTPException(status_code=403, detail=e.reason)


@router.delete("/approvals/{approval_id}", response_model=ApiResponse)
async def cancel_approval_delete(
    approval_id: str,
    requester_name: str = Query(..., description="Must match original requester"),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an approval request (legacy endpoint - use POST /cancel instead)."""
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending approvals can be cancelled")

    if approval.requester_name != requester_name:
        raise HTTPException(status_code=403, detail="Only the requester can cancel this approval")

    approval.status = "cancelled"
    approval.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(approval, ["votes"])

    return ApiResponse(
        data=ApprovalResponse.from_approval(approval),
        message="Approval request cancelled",
    )


async def _cast_vote(
    approval_id: str,
    data: LegacyVoteCreate,
    vote_type: str,
    db: AsyncSession,
) -> ApiResponse:
    """Internal function to cast a vote (legacy implementation)."""
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="This approval is no longer pending")

    # Check if user already voted
    for vote in approval.votes:
        if vote.user_name == data.user_name:
            raise HTTPException(status_code=400, detail="You have already voted on this request")

    # Check if requester is trying to approve their own request
    if data.user_name == approval.requester_name:
        raise HTTPException(status_code=400, detail="You cannot vote on your own request")

    # Check expiration
    if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at.replace(tzinfo=timezone.utc):
        approval.status = "expired"
        approval.resolved_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=400, detail="This approval request has expired")

    # Cast vote
    vote = ApprovalVote(
        approval_id=approval.id,
        user_id=data.user_id,
        user_name=data.user_name,
        vote=vote_type,
        comment=data.comment,
    )
    db.add(vote)
    await db.flush()

    # Refresh to get updated votes
    await db.refresh(approval, ["votes"])

    # Check if approval threshold reached
    approve_count = sum(1 for v in approval.votes if v.vote == "approve")
    reject_count = sum(1 for v in approval.votes if v.vote == "reject")

    message = f"Vote recorded ({vote_type})"

    if approve_count >= approval.required_approvers:
        approval.status = "approved"
        approval.resolved_at = datetime.now(timezone.utc)
        message = "Approval request approved"
        # TODO: Execute the approved action
    elif reject_count >= approval.required_approvers:
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        message = "Approval request rejected"

    await db.flush()
    await db.refresh(approval, ["votes"])

    return ApiResponse(
        data=ApprovalResponse.from_approval(approval),
        message=message,
    )


async def _expire_old_approvals(db: AsyncSession):
    """Mark expired approvals."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Approval)
        .where(Approval.status == "pending")
        .where(Approval.expires_at < now)
    )
    expired = result.scalars().all()

    for approval in expired:
        approval.status = "expired"
        approval.resolved_at = now

    if expired:
        await db.flush()
