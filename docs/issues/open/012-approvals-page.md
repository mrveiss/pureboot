# Issue 012: Implement Approvals Page and API

**Priority:** MEDIUM
**Type:** Full Stack Feature
**Component:** Frontend + Backend
**Status:** Open

---

## Summary

The Approvals page shows "Coming Soon" placeholder. Per the PRD, PureBoot implements a "four-eye principle" requiring approval for sensitive operations on production nodes.

## Current Behavior

**Router:** `frontend/src/router.tsx:27`
```typescript
{ path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
```

**Sidebar shows:** Pending approvals badge (currently hardcoded to 3)

## PRD Requirement

From CLAUDE.md:
```python
class ApprovalSystem:
    def __init__(self):
        self.pending_actions = {}

    def request_approval(self, action, requester):
        # Creates approval request

    def approve_action(self, approval_id, approver):
        # Requires 2+ approvers
```

## Expected Functionality

### Approval Workflow

1. User initiates sensitive action (bulk state change, wipe, etc.)
2. System creates approval request
3. Other users (with approval permission) see pending request
4. 2+ approvers must approve
5. Action executes after approval threshold met

### Backend API Design

```
GET    /api/v1/approvals                    - List pending approvals
GET    /api/v1/approvals/{id}               - Get approval details
POST   /api/v1/approvals                    - Create approval request
POST   /api/v1/approvals/{id}/approve       - Approve action
POST   /api/v1/approvals/{id}/reject        - Reject action
DELETE /api/v1/approvals/{id}               - Cancel request (requester only)
GET    /api/v1/approvals/history            - Get completed approvals
```

### Approval Model

```python
class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String, primary_key=True, default=generate_uuid)
    action_type = Column(String, nullable=False)  # bulk_state_change, wipe, retire, etc.
    action_data = Column(JSON)  # Serialized action parameters
    requester_id = Column(String)  # User who requested
    requester_name = Column(String)
    status = Column(String, default="pending")  # pending, approved, rejected, cancelled, expired
    required_approvers = Column(Integer, default=2)
    expires_at = Column(DateTime)  # Auto-expire after 24h
    created_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime)

class ApprovalVote(Base):
    __tablename__ = "approval_votes"

    id = Column(String, primary_key=True, default=generate_uuid)
    approval_id = Column(String, ForeignKey("approvals.id"))
    user_id = Column(String)
    user_name = Column(String)
    vote = Column(String)  # approve, reject
    comment = Column(Text)
    created_at = Column(DateTime, default=utcnow)
```

### Frontend Page Features

1. **Pending Tab:** List approvals awaiting votes
2. **My Requests Tab:** User's own pending requests
3. **History Tab:** Completed/expired approvals
4. Approve/Reject buttons with comment field
5. Real-time updates via WebSocket
6. Notification badge in sidebar

### Integration Points

Actions requiring approval:
- Bulk state change to `wiping`
- Bulk state change to `retired`
- Any action on nodes in "production" group
- Template deletion
- Workflow deletion

## Implementation Steps

### Phase 1: Backend
1. Create Approval and ApprovalVote models
2. Create approval service with business logic
3. Create CRUD endpoints
4. Integrate with bulk operations
5. Add WebSocket notifications

### Phase 2: Frontend
1. Create types
2. Create API client
3. Create hooks with real-time updates
4. Create Approvals page with tabs
5. Update sidebar badge to use real count
6. Add approval dialogs to bulk operations

## Acceptance Criteria

- [ ] Sensitive actions create approval requests
- [ ] Multiple users can vote approve/reject
- [ ] Action executes when threshold met
- [ ] Requests expire after 24 hours
- [ ] Real-time updates for pending approvals
- [ ] Audit trail of all approvals

## Related Files

- `frontend/src/router.tsx`
- `frontend/src/components/layout/Sidebar.tsx` (badge)
- `src/db/models.py`
- `src/api/routes/approvals.py` (new)
- `src/core/approval_service.py` (new)

## Dependencies

- User authentication system (Issue 014)
- WebSocket support (exists)
