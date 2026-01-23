# Issue 006: Implement Bulk Change State Endpoint

**Priority:** HIGH
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend BulkActionBar component calls `POST /api/v1/nodes/bulk/change-state` to change the state of multiple nodes. This endpoint does not exist in the backend.

## Current Behavior

Frontend calls non-existent endpoint, resulting in 404 error.

**Frontend location:** `frontend/src/api/nodes.ts:81-86`
```typescript
async bulkChangeState(nodeIds: string[], newState: string): Promise<ApiResponse<{ updated: number; failed: number }>> {
  return apiClient.post<ApiResponse<{ updated: number; failed: number }>>('/nodes/bulk/change-state', {
    node_ids: nodeIds,
    new_state: newState,
  })
}
```

## Expected Behavior

New endpoint: `POST /api/v1/nodes/bulk/change-state`

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "new_state": "pending"
}
```

**Response (Success):**
```json
{
  "success": true,
  "data": {
    "updated": 2,
    "failed": 1,
    "errors": [
      {
        "node_id": "uuid3",
        "error": "Invalid state transition from 'active' to 'pending'"
      }
    ]
  },
  "message": "Changed state for 2 nodes, 1 failed"
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
class BulkChangeStateRequest(BaseModel):
    node_ids: list[str]
    new_state: str

class BulkChangeStateError(BaseModel):
    node_id: str
    error: str

class BulkChangeStateResult(BaseModel):
    updated: int
    failed: int
    errors: list[BulkChangeStateError]

@router.post("/nodes/bulk/change-state", response_model=ApiResponse[BulkChangeStateResult])
async def bulk_change_state(
    request: BulkChangeStateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Change state for multiple nodes with individual validation."""
    # Validate target state is valid
    valid_states = ['discovered', 'ignored', 'pending', 'installing', 'installed',
                    'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping']
    if request.new_state not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state: {request.new_state}")

    # Get all nodes
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.id.in_(request.node_ids))
    )
    nodes = result.scalars().all()

    updated = 0
    errors = []

    for node in nodes:
        try:
            await StateTransitionService.transition(
                db=db,
                node=node,
                to_state=request.new_state,
                triggered_by="bulk_operation",
            )
            updated += 1
        except (InvalidStateTransition, ValueError) as e:
            errors.append(BulkChangeStateError(
                node_id=node.id,
                error=str(e),
            ))

    await db.flush()

    return ApiResponse(
        data=BulkChangeStateResult(
            updated=updated,
            failed=len(errors),
            errors=errors,
        ),
        message=f"Changed state for {updated} node(s), {len(errors)} failed",
    )
```

## Acceptance Criteria

- [ ] Endpoint accepts list of node IDs and target state
- [ ] Validates target state is a valid state name
- [ ] Validates each transition individually using state machine
- [ ] Invalid transitions are reported but don't stop others
- [ ] Returns detailed error list for failed transitions
- [ ] Logs state transitions in NodeStateLog
- [ ] Transaction commits only successful transitions

## Related Files

- `frontend/src/api/nodes.ts`
- `frontend/src/hooks/useBulkActions.ts`
- `frontend/src/components/nodes/BulkActionBar.tsx`
- `src/api/routes/nodes.py`
- `src/core/state_machine.py`
- `src/core/state_service.py`
