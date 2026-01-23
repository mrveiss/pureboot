# Issue 015: Enable Workflow Assignment in Node Detail Page

**Priority:** HIGH
**Type:** Frontend Enhancement
**Component:** Frontend - NodeDetail
**Status:** Open

---

## Summary

The NodeDetail page has a disabled "Assign Workflow (Coming Soon)" button, but the backend is ready to support workflow assignment.

## Current Behavior

**Location:** `frontend/src/pages/NodeDetail.tsx:273`
```typescript
<Button variant="outline" disabled>
  Assign Workflow (Coming Soon)
</Button>
```

## Backend Ready

- `GET /api/v1/workflows` - Lists available workflows
- `PATCH /api/v1/nodes/{id}` - Can update `workflow_id` field
- Node model has `workflow_id` column

## Expected Behavior

1. Button opens workflow selection dialog
2. Dialog shows available workflows
3. Selecting workflow updates node
4. Current workflow shown in UI

## Implementation

### 1. Update NodeDetail.tsx

```typescript
import { useWorkflows } from '@/hooks'
import { Dialog, Select } from '@/components/ui'

export function NodeDetail() {
  const [workflowDialogOpen, setWorkflowDialogOpen] = useState(false)
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null)

  const { data: workflowsResponse } = useWorkflows()
  const updateNode = useUpdateNode()

  const workflows = workflowsResponse?.data ?? []
  const node = nodeResponse?.data

  const handleAssignWorkflow = () => {
    if (node && selectedWorkflow !== undefined) {
      updateNode.mutate({
        nodeId: node.id,
        data: { workflow_id: selectedWorkflow }
      }, {
        onSuccess: () => setWorkflowDialogOpen(false)
      })
    }
  }

  return (
    // ... existing JSX ...

    {/* Workflow Card */}
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="h-5 w-5" />
          Workflow
        </CardTitle>
      </CardHeader>
      <CardContent>
        {node?.workflow_id ? (
          <div className="flex items-center justify-between">
            <span className="font-mono">{node.workflow_id}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWorkflowDialogOpen(true)}
            >
              Change
            </Button>
          </div>
        ) : (
          <div className="text-muted-foreground">
            <p>No workflow assigned</p>
            <Button
              variant="outline"
              className="mt-2"
              onClick={() => setWorkflowDialogOpen(true)}
            >
              Assign Workflow
            </Button>
          </div>
        )}
      </CardContent>
    </Card>

    {/* Workflow Dialog */}
    <Dialog open={workflowDialogOpen} onOpenChange={setWorkflowDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Assign Workflow</DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <Select
            value={selectedWorkflow ?? ''}
            onValueChange={setSelectedWorkflow}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select a workflow..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">No Workflow</SelectItem>
              {workflows.map(wf => (
                <SelectItem key={wf.id} value={wf.id}>
                  {wf.name} ({wf.architecture})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setWorkflowDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleAssignWorkflow} disabled={updateNode.isPending}>
            {updateNode.isPending ? 'Assigning...' : 'Assign'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

### 2. Add useWorkflows hook (if not exists)

See Issue 009 for hook implementation.

### 3. Update useUpdateNode to handle workflow_id

The existing `useUpdateNode` hook should work if `NodeUpdate` schema accepts `workflow_id`.

Verify in backend `src/api/schemas.py`:
```python
class NodeUpdate(BaseModel):
    hostname: str | None = None
    workflow_id: str | None = None
    group_id: str | None = None
    # ... other fields
```

## Acceptance Criteria

- [ ] "Assign Workflow" button is enabled
- [ ] Dialog shows list of available workflows
- [ ] Can select and assign workflow
- [ ] Can clear workflow assignment
- [ ] Current workflow displayed in UI
- [ ] Loading state during assignment

## Related Files

- `frontend/src/pages/NodeDetail.tsx`
- `frontend/src/hooks/useWorkflows.ts`
- `frontend/src/hooks/useNodes.ts`
- `src/api/routes/nodes.py`
- `src/api/schemas.py`
