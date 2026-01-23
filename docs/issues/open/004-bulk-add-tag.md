# Issue 004: Implement Bulk Add Tag Endpoint

**Priority:** HIGH
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend BulkActionBar component calls `POST /api/v1/nodes/bulk/add-tag` to add a tag to multiple nodes. This endpoint does not exist in the backend.

## Current Behavior

Frontend calls non-existent endpoint, resulting in 404 error.

**Frontend location:** `frontend/src/api/nodes.ts:67-73`
```typescript
async bulkAddTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
  return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/add-tag', {
    node_ids: nodeIds,
    tag,
  })
}
```

## Expected Behavior

New endpoint: `POST /api/v1/nodes/bulk/add-tag`

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "tag": "production"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "updated": 3
  },
  "message": "Added tag 'production' to 3 nodes"
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
class BulkAddTagRequest(BaseModel):
    node_ids: list[str]
    tag: str

@router.post("/nodes/bulk/add-tag", response_model=ApiResponse[dict])
async def bulk_add_tag(
    request: BulkAddTagRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a tag to multiple nodes."""
    tag_lower = request.tag.lower().strip()
    if not tag_lower:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")

    # Get existing tags to avoid duplicates
    existing = await db.execute(
        select(NodeTag.node_id)
        .where(NodeTag.node_id.in_(request.node_ids))
        .where(NodeTag.tag == tag_lower)
    )
    existing_node_ids = {row[0] for row in existing.all()}

    # Add tags only to nodes that don't have it
    nodes_to_tag = set(request.node_ids) - existing_node_ids

    for node_id in nodes_to_tag:
        db.add(NodeTag(node_id=node_id, tag=tag_lower))

    await db.flush()

    return ApiResponse(
        data={"updated": len(nodes_to_tag)},
        message=f"Added tag '{tag_lower}' to {len(nodes_to_tag)} node(s)",
    )
```

## Acceptance Criteria

- [ ] Endpoint accepts list of node IDs and tag string
- [ ] Tag is normalized to lowercase
- [ ] Skips nodes that already have the tag (no duplicates)
- [ ] Returns count of nodes actually updated
- [ ] Non-existent node IDs are silently skipped
- [ ] Empty tag returns 400 error

## Related Files

- `frontend/src/api/nodes.ts`
- `frontend/src/hooks/useBulkActions.ts`
- `frontend/src/components/nodes/BulkActionBar.tsx`
- `src/api/routes/nodes.py`
- `src/db/models.py` (NodeTag model)
