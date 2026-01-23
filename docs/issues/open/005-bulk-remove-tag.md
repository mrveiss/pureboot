# Issue 005: Implement Bulk Remove Tag Endpoint

**Priority:** MEDIUM
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend has API methods to bulk remove tags from nodes, but the backend endpoint does not exist.

## Current Behavior

Frontend calls non-existent endpoint, resulting in 404 error.

**Frontend location:** `frontend/src/api/nodes.ts:74-79`
```typescript
async bulkRemoveTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
  return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/remove-tag', {
    node_ids: nodeIds,
    tag,
  })
}
```

## Expected Behavior

New endpoint: `POST /api/v1/nodes/bulk/remove-tag`

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "tag": "staging"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "updated": 2
  },
  "message": "Removed tag 'staging' from 2 nodes"
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
class BulkRemoveTagRequest(BaseModel):
    node_ids: list[str]
    tag: str

@router.post("/nodes/bulk/remove-tag", response_model=ApiResponse[dict])
async def bulk_remove_tag(
    request: BulkRemoveTagRequest,
    db: AsyncSession = Depends(get_db),
):
    """Remove a tag from multiple nodes."""
    tag_lower = request.tag.lower().strip()
    if not tag_lower:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")

    # Delete matching tags
    result = await db.execute(
        delete(NodeTag)
        .where(NodeTag.node_id.in_(request.node_ids))
        .where(NodeTag.tag == tag_lower)
    )

    deleted = result.rowcount

    return ApiResponse(
        data={"updated": deleted},
        message=f"Removed tag '{tag_lower}' from {deleted} node(s)",
    )
```

## Acceptance Criteria

- [ ] Endpoint accepts list of node IDs and tag string
- [ ] Tag matching is case-insensitive
- [ ] Returns count of tags actually removed
- [ ] Non-existent node IDs are silently skipped
- [ ] Nodes without the tag are silently skipped
- [ ] Empty tag returns 400 error

## Related Files

- `frontend/src/api/nodes.ts`
- `frontend/src/hooks/useBulkActions.ts`
- `src/api/routes/nodes.py`
- `src/db/models.py` (NodeTag model)
