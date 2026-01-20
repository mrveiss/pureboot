# Web UI Phase 3: Groups & Bulk Operations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build device groups management with CRUD operations, bulk node selection with actions, group assignment, and approval rules per group.

**Architecture:** Extend Phase 2 with React Query hooks for groups, bulk selection state management via Zustand, and reusable bulk action components. All components use existing shadcn/ui patterns.

**Tech Stack:** React 18, TypeScript, TanStack Query, Zustand, React Router v6, Tailwind CSS, Lucide icons

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-groups/frontend`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run npm install, npm run dev, or any other commands that execute the application. Only create/edit files.

---

## Task 1: Add Group Types and Bulk Action Types

**Files:**
- Create: `frontend/src/types/group.ts`
- Modify: `frontend/src/types/index.ts`

**Step 1: Create group.ts**

```typescript
import type { NodeState } from './node'

export interface ApprovalRule {
  action: BulkActionType
  required: boolean
  min_approvers: number
}

export type BulkActionType =
  | 'assign_workflow'
  | 'assign_group'
  | 'add_tag'
  | 'remove_tag'
  | 'change_state'
  | 'retire'
  | 'wipe'

export interface BulkAction {
  type: BulkActionType
  label: string
  icon: string
  requiresApproval: boolean
  dangerLevel: 'safe' | 'warning' | 'danger'
  allowedFromStates?: NodeState[]
}

export const BULK_ACTIONS: BulkAction[] = [
  {
    type: 'assign_workflow',
    label: 'Assign Workflow',
    icon: 'GitBranch',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'assign_group',
    label: 'Assign Group',
    icon: 'FolderOpen',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'add_tag',
    label: 'Add Tag',
    icon: 'Tag',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'remove_tag',
    label: 'Remove Tag',
    icon: 'TagOff',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'change_state',
    label: 'Change State',
    icon: 'RefreshCw',
    requiresApproval: true,
    dangerLevel: 'warning',
  },
  {
    type: 'retire',
    label: 'Retire Nodes',
    icon: 'Archive',
    requiresApproval: true,
    dangerLevel: 'warning',
    allowedFromStates: ['active'],
  },
  {
    type: 'wipe',
    label: 'Wipe Nodes',
    icon: 'Trash2',
    requiresApproval: true,
    dangerLevel: 'danger',
    allowedFromStates: ['decommissioned'],
  },
]

export interface BulkOperationResult {
  success: boolean
  total: number
  succeeded: number
  failed: number
  errors: { nodeId: string; error: string }[]
}
```

**Step 2: Update types/index.ts**

```typescript
export type { ApiResponse, ApiListResponse, ApiErrorResponse } from './api'
export type { User, LoginCredentials, AuthTokens, AuthState } from './auth'
export type {
  Node,
  NodeState,
  DeviceGroup,
  Architecture,
  BootMode,
  NodeFilterParams,
  StateHistoryEntry,
  NodeStats,
} from './node'
export {
  NODE_STATE_COLORS,
  NODE_STATE_LABELS,
  NODE_STATE_TRANSITIONS,
} from './node'
export type {
  ApprovalRule,
  BulkActionType,
  BulkAction,
  BulkOperationResult,
} from './group'
export { BULK_ACTIONS } from './group'
```

**Step 3: Commit**

```bash
git add frontend/src/types/
git commit -m "feat(frontend): add group and bulk action types"
```

---

## Task 2: Create Selection Store with Zustand

**Files:**
- Create: `frontend/src/stores/selection.ts`
- Modify: `frontend/src/stores/index.ts`

**Step 1: Create selection.ts**

```typescript
import { create } from 'zustand'

interface SelectionState {
  selectedNodeIds: Set<string>
  isAllSelected: boolean
  totalNodes: number

  // Actions
  toggleNode: (nodeId: string) => void
  selectNode: (nodeId: string) => void
  deselectNode: (nodeId: string) => void
  selectAll: (nodeIds: string[]) => void
  deselectAll: () => void
  setTotalNodes: (count: number) => void
}

export const useSelectionStore = create<SelectionState>((set, get) => ({
  selectedNodeIds: new Set(),
  isAllSelected: false,
  totalNodes: 0,

  toggleNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId)
      } else {
        newSet.add(nodeId)
      }
      return {
        selectedNodeIds: newSet,
        isAllSelected: newSet.size === state.totalNodes && state.totalNodes > 0,
      }
    })
  },

  selectNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      newSet.add(nodeId)
      return {
        selectedNodeIds: newSet,
        isAllSelected: newSet.size === state.totalNodes && state.totalNodes > 0,
      }
    })
  },

  deselectNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      newSet.delete(nodeId)
      return {
        selectedNodeIds: newSet,
        isAllSelected: false,
      }
    })
  },

  selectAll: (nodeIds) => {
    set({
      selectedNodeIds: new Set(nodeIds),
      isAllSelected: true,
    })
  },

  deselectAll: () => {
    set({
      selectedNodeIds: new Set(),
      isAllSelected: false,
    })
  },

  setTotalNodes: (count) => {
    set({ totalNodes: count })
  },
}))
```

**Step 2: Update stores/index.ts**

```typescript
export { useAuthStore } from './auth'
export { useThemeStore } from './theme'
export { useSelectionStore } from './selection'
```

**Step 3: Commit**

```bash
git add frontend/src/stores/
git commit -m "feat(frontend): add selection store for bulk operations"
```

---

## Task 3: Create React Query Hooks for Groups

**Files:**
- Create: `frontend/src/hooks/useGroups.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Create useGroups.ts**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { groupsApi } from '@/api'
import type { DeviceGroup } from '@/types'

export const groupKeys = {
  all: ['groups'] as const,
  lists: () => [...groupKeys.all, 'list'] as const,
  list: () => [...groupKeys.lists()] as const,
  details: () => [...groupKeys.all, 'detail'] as const,
  detail: (id: string) => [...groupKeys.details(), id] as const,
  nodes: (id: string) => [...groupKeys.all, 'nodes', id] as const,
}

export function useGroups() {
  return useQuery({
    queryKey: groupKeys.list(),
    queryFn: () => groupsApi.list(),
  })
}

export function useGroup(groupId: string) {
  return useQuery({
    queryKey: groupKeys.detail(groupId),
    queryFn: () => groupsApi.get(groupId),
    enabled: !!groupId,
  })
}

export function useGroupNodes(groupId: string) {
  return useQuery({
    queryKey: groupKeys.nodes(groupId),
    queryFn: () => groupsApi.getNodes(groupId),
    enabled: !!groupId,
  })
}

export function useCreateGroup() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Partial<DeviceGroup>) => groupsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() })
    },
  })
}

export function useUpdateGroup() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ groupId, data }: { groupId: string; data: Partial<DeviceGroup> }) =>
      groupsApi.update(groupId, data),
    onSuccess: (_, { groupId }) => {
      queryClient.invalidateQueries({ queryKey: groupKeys.detail(groupId) })
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() })
    },
  })
}

export function useDeleteGroup() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (groupId: string) => groupsApi.delete(groupId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() })
    },
  })
}
```

**Step 2: Update hooks/index.ts**

```typescript
export { useWebSocket } from './useWebSocket'
export type { WebSocketEvent } from './useWebSocket'
export {
  useNodes,
  useNode,
  useNodeStats,
  useUpdateNodeState,
  useUpdateNode,
  nodeKeys,
} from './useNodes'
export { useNodeUpdates } from './useNodeUpdates'
export {
  useGroups,
  useGroup,
  useGroupNodes,
  useCreateGroup,
  useUpdateGroup,
  useDeleteGroup,
  groupKeys,
} from './useGroups'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add React Query hooks for groups"
```

---

## Task 4: Add Bulk API Methods

**Files:**
- Modify: `frontend/src/api/nodes.ts`

**Step 1: Add bulk methods to nodesApi**

Add to the end of the `nodesApi` object (before the closing brace):

```typescript
  async bulkAssignGroup(nodeIds: string[], groupId: string | null): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-group', {
      node_ids: nodeIds,
      group_id: groupId,
    })
  },

  async bulkAssignWorkflow(nodeIds: string[], workflowId: string | null): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-workflow', {
      node_ids: nodeIds,
      workflow_id: workflowId,
    })
  },

  async bulkAddTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/add-tag', {
      node_ids: nodeIds,
      tag,
    })
  },

  async bulkRemoveTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/remove-tag', {
      node_ids: nodeIds,
      tag,
    })
  },

  async bulkChangeState(nodeIds: string[], newState: string): Promise<ApiResponse<{ updated: number; failed: number }>> {
    return apiClient.post<ApiResponse<{ updated: number; failed: number }>>('/nodes/bulk/change-state', {
      node_ids: nodeIds,
      new_state: newState,
    })
  },
```

**Step 2: Commit**

```bash
git add frontend/src/api/nodes.ts
git commit -m "feat(frontend): add bulk operation API methods"
```

---

## Task 5: Create Bulk Actions Hook

**Files:**
- Create: `frontend/src/hooks/useBulkActions.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Create useBulkActions.ts**

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { nodesApi } from '@/api'
import { nodeKeys } from './useNodes'
import { groupKeys } from './useGroups'
import { useSelectionStore } from '@/stores'

export function useBulkAssignGroup() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, groupId }: { nodeIds: string[]; groupId: string | null }) =>
      nodesApi.bulkAssignGroup(nodeIds, groupId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkAssignWorkflow() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, workflowId }: { nodeIds: string[]; workflowId: string | null }) =>
      nodesApi.bulkAssignWorkflow(nodeIds, workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkAddTag() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, tag }: { nodeIds: string[]; tag: string }) =>
      nodesApi.bulkAddTag(nodeIds, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkRemoveTag() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, tag }: { nodeIds: string[]; tag: string }) =>
      nodesApi.bulkRemoveTag(nodeIds, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkChangeState() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, newState }: { nodeIds: string[]; newState: string }) =>
      nodesApi.bulkChangeState(nodeIds, newState),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
      deselectAll()
    },
  })
}
```

**Step 2: Update hooks/index.ts**

Add to exports:

```typescript
export {
  useBulkAssignGroup,
  useBulkAssignWorkflow,
  useBulkAddTag,
  useBulkRemoveTag,
  useBulkChangeState,
} from './useBulkActions'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add bulk action mutation hooks"
```

---

## Task 6: Create Checkbox Component

**Files:**
- Create: `frontend/src/components/ui/checkbox.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Create checkbox.tsx**

```typescript
import * as React from 'react'
import { Check, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface CheckboxProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked?: boolean
  indeterminate?: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(
  ({ className, checked, indeterminate, onCheckedChange, ...props }, ref) => {
    return (
      <button
        type="button"
        role="checkbox"
        aria-checked={indeterminate ? 'mixed' : checked}
        ref={ref}
        onClick={() => onCheckedChange?.(!checked)}
        className={cn(
          'peer h-4 w-4 shrink-0 rounded-sm border border-primary shadow',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          (checked || indeterminate) && 'bg-primary text-primary-foreground',
          className
        )}
        {...props}
      >
        {indeterminate ? (
          <Minus className="h-3 w-3" />
        ) : checked ? (
          <Check className="h-3 w-3" />
        ) : null}
      </button>
    )
  }
)
Checkbox.displayName = 'Checkbox'

export { Checkbox }
```

**Step 2: Update ui/index.ts**

```typescript
export { Badge } from './badge'
export { Button } from './button'
export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent } from './card'
export { Checkbox } from './checkbox'
export { Input } from './input'
export { Label } from './label'
export { Separator } from './separator'
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(frontend): add checkbox component"
```

---

## Task 7: Create Dialog Component

**Files:**
- Create: `frontend/src/components/ui/dialog.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Create dialog.tsx**

```typescript
import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface DialogContextValue {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DialogContext = React.createContext<DialogContextValue | null>(null)

function useDialogContext() {
  const context = React.useContext(DialogContext)
  if (!context) {
    throw new Error('Dialog components must be used within a Dialog')
  }
  return context
}

interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open = false, onOpenChange, children }: DialogProps) {
  const [internalOpen, setInternalOpen] = React.useState(open)
  const isControlled = onOpenChange !== undefined
  const isOpen = isControlled ? open : internalOpen
  const setOpen = isControlled ? onOpenChange : setInternalOpen

  return (
    <DialogContext.Provider value={{ open: isOpen, onOpenChange: setOpen }}>
      {children}
    </DialogContext.Provider>
  )
}

interface DialogTriggerProps {
  children: React.ReactNode
  asChild?: boolean
}

function DialogTrigger({ children, asChild }: DialogTriggerProps) {
  const { onOpenChange } = useDialogContext()

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<{ onClick?: () => void }>, {
      onClick: () => onOpenChange(true),
    })
  }

  return (
    <button type="button" onClick={() => onOpenChange(true)}>
      {children}
    </button>
  )
}

interface DialogContentProps {
  children: React.ReactNode
  className?: string
}

function DialogContent({ children, className }: DialogContentProps) {
  const { open, onOpenChange } = useDialogContext()

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/80"
        onClick={() => onOpenChange(false)}
      />
      {/* Content */}
      <div className="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%]">
        <div
          className={cn(
            'w-full max-w-lg bg-background p-6 shadow-lg rounded-lg border',
            'max-h-[85vh] overflow-y-auto',
            className
          )}
        >
          {children}
          <button
            type="button"
            className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
      </div>
    </div>
  )
}

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2', className)}
      {...props}
    />
  )
}

function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn('text-lg font-semibold leading-none tracking-tight', className)}
      {...props}
    />
  )
}

function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn('text-sm text-muted-foreground', className)} {...props} />
  )
}

export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
```

**Step 2: Update ui/index.ts**

Add the dialog export:

```typescript
export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './dialog'
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(frontend): add dialog component"
```

---

## Task 8: Create Select Component

**Files:**
- Create: `frontend/src/components/ui/select.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Create select.tsx**

```typescript
import * as React from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SelectContextValue {
  value: string
  onValueChange: (value: string) => void
  open: boolean
  setOpen: (open: boolean) => void
}

const SelectContext = React.createContext<SelectContextValue | null>(null)

function useSelectContext() {
  const context = React.useContext(SelectContext)
  if (!context) {
    throw new Error('Select components must be used within a Select')
  }
  return context
}

interface SelectProps {
  value?: string
  onValueChange?: (value: string) => void
  children: React.ReactNode
}

function Select({ value = '', onValueChange, children }: SelectProps) {
  const [internalValue, setInternalValue] = React.useState(value)
  const [open, setOpen] = React.useState(false)
  const isControlled = onValueChange !== undefined
  const currentValue = isControlled ? value : internalValue
  const setValue = isControlled ? onValueChange : setInternalValue

  return (
    <SelectContext.Provider value={{ value: currentValue, onValueChange: setValue, open, setOpen }}>
      <div className="relative">
        {children}
      </div>
    </SelectContext.Provider>
  )
}

interface SelectTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode
}

const SelectTrigger = React.forwardRef<HTMLButtonElement, SelectTriggerProps>(
  ({ className, children, ...props }, ref) => {
    const { open, setOpen } = useSelectContext()

    return (
      <button
        type="button"
        ref={ref}
        onClick={() => setOpen(!open)}
        className={cn(
          'flex h-9 w-full items-center justify-between rounded-md border border-input',
          'bg-transparent px-3 py-2 text-sm shadow-sm',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        {...props}
      >
        {children}
        <ChevronDown className="h-4 w-4 opacity-50" />
      </button>
    )
  }
)
SelectTrigger.displayName = 'SelectTrigger'

function SelectValue({ placeholder }: { placeholder?: string }) {
  const { value } = useSelectContext()
  return <span>{value || placeholder}</span>
}

interface SelectContentProps {
  children: React.ReactNode
  className?: string
}

function SelectContent({ children, className }: SelectContentProps) {
  const { open, setOpen } = useSelectContext()

  React.useEffect(() => {
    if (open) {
      const handleClickOutside = () => setOpen(false)
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [open, setOpen])

  if (!open) return null

  return (
    <div
      className={cn(
        'absolute z-50 mt-1 w-full min-w-[8rem] overflow-hidden rounded-md border',
        'bg-popover text-popover-foreground shadow-md',
        className
      )}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="p-1">{children}</div>
    </div>
  )
}

interface SelectItemProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string
  children: React.ReactNode
}

function SelectItem({ value, children, className, ...props }: SelectItemProps) {
  const { value: selectedValue, onValueChange, setOpen } = useSelectContext()
  const isSelected = selectedValue === value

  return (
    <div
      role="option"
      aria-selected={isSelected}
      onClick={() => {
        onValueChange(value)
        setOpen(false)
      }}
      className={cn(
        'relative flex w-full cursor-pointer select-none items-center rounded-sm',
        'py-1.5 pl-8 pr-2 text-sm outline-none',
        'hover:bg-accent hover:text-accent-foreground',
        'focus:bg-accent focus:text-accent-foreground',
        className
      )}
      {...props}
    >
      {isSelected && (
        <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
          <Check className="h-4 w-4" />
        </span>
      )}
      {children}
    </div>
  )
}

export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
}
```

**Step 2: Update ui/index.ts**

Add the select exports:

```typescript
export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from './select'
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(frontend): add select component"
```

---

## Task 9: Create Bulk Action Bar Component

**Files:**
- Create: `frontend/src/components/nodes/BulkActionBar.tsx`

**Step 1: Create BulkActionBar.tsx**

```typescript
import { useState } from 'react'
import {
  GitBranch,
  FolderOpen,
  Tag,
  RefreshCw,
  Archive,
  Trash2,
  X,
} from 'lucide-react'
import { Button, Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, Input, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui'
import { useSelectionStore } from '@/stores'
import { useGroups, useBulkAssignGroup, useBulkAddTag, useBulkChangeState } from '@/hooks'
import { NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

type ActionDialogType = 'group' | 'tag' | 'state' | null

export function BulkActionBar() {
  const { selectedNodeIds, deselectAll } = useSelectionStore()
  const [activeDialog, setActiveDialog] = useState<ActionDialogType>(null)
  const [selectedGroup, setSelectedGroup] = useState<string>('')
  const [tagInput, setTagInput] = useState('')
  const [selectedState, setSelectedState] = useState<NodeState | ''>('')

  const { data: groupsResponse } = useGroups()
  const assignGroup = useBulkAssignGroup()
  const addTag = useBulkAddTag()
  const changeState = useBulkChangeState()

  const selectedCount = selectedNodeIds.size

  if (selectedCount === 0) return null

  const groups = groupsResponse?.data ?? []
  const nodeIds = Array.from(selectedNodeIds)

  const handleAssignGroup = () => {
    if (selectedGroup) {
      assignGroup.mutate({
        nodeIds,
        groupId: selectedGroup === 'none' ? null : selectedGroup,
      })
    }
    setActiveDialog(null)
    setSelectedGroup('')
  }

  const handleAddTag = () => {
    if (tagInput.trim()) {
      addTag.mutate({ nodeIds, tag: tagInput.trim() })
    }
    setActiveDialog(null)
    setTagInput('')
  }

  const handleChangeState = () => {
    if (selectedState) {
      changeState.mutate({ nodeIds, newState: selectedState })
    }
    setActiveDialog(null)
    setSelectedState('')
  }

  const allowedStates: NodeState[] = ['pending', 'retired', 'reprovision']

  return (
    <>
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40">
        <div className="flex items-center gap-2 bg-background border rounded-lg shadow-lg px-4 py-3">
          <span className="text-sm font-medium mr-2">
            {selectedCount} node{selectedCount !== 1 ? 's' : ''} selected
          </span>

          <div className="h-6 w-px bg-border" />

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('group')}
            className="gap-2"
          >
            <FolderOpen className="h-4 w-4" />
            Assign Group
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('tag')}
            className="gap-2"
          >
            <Tag className="h-4 w-4" />
            Add Tag
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('state')}
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Change State
          </Button>

          <div className="h-6 w-px bg-border" />

          <Button variant="ghost" size="sm" onClick={deselectAll}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Assign Group Dialog */}
      <Dialog open={activeDialog === 'group'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign Group to {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Select value={selectedGroup} onValueChange={setSelectedGroup}>
              <SelectTrigger>
                <SelectValue placeholder="Select a group..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Group</SelectItem>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleAssignGroup} disabled={!selectedGroup || assignGroup.isPending}>
              {assignGroup.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Tag Dialog */}
      <Dialog open={activeDialog === 'tag'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Tag to {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="Enter tag name..."
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleAddTag} disabled={!tagInput.trim() || addTag.isPending}>
              {addTag.isPending ? 'Adding...' : 'Add Tag'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change State Dialog */}
      <Dialog open={activeDialog === 'state'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change State of {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Note: State changes are only applied to nodes where the transition is valid.
            </p>
            <Select value={selectedState} onValueChange={(v) => setSelectedState(v as NodeState)}>
              <SelectTrigger>
                <SelectValue placeholder="Select new state..." />
              </SelectTrigger>
              <SelectContent>
                {allowedStates.map((state) => (
                  <SelectItem key={state} value={state}>
                    {NODE_STATE_LABELS[state]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleChangeState} disabled={!selectedState || changeState.isPending}>
              {changeState.isPending ? 'Changing...' : 'Change State'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
```

**Step 2: Update nodes/index.ts**

```typescript
export { StateMachine } from './StateMachine'
export { NodeTable } from './NodeTable'
export { BulkActionBar } from './BulkActionBar'
```

**Step 3: Commit**

```bash
git add frontend/src/components/nodes/
git commit -m "feat(frontend): add bulk action bar component"
```

---

## Task 10: Update NodeTable with Selection

**Files:**
- Modify: `frontend/src/components/nodes/NodeTable.tsx`

**Step 1: Add checkbox column and selection integration**

Update NodeTable.tsx to include selection checkboxes. The key changes:

1. Import `Checkbox` from ui components
2. Import `useSelectionStore` from stores
3. Add checkbox in header for select all
4. Add checkbox in each row
5. Call `setTotalNodes` when nodes change

Replace the entire NodeTable.tsx with selection support:

```typescript
import { useRef, useState, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Badge, Button, Input, Checkbox } from '@/components/ui'
import { Search, ChevronUp, ChevronDown, Filter } from 'lucide-react'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type Node, type NodeState } from '@/types'
import { useSelectionStore } from '@/stores'

interface NodeTableProps {
  nodes: Node[]
  isLoading?: boolean
  onStateFilter?: (state: NodeState | null) => void
  selectedState?: NodeState | null
  enableSelection?: boolean
}

type SortField = 'hostname' | 'mac_address' | 'state' | 'arch' | 'last_seen_at'
type SortDirection = 'asc' | 'desc'

function StateBadge({ state }: { state: NodeState }) {
  return (
    <Badge
      variant="outline"
      className={cn('border-0 text-white', NODE_STATE_COLORS[state])}
    >
      {NODE_STATE_LABELS[state]}
    </Badge>
  )
}

function formatLastSeen(dateStr: string | null): string {
  if (!dateStr) return 'Never'

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function NodeTable({
  nodes,
  isLoading,
  onStateFilter,
  selectedState,
  enableSelection = true,
}: NodeTableProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('hostname')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  const {
    selectedNodeIds,
    isAllSelected,
    toggleNode,
    selectAll,
    deselectAll,
    setTotalNodes,
  } = useSelectionStore()

  // Filter nodes by search
  const filteredNodes = nodes.filter((node) => {
    const searchLower = search.toLowerCase()
    return (
      (node.hostname?.toLowerCase().includes(searchLower) ?? false) ||
      node.mac_address.toLowerCase().includes(searchLower) ||
      node.state.toLowerCase().includes(searchLower) ||
      (node.ip_address?.toLowerCase().includes(searchLower) ?? false)
    )
  })

  // Sort nodes
  const sortedNodes = [...filteredNodes].sort((a, b) => {
    let aVal: string | null = ''
    let bVal: string | null = ''

    switch (sortField) {
      case 'hostname':
        aVal = a.hostname ?? ''
        bVal = b.hostname ?? ''
        break
      case 'mac_address':
        aVal = a.mac_address
        bVal = b.mac_address
        break
      case 'state':
        aVal = a.state
        bVal = b.state
        break
      case 'arch':
        aVal = a.arch
        bVal = b.arch
        break
      case 'last_seen_at':
        aVal = a.last_seen_at ?? ''
        bVal = b.last_seen_at ?? ''
        break
    }

    const cmp = (aVal ?? '').localeCompare(bVal ?? '')
    return sortDirection === 'asc' ? cmp : -cmp
  })

  // Update total nodes count for selection store
  useEffect(() => {
    setTotalNodes(sortedNodes.length)
  }, [sortedNodes.length, setTotalNodes])

  const rowVirtualizer = useVirtualizer({
    count: sortedNodes.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 52,
    overscan: 10,
  })

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  const handleSelectAll = () => {
    if (isAllSelected) {
      deselectAll()
    } else {
      selectAll(sortedNodes.map(n => n.id))
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null
    return sortDirection === 'asc' ? (
      <ChevronUp className="h-4 w-4" />
    ) : (
      <ChevronDown className="h-4 w-4" />
    )
  }

  const allStates: NodeState[] = [
    'discovered', 'ignored', 'pending', 'installing', 'installed',
    'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping'
  ]

  const someSelected = selectedNodeIds.size > 0 && !isAllSelected

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by hostname, MAC, IP..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {onStateFilter && (
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <div className="flex flex-wrap gap-1">
              <Button
                variant={selectedState === null ? 'default' : 'outline'}
                size="sm"
                onClick={() => onStateFilter(null)}
              >
                All
              </Button>
              {allStates.map((state) => (
                <Button
                  key={state}
                  variant={selectedState === state ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => onStateFilter(state)}
                  className={cn(
                    selectedState === state && NODE_STATE_COLORS[state],
                    selectedState === state && 'text-white border-0'
                  )}
                >
                  {NODE_STATE_LABELS[state]}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="rounded-md border">
        {/* Header */}
        <div className="flex border-b bg-muted/50 text-sm font-medium">
          {enableSelection && (
            <div className="w-12 p-3 flex items-center justify-center">
              <Checkbox
                checked={isAllSelected}
                indeterminate={someSelected}
                onCheckedChange={handleSelectAll}
              />
            </div>
          )}
          <button
            className="flex-1 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('hostname')}
          >
            Hostname <SortIcon field="hostname" />
          </button>
          <button
            className="w-40 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('mac_address')}
          >
            MAC Address <SortIcon field="mac_address" />
          </button>
          <button
            className="w-32 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('state')}
          >
            State <SortIcon field="state" />
          </button>
          <button
            className="w-24 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('arch')}
          >
            Arch <SortIcon field="arch" />
          </button>
          <button
            className="w-28 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('last_seen_at')}
          >
            Last Seen <SortIcon field="last_seen_at" />
          </button>
        </div>

        {/* Virtual scrolling body */}
        <div
          ref={parentRef}
          className="h-[500px] overflow-auto"
        >
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              Loading nodes...
            </div>
          ) : sortedNodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No nodes found
            </div>
          ) : (
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: '100%',
                position: 'relative',
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const node = sortedNodes[virtualRow.index]
                const isSelected = selectedNodeIds.has(node.id)
                return (
                  <div
                    key={node.id}
                    className={cn(
                      'absolute left-0 right-0 flex items-center border-b last:border-0',
                      isSelected ? 'bg-muted/50' : 'hover:bg-muted/30'
                    )}
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {enableSelection && (
                      <div
                        className="w-12 p-3 flex items-center justify-center"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleNode(node.id)}
                        />
                      </div>
                    )}
                    <Link
                      to={`/nodes/${node.id}`}
                      className="flex-1 flex items-center"
                    >
                      <div className="flex-1 p-3 text-sm font-medium truncate">
                        {node.hostname || (
                          <span className="text-muted-foreground">(undiscovered)</span>
                        )}
                      </div>
                      <div className="w-40 p-3 text-sm font-mono text-muted-foreground">
                        {node.mac_address}
                      </div>
                      <div className="w-32 p-3">
                        <StateBadge state={node.state} />
                      </div>
                      <div className="w-24 p-3 text-sm">{node.arch}</div>
                      <div className="w-28 p-3 text-sm text-muted-foreground">
                        {formatLastSeen(node.last_seen_at)}
                      </div>
                    </Link>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer with count */}
      <div className="text-sm text-muted-foreground">
        Showing {sortedNodes.length} of {nodes.length} nodes
        {selectedNodeIds.size > 0 && ` · ${selectedNodeIds.size} selected`}
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/nodes/NodeTable.tsx
git commit -m "feat(frontend): add selection support to node table"
```

---

## Task 11: Create Groups Page

**Files:**
- Create: `frontend/src/pages/Groups.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create Groups.tsx**

```typescript
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus,
  FolderOpen,
  MoreVertical,
  Pencil,
  Trash2,
  Users,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Label,
  Checkbox,
} from '@/components/ui'
import { useGroups, useCreateGroup, useUpdateGroup, useDeleteGroup } from '@/hooks'
import type { DeviceGroup } from '@/types'
import { cn } from '@/lib/utils'

export function Groups() {
  const { data: response, isLoading } = useGroups()
  const createGroup = useCreateGroup()
  const updateGroup = useUpdateGroup()
  const deleteGroup = useDeleteGroup()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<DeviceGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<DeviceGroup | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    auto_provision: false,
  })

  const groups = response?.data ?? []

  const handleCreate = () => {
    createGroup.mutate(formData, {
      onSuccess: () => {
        setIsCreateOpen(false)
        setFormData({ name: '', description: '', auto_provision: false })
      },
    })
  }

  const handleUpdate = () => {
    if (!editingGroup) return
    updateGroup.mutate(
      { groupId: editingGroup.id, data: formData },
      {
        onSuccess: () => {
          setEditingGroup(null)
          setFormData({ name: '', description: '', auto_provision: false })
        },
      }
    )
  }

  const handleDelete = () => {
    if (!deletingGroup) return
    deleteGroup.mutate(deletingGroup.id, {
      onSuccess: () => setDeletingGroup(null),
    })
  }

  const openEdit = (group: DeviceGroup) => {
    setFormData({
      name: group.name,
      description: group.description ?? '',
      auto_provision: group.auto_provision,
    })
    setEditingGroup(group)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Device Groups</h2>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Group
        </Button>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading groups...</div>
      ) : groups.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <FolderOpen className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No groups created yet.</p>
              <p className="text-sm mt-1">Create a group to organize your nodes.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => (
            <Card key={group.id} className="relative">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <FolderOpen className="h-5 w-5" />
                    {group.name}
                  </CardTitle>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => openEdit(group)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => setDeletingGroup(group)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">
                  {group.description || 'No description'}
                </p>
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1">
                    <Users className="h-4 w-4" />
                    <span>{group.node_count} nodes</span>
                  </div>
                  {group.auto_provision && (
                    <span className="text-xs bg-green-500/10 text-green-600 px-2 py-1 rounded">
                      Auto-provision
                    </span>
                  )}
                </div>
                <Link
                  to={`/groups/${group.id}`}
                  className="absolute inset-0"
                  aria-label={`View ${group.name}`}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Device Group</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Production Servers"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optional description"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="auto_provision"
                checked={formData.auto_provision}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, auto_provision: !!checked })
                }
              />
              <Label htmlFor="auto_provision" className="font-normal">
                Auto-provision new nodes in this group
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!formData.name || createGroup.isPending}>
              {createGroup.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingGroup} onOpenChange={(open) => !open && setEditingGroup(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Device Group</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">Description</Label>
              <Input
                id="edit-description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="edit-auto_provision"
                checked={formData.auto_provision}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, auto_provision: !!checked })
                }
              />
              <Label htmlFor="edit-auto_provision" className="font-normal">
                Auto-provision new nodes in this group
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingGroup(null)}>
              Cancel
            </Button>
            <Button onClick={handleUpdate} disabled={!formData.name || updateGroup.isPending}>
              {updateGroup.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingGroup} onOpenChange={(open) => !open && setDeletingGroup(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Group</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingGroup?.name}</strong>?
            {deletingGroup?.node_count && deletingGroup.node_count > 0 && (
              <span className="block mt-2 text-sm text-muted-foreground">
                This group has {deletingGroup.node_count} nodes. They will be unassigned from this group.
              </span>
            )}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingGroup(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteGroup.isPending}
            >
              {deleteGroup.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

**Step 2: Update pages/index.ts**

```typescript
export { Dashboard } from './Dashboard'
export { Login } from './Login'
export { Nodes } from './Nodes'
export { NodeDetail } from './NodeDetail'
export { Groups } from './Groups'
export { NotFound } from './NotFound'
```

**Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(frontend): add groups page with CRUD operations"
```

---

## Task 12: Create Group Detail Page

**Files:**
- Create: `frontend/src/pages/GroupDetail.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create GroupDetail.tsx**

```typescript
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FolderOpen, Users, Settings, GitBranch } from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
} from '@/components/ui'
import { NodeTable } from '@/components/nodes/NodeTable'
import { useGroup, useGroupNodes } from '@/hooks'

export function GroupDetail() {
  const { groupId } = useParams<{ groupId: string }>()
  const { data: groupResponse, isLoading: groupLoading } = useGroup(groupId ?? '')
  const { data: nodesResponse, isLoading: nodesLoading } = useGroupNodes(groupId ?? '')

  if (groupLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading group details...</div>
      </div>
    )
  }

  const group = groupResponse?.data
  const nodes = nodesResponse?.data ?? []

  if (!group) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/groups">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Groups
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">Group not found</div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/groups">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <FolderOpen className="h-6 w-6" />
              {group.name}
            </h2>
            <p className="text-muted-foreground">
              {group.description || 'No description'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {group.auto_provision && (
            <Badge variant="secondary" className="bg-green-500/10 text-green-600">
              Auto-provision
            </Badge>
          )}
          <Button variant="outline" disabled>
            <Settings className="mr-2 h-4 w-4" />
            Settings
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Nodes</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{group.node_count}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Default Workflow</CardTitle>
            <GitBranch className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {group.default_workflow_id || 'None'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Created</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {new Date(group.created_at).toLocaleDateString()}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Nodes Table */}
      <Card>
        <CardHeader>
          <CardTitle>Nodes in this Group</CardTitle>
        </CardHeader>
        <CardContent>
          <NodeTable
            nodes={nodes}
            isLoading={nodesLoading}
            enableSelection={true}
          />
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Update pages/index.ts**

```typescript
export { Dashboard } from './Dashboard'
export { Login } from './Login'
export { Nodes } from './Nodes'
export { NodeDetail } from './NodeDetail'
export { Groups } from './Groups'
export { GroupDetail } from './GroupDetail'
export { NotFound } from './NotFound'
```

**Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(frontend): add group detail page"
```

---

## Task 13: Update Router and Nodes Page

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/Nodes.tsx`

**Step 1: Update router.tsx**

Add the groups routes and import GroupDetail:

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Login, Nodes, NodeDetail, Groups, GroupDetail, NotFound } from '@/pages'
import { useAuthStore } from '@/stores'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <PublicRoute>
        <Login />
      </PublicRoute>
    ),
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'nodes', element: <Nodes /> },
      { path: 'nodes/:nodeId', element: <NodeDetail /> },
      { path: 'groups', element: <Groups /> },
      { path: 'groups/:groupId', element: <GroupDetail /> },
      { path: 'workflows', element: <div>Workflows (Coming Soon)</div> },
      { path: 'templates', element: <div>Templates (Coming Soon)</div> },
      { path: 'hypervisors', element: <div>Hypervisors (Coming Soon)</div> },
      { path: 'storage', element: <div>Storage (Coming Soon)</div> },
      { path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
      { path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
      { path: 'settings', element: <div>Settings (Coming Soon)</div> },
      { path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
```

**Step 2: Update Nodes.tsx to include BulkActionBar**

```typescript
import { useState } from 'react'
import { Card, CardContent, CardHeader, Button } from '@/components/ui'
import { Plus, RefreshCw } from 'lucide-react'
import { NodeTable, BulkActionBar } from '@/components/nodes'
import { useNodes } from '@/hooks'
import type { NodeState } from '@/types'

export function Nodes() {
  const [stateFilter, setStateFilter] = useState<NodeState | null>(null)

  const { data: response, isLoading, refetch, isFetching } = useNodes(
    stateFilter ? { state: stateFilter, limit: 1000 } : { limit: 1000 }
  )

  const nodes = response?.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Nodes</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button disabled>
            <Plus className="mr-2 h-4 w-4" />
            Register Node
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-0" />
        <CardContent>
          <NodeTable
            nodes={nodes}
            isLoading={isLoading}
            onStateFilter={setStateFilter}
            selectedState={stateFilter}
            enableSelection={true}
          />
        </CardContent>
      </Card>

      <BulkActionBar />
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/router.tsx frontend/src/pages/Nodes.tsx
git commit -m "feat(frontend): add group routes and bulk action bar to nodes page"
```

---

## Task 14: Final Verification and Push

**Step 1: Verify all files are committed**

```bash
git status
```

**Step 2: Push the feature branch**

```bash
git push -u origin feature/groups
```

---

## Phase 3 Complete

**What was built:**
- Group and bulk action type definitions
- Selection store with Zustand for multi-select
- React Query hooks for groups CRUD
- Bulk operation API methods
- Bulk action mutation hooks
- Checkbox, Dialog, and Select UI components
- Bulk action bar component with dialogs
- NodeTable updated with selection support
- Groups list page with create/edit/delete
- Group detail page with nodes table
- Updated routes for groups

**Next Phase:** Storage Infrastructure (Storage backends, file browser, iSCSI LUN management)
