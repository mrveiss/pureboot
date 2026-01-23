# Issue 002: Implement Bulk Assign Group Endpoint

**Priority:** HIGH
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend BulkActionBar component calls `POST /api/v1/nodes/bulk/assign-group` to assign multiple nodes to a device group. This endpoint does not exist in the backend.

## Current Behavior

Frontend calls non-existent endpoint, resulting in 404 error.

**Frontend location:** `frontend/src/api/nodes.ts:53-58`
```typescript
async bulkAssignGroup(nodeIds: string[], groupId: string | null): Promise<ApiResponse<{ updated: number }>> {
  return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-group', {
    node_ids: nodeIds,
    group_id: groupId,
  })
}
```

## Expected Behavior

New endpoint: `POST /api/v1/nodes/bulk/assign-group`

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "group_id": "group-uuid"
}
```

To unassign from group:
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "group_id": null
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "updated": 3
  },
  "message": "Assigned 3 nodes to group"
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
class BulkAssignGroupRequest(BaseModel):
    node_ids: list[str]
    group_id: str | None = None

@router.post("/nodes/bulk/assign-group", response_model=ApiResponse[dict])
async def bulk_assign_group(
    request: BulkAssignGroupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign multiple nodes to a device group."""
    # Validate group exists if provided
    if request.group_id:
        group_result = await db.execute(
            select(DeviceGroup).where(DeviceGroup.id == request.group_id)
        )
        if not group_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Group not found")

    # Update nodes
    result = await db.execute(
        update(Node)
        .where(Node.id.in_(request.node_ids))
        .values(group_id=request.group_id)
    )

    updated = result.rowcount

    action = "assigned to group" if request.group_id else "unassigned from group"
    return ApiResponse(
        data={"updated": updated},
        message=f"{updated} node(s) {action}",
    )
```

## Acceptance Criteria

- [ ] Endpoint accepts list of node IDs and group ID
- [ ] Validates group exists before assignment
- [ ] Allows `null` group_id to unassign
- [ ] Returns count of updated nodes
- [ ] Non-existent node IDs are silently skipped
- [ ] Transaction is atomic

## Related Files

- `frontend/src/api/nodes.ts`
- `frontend/src/hooks/useBulkActions.ts`
- `frontend/src/components/nodes/BulkActionBar.tsx`
- `src/api/routes/nodes.py`
