# Issue 003: Implement Bulk Assign Workflow Endpoint

**Priority:** MEDIUM
**Type:** Backend Feature
**Component:** API - Nodes
**Status:** Open

---

## Summary

The frontend has API methods to bulk assign workflows to nodes, but the backend endpoint does not exist.

## Current Behavior

Frontend calls non-existent endpoint, resulting in 404 error.

**Frontend location:** `frontend/src/api/nodes.ts:60-65`
```typescript
async bulkAssignWorkflow(nodeIds: string[], workflowId: string | null): Promise<ApiResponse<{ updated: number }>> {
  return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-workflow', {
    node_ids: nodeIds,
    workflow_id: workflowId,
  })
}
```

## Expected Behavior

New endpoint: `POST /api/v1/nodes/bulk/assign-workflow`

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "workflow_id": "ubuntu-2404-server"
}
```

To unassign workflow:
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "workflow_id": null
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "updated": 3
  },
  "message": "Assigned workflow to 3 nodes"
}
```

## Implementation

**File:** `src/api/routes/nodes.py`

```python
class BulkAssignWorkflowRequest(BaseModel):
    node_ids: list[str]
    workflow_id: str | None = None

@router.post("/nodes/bulk/assign-workflow", response_model=ApiResponse[dict])
async def bulk_assign_workflow(
    request: BulkAssignWorkflowRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign a workflow to multiple nodes."""
    # Validate workflow exists if provided
    if request.workflow_id:
        from src.core.workflows import WorkflowManager
        workflow = WorkflowManager.get_workflow(request.workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

    # Update nodes
    result = await db.execute(
        update(Node)
        .where(Node.id.in_(request.node_ids))
        .values(workflow_id=request.workflow_id)
    )

    updated = result.rowcount

    action = "assigned workflow" if request.workflow_id else "unassigned workflow"
    return ApiResponse(
        data={"updated": updated},
        message=f"{action} for {updated} node(s)",
    )
```

## Acceptance Criteria

- [ ] Endpoint accepts list of node IDs and workflow ID
- [ ] Validates workflow exists before assignment
- [ ] Allows `null` workflow_id to unassign
- [ ] Returns count of updated nodes
- [ ] Non-existent node IDs are silently skipped

## Related Files

- `frontend/src/api/nodes.ts`
- `frontend/src/hooks/useBulkActions.ts`
- `src/api/routes/nodes.py`
- `src/core/workflows.py`
