# Issue 013: Implement Activity Log Page

**Priority:** MEDIUM
**Type:** Frontend Feature (Backend Partial)
**Component:** Frontend - Pages
**Status:** Open

---

## Summary

The Activity Log page shows "Coming Soon" placeholder. The backend has node-level events and state history, but needs a global activity/audit log endpoint.

## Current Behavior

**Router:** `frontend/src/router.tsx:28`
```typescript
{ path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
```

## Backend Status - Partial

Existing endpoints:
- `GET /api/v1/nodes/{id}/events` - Node-specific events
- `GET /api/v1/nodes/{id}/history` - Node state transitions

Missing:
- Global activity stream across all nodes
- User action audit log
- System events (storage, sync jobs, etc.)

## Expected Functionality

### Global Activity Log

Shows all system activity in chronological order:
- Node state changes
- Node discovery events
- Installation progress/completion
- User actions (bulk operations, config changes)
- System events (sync jobs, storage operations)

### Backend API Addition

```
GET /api/v1/activity
    ?limit=50
    &offset=0
    &type=node_event|state_change|user_action|system
    &node_id=<uuid>
    &since=<datetime>
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "evt-123",
      "timestamp": "2026-01-23T10:30:00Z",
      "type": "state_change",
      "category": "node",
      "node_id": "node-456",
      "node_name": "web-server-01",
      "message": "State changed from pending to installing",
      "details": {
        "from_state": "pending",
        "to_state": "installing",
        "triggered_by": "workflow_start"
      },
      "user": null
    },
    {
      "id": "evt-124",
      "timestamp": "2026-01-23T10:25:00Z",
      "type": "user_action",
      "category": "bulk_operation",
      "message": "Assigned 5 nodes to group 'Production'",
      "details": {
        "action": "bulk_assign_group",
        "node_count": 5,
        "group_name": "Production"
      },
      "user": "admin"
    }
  ],
  "total": 1250
}
```

### Frontend Page Features

1. **Timeline View:** Chronological list of events
2. **Filters:**
   - Event type (state changes, user actions, system)
   - Node filter (specific node)
   - Date range
3. **Search:** Full-text search in messages
4. **Real-time:** WebSocket for live updates
5. **Export:** Download as CSV/JSON

## Implementation

### Backend: Create unified activity endpoint

```python
@router.get("/activity", response_model=ApiListResponse[ActivityEntry])
async def get_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    type: str | None = Query(None),
    node_id: str | None = Query(None),
    since: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get global activity log."""
    # Query NodeEvents + NodeStateLogs + (future) UserActionLogs
    # Union and sort by timestamp
    pass
```

### Frontend: Create Activity page

```typescript
export function ActivityLog() {
  const [filters, setFilters] = useState({ type: null, nodeId: null })
  const { data, isLoading, fetchNextPage } = useInfiniteActivity(filters)

  return (
    <div className="space-y-6">
      <h2>Activity Log</h2>
      <ActivityFilters filters={filters} onChange={setFilters} />
      <ActivityTimeline events={data?.pages.flat() ?? []} />
    </div>
  )
}
```

## Acceptance Criteria

- [ ] Global activity endpoint aggregates all event types
- [ ] Frontend displays chronological timeline
- [ ] Filtering by type, node, date range works
- [ ] Infinite scroll or pagination
- [ ] Real-time updates for new events
- [ ] Export functionality

## Related Files

- `frontend/src/router.tsx`
- `frontend/src/pages/ActivityLog.tsx` (new)
- `src/api/routes/activity.py` (new) or extend `src/api/routes/system.py`
- `src/db/models.py` (NodeEvent, NodeStateLog exist)
