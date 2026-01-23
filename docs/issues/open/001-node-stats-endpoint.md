# Issue 001: Implement Node Stats Endpoint

**Priority:** HIGH
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend Dashboard requires a dedicated stats endpoint to efficiently retrieve node statistics. Currently, the frontend fetches ALL nodes and computes stats client-side, which is inefficient and will fail at scale.

## Current Behavior

Frontend hook `useNodeStats()` in `frontend/src/hooks/useNodes.ts:30-61`:
```typescript
queryFn: async (): Promise<NodeStats> => {
  // This will call a stats endpoint when available
  // For now, compute from list
  const response = await nodesApi.list({ limit: 1000 })
  const nodes = response.data
  // ... client-side aggregation
}
```

## Expected Behavior

New endpoint: `GET /api/v1/nodes/stats`

**Response:**
```json
{
  "success": true,
  "data": {
    "total": 150,
    "by_state": {
      "discovered": 5,
      "ignored": 0,
      "pending": 10,
      "installing": 3,
      "installed": 2,
      "active": 120,
      "reprovision": 2,
      "migrating": 0,
      "retired": 8,
      "decommissioned": 0,
      "wiping": 0
    },
    "discovered_last_hour": 2,
    "installing_count": 3
  }
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
@router.get("/nodes/stats", response_model=ApiResponse[NodeStatsResponse])
async def get_node_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated node statistics."""
    from sqlalchemy import func, case
    from datetime import datetime, timedelta, timezone

    # Total count
    total_result = await db.execute(select(func.count()).select_from(Node))
    total = total_result.scalar() or 0

    # Count by state
    state_counts = await db.execute(
        select(Node.state, func.count())
        .group_by(Node.state)
    )
    by_state = dict(state_counts.all())

    # Discovered in last hour
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    discovered_result = await db.execute(
        select(func.count())
        .select_from(Node)
        .where(Node.state == 'discovered')
        .where(Node.created_at >= one_hour_ago)
    )
    discovered_last_hour = discovered_result.scalar() or 0

    return ApiResponse(
        data=NodeStatsResponse(
            total=total,
            by_state=by_state,
            discovered_last_hour=discovered_last_hour,
            installing_count=by_state.get('installing', 0),
        )
    )
```

**Schema addition in `src/api/schemas.py`:**
```python
class NodeStatsResponse(BaseModel):
    total: int
    by_state: dict[str, int]
    discovered_last_hour: int
    installing_count: int
```

## Acceptance Criteria

- [ ] Endpoint returns correct total count
- [ ] Endpoint returns correct counts per state
- [ ] Endpoint returns discovered_last_hour count
- [ ] Response time < 100ms for 10,000 nodes
- [ ] Frontend `useNodeStats()` updated to call endpoint

## Related Files

- `frontend/src/hooks/useNodes.ts`
- `frontend/src/pages/Dashboard.tsx`
- `src/api/routes/nodes.py`
- `src/api/schemas.py`
