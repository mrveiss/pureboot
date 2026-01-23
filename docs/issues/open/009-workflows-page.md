# Issue 009: Implement Workflows Page

**Priority:** HIGH
**Type:** Frontend Feature
**Component:** Frontend - Pages
**Status:** Open

---

## Summary

The Workflows page shows "Coming Soon" placeholder but the backend API is ready. Users need to view available workflows and their configurations.

## Current Behavior

**Router:** `frontend/src/router.tsx:23`
```typescript
{ path: 'workflows', element: <div>Workflows (Coming Soon)</div> },
```

## Backend Ready

The workflows API is implemented:
- `GET /api/v1/workflows` - List all workflows
- `GET /api/v1/workflows/{id}` - Get workflow details

**Workflow Response:**
```json
{
  "id": "ubuntu-2404-server",
  "name": "Ubuntu 24.04 Server",
  "kernel_path": "/tftp/ubuntu/vmlinuz",
  "initrd_path": "/tftp/ubuntu/initrd",
  "cmdline": "ip=dhcp url=http://pureboot.local/ubuntu-2404.iso",
  "architecture": "x86_64",
  "boot_mode": "uefi"
}
```

## Expected Behavior

Create a Workflows page that:
1. Lists all available workflows in a grid/table
2. Shows workflow details (kernel, initrd, cmdline)
3. Indicates architecture and boot mode compatibility
4. Links to node assignment

## Implementation

### 1. Create API client `frontend/src/api/workflows.ts`

```typescript
import { apiClient } from './client'
import type { ApiResponse, ApiListResponse, Workflow } from '@/types'

export const workflowsApi = {
  async list(): Promise<ApiListResponse<Workflow>> {
    return apiClient.get<ApiListResponse<Workflow>>('/workflows')
  },

  async get(workflowId: string): Promise<ApiResponse<Workflow>> {
    return apiClient.get<ApiResponse<Workflow>>(`/workflows/${workflowId}`)
  },
}
```

### 2. Create hook `frontend/src/hooks/useWorkflows.ts`

```typescript
import { useQuery } from '@tanstack/react-query'
import { workflowsApi } from '@/api'

export const workflowKeys = {
  all: ['workflows'] as const,
  lists: () => [...workflowKeys.all, 'list'] as const,
  detail: (id: string) => [...workflowKeys.all, 'detail', id] as const,
}

export function useWorkflows() {
  return useQuery({
    queryKey: workflowKeys.lists(),
    queryFn: () => workflowsApi.list(),
  })
}

export function useWorkflow(workflowId: string) {
  return useQuery({
    queryKey: workflowKeys.detail(workflowId),
    queryFn: () => workflowsApi.get(workflowId),
    enabled: !!workflowId,
  })
}
```

### 3. Create types `frontend/src/types/workflow.ts`

```typescript
export interface Workflow {
  id: string
  name: string
  kernel_path: string
  initrd_path: string
  cmdline: string
  architecture: 'x86_64' | 'arm64' | 'aarch64'
  boot_mode: 'bios' | 'uefi'
}
```

### 4. Create page `frontend/src/pages/Workflows.tsx`

```typescript
import { GitBranch, Cpu, Server } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { useWorkflows } from '@/hooks'

export function Workflows() {
  const { data: response, isLoading } = useWorkflows()
  const workflows = response?.data ?? []

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold tracking-tight">Workflows</h2>

      {isLoading ? (
        <div>Loading workflows...</div>
      ) : workflows.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            <GitBranch className="mx-auto h-12 w-12 mb-4 opacity-50" />
            <p>No workflows configured.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <Card key={workflow.id}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <GitBranch className="h-5 w-5" />
                  {workflow.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2">
                  <Badge variant="outline">{workflow.architecture}</Badge>
                  <Badge variant="outline">{workflow.boot_mode.toUpperCase()}</Badge>
                </div>
                <div className="text-sm text-muted-foreground">
                  <p className="font-mono truncate">{workflow.kernel_path}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
```

### 5. Update router

```typescript
import { Workflows } from '@/pages'
// ...
{ path: 'workflows', element: <Workflows /> },
```

## Acceptance Criteria

- [ ] Workflows page lists all available workflows
- [ ] Each workflow shows name, architecture, boot mode
- [ ] Shows kernel/initrd paths
- [ ] Empty state when no workflows configured
- [ ] Loading state while fetching

## Related Files

- `frontend/src/router.tsx`
- `frontend/src/pages/Workflows.tsx` (new)
- `frontend/src/api/workflows.ts` (new)
- `frontend/src/hooks/useWorkflows.ts` (new)
- `frontend/src/types/workflow.ts` (new)
- `src/api/routes/workflows.py`
