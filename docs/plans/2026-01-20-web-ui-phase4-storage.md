# Web UI Phase 4: Storage Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build storage management UI with backend CRUD, file browser, iSCSI LUN management, and sync jobs.

**Architecture:** Extend Phase 3 with storage-specific types, API client, React Query hooks, and tabbed Storage page. All components follow existing shadcn/ui patterns. Backend APIs are documented but not implemented - frontend will call mock-ready endpoints.

**Tech Stack:** React 18, TypeScript, TanStack Query, React Router v6, Tailwind CSS, Lucide icons

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-storage/frontend`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run npm install, npm run dev, or any execution commands. Only create/edit files and make git commits.

---

## Task 1: Add Storage Types

**Files:**
- Create: `frontend/src/types/storage.ts`
- Modify: `frontend/src/types/index.ts`

**Step 1: Create storage.ts**

```typescript
// Storage Backend Types
export type StorageBackendType = 'nfs' | 'iscsi' | 's3' | 'http'
export type StorageBackendStatus = 'online' | 'offline' | 'error'

export interface NfsConfig {
  server: string
  export_path: string
  mount_options?: string
  auth_method: 'none' | 'kerberos'
}

export interface IscsiTargetConfig {
  target: string
  port: number
  chap_enabled: boolean
}

export interface S3Config {
  endpoint: string
  bucket: string
  region?: string
  access_key_id: string
  secret_access_key?: string // Only for create/update, never returned
  cdn_enabled: boolean
  cdn_url?: string
}

export interface HttpConfig {
  base_url: string
  auth_method: 'none' | 'basic' | 'bearer'
  username?: string
  password?: string // Only for create/update
}

export type StorageBackendConfig = NfsConfig | IscsiTargetConfig | S3Config | HttpConfig

export interface StorageBackendStats {
  used_bytes: number
  total_bytes: number | null
  file_count: number
  template_count: number
}

export interface StorageBackend {
  id: string
  name: string
  type: StorageBackendType
  status: StorageBackendStatus
  config: StorageBackendConfig
  stats: StorageBackendStats
  created_at: string
  updated_at: string
}

// File Browser Types
export type FileType = 'file' | 'directory'

export interface StorageFile {
  name: string
  path: string
  type: FileType
  size: number | null
  mime_type?: string
  modified_at: string
  item_count?: number
}

// iSCSI LUN Types
export type LunPurpose = 'boot_from_san' | 'install_source' | 'auto_provision'
export type LunStatus = 'active' | 'ready' | 'error' | 'creating' | 'deleting'

export interface IscsiLun {
  id: string
  name: string
  size_gb: number
  target_id: string
  target_name: string
  iqn: string
  purpose: LunPurpose
  status: LunStatus
  assigned_node_id: string | null
  assigned_node_name: string | null
  chap_enabled: boolean
  created_at: string
  updated_at: string
}

// Sync Job Types
export type SyncSchedule = 'manual' | 'hourly' | 'daily' | 'weekly' | 'monthly'
export type SyncStatus = 'idle' | 'running' | 'synced' | 'failed'

export interface SyncJobRun {
  id: string
  started_at: string
  completed_at: string | null
  status: 'running' | 'success' | 'failed'
  files_synced: number
  bytes_transferred: number
  error?: string
}

export interface SyncJob {
  id: string
  name: string
  source_url: string
  destination_backend_id: string
  destination_backend_name: string
  destination_path: string
  include_pattern?: string
  exclude_pattern?: string
  schedule: SyncSchedule
  schedule_day?: number
  schedule_time?: string
  verify_checksums: boolean
  delete_removed: boolean
  keep_versions: number
  status: SyncStatus
  last_run_at: string | null
  last_error?: string
  next_run_at: string | null
  created_at: string
  updated_at: string
}

// Display helpers
export const STORAGE_BACKEND_TYPE_LABELS: Record<StorageBackendType, string> = {
  nfs: 'NFS',
  iscsi: 'iSCSI',
  s3: 'S3',
  http: 'HTTP',
}

export const STORAGE_STATUS_COLORS: Record<StorageBackendStatus, string> = {
  online: 'bg-green-500',
  offline: 'bg-gray-500',
  error: 'bg-red-500',
}

export const LUN_PURPOSE_LABELS: Record<LunPurpose, string> = {
  boot_from_san: 'Boot from SAN',
  install_source: 'Install Source',
  auto_provision: 'Auto-provision',
}

export const LUN_STATUS_COLORS: Record<LunStatus, string> = {
  active: 'bg-green-500',
  ready: 'bg-blue-500',
  error: 'bg-red-500',
  creating: 'bg-yellow-500',
  deleting: 'bg-orange-500',
}

export const SYNC_STATUS_COLORS: Record<SyncStatus, string> = {
  idle: 'bg-gray-500',
  running: 'bg-yellow-500',
  synced: 'bg-green-500',
  failed: 'bg-red-500',
}

export const SYNC_SCHEDULE_LABELS: Record<SyncSchedule, string> = {
  manual: 'Manual',
  hourly: 'Hourly',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
}
```

**Step 2: Update types/index.ts**

Add at the end of the file:

```typescript
export type {
  StorageBackendType,
  StorageBackendStatus,
  NfsConfig,
  IscsiTargetConfig,
  S3Config,
  HttpConfig,
  StorageBackendConfig,
  StorageBackendStats,
  StorageBackend,
  FileType,
  StorageFile,
  LunPurpose,
  LunStatus,
  IscsiLun,
  SyncSchedule,
  SyncStatus,
  SyncJobRun,
  SyncJob,
} from './storage'
export {
  STORAGE_BACKEND_TYPE_LABELS,
  STORAGE_STATUS_COLORS,
  LUN_PURPOSE_LABELS,
  LUN_STATUS_COLORS,
  SYNC_STATUS_COLORS,
  SYNC_SCHEDULE_LABELS,
} from './storage'
```

**Step 3: Commit**

```bash
git add frontend/src/types/
git commit -m "feat(frontend): add storage types for backends, files, LUNs, and sync jobs"
```

---

## Task 2: Create Storage API Client

**Files:**
- Create: `frontend/src/api/storage.ts`
- Modify: `frontend/src/api/index.ts`

**Step 1: Create storage.ts**

```typescript
import { apiClient } from './client'
import type {
  ApiResponse,
  ApiListResponse,
  StorageBackend,
  StorageFile,
  IscsiLun,
  SyncJob,
  SyncJobRun,
} from '@/types'

// Storage Backends API
export const storageBackendsApi = {
  async list(): Promise<ApiListResponse<StorageBackend>> {
    return apiClient.get<ApiListResponse<StorageBackend>>('/storage/backends')
  },

  async get(backendId: string): Promise<ApiResponse<StorageBackend>> {
    return apiClient.get<ApiResponse<StorageBackend>>(`/storage/backends/${backendId}`)
  },

  async create(data: Partial<StorageBackend>): Promise<ApiResponse<StorageBackend>> {
    return apiClient.post<ApiResponse<StorageBackend>>('/storage/backends', data)
  },

  async update(backendId: string, data: Partial<StorageBackend>): Promise<ApiResponse<StorageBackend>> {
    return apiClient.patch<ApiResponse<StorageBackend>>(`/storage/backends/${backendId}`, data)
  },

  async delete(backendId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/storage/backends/${backendId}`)
  },

  async test(backendId: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return apiClient.post<ApiResponse<{ success: boolean; message: string }>>(
      `/storage/backends/${backendId}/test`
    )
  },
}

// File Browser API
export const storageFilesApi = {
  async list(backendId: string, path: string = '/'): Promise<ApiListResponse<StorageFile>> {
    return apiClient.get<ApiListResponse<StorageFile>>(
      `/storage/backends/${backendId}/files`,
      { params: { path } }
    )
  },

  async createFolder(backendId: string, path: string, name: string): Promise<ApiResponse<StorageFile>> {
    return apiClient.post<ApiResponse<StorageFile>>(
      `/storage/backends/${backendId}/folders`,
      { path, name }
    )
  },

  async delete(backendId: string, paths: string[]): Promise<ApiResponse<{ deleted: number }>> {
    return apiClient.delete<ApiResponse<{ deleted: number }>>(
      `/storage/backends/${backendId}/files`,
      { data: { paths } }
    )
  },

  async move(
    backendId: string,
    sourcePaths: string[],
    destinationPath: string
  ): Promise<ApiResponse<{ moved: number }>> {
    return apiClient.post<ApiResponse<{ moved: number }>>(
      `/storage/backends/${backendId}/files/move`,
      { source_paths: sourcePaths, destination_path: destinationPath }
    )
  },

  getDownloadUrl(backendId: string, path: string): string {
    return `/api/v1/storage/backends/${backendId}/files/download?path=${encodeURIComponent(path)}`
  },

  getUploadUrl(backendId: string): string {
    return `/api/v1/storage/backends/${backendId}/files`
  },
}

// iSCSI LUNs API
export const lunsApi = {
  async list(): Promise<ApiListResponse<IscsiLun>> {
    return apiClient.get<ApiListResponse<IscsiLun>>('/storage/luns')
  },

  async get(lunId: string): Promise<ApiResponse<IscsiLun>> {
    return apiClient.get<ApiResponse<IscsiLun>>(`/storage/luns/${lunId}`)
  },

  async create(data: Partial<IscsiLun>): Promise<ApiResponse<IscsiLun>> {
    return apiClient.post<ApiResponse<IscsiLun>>('/storage/luns', data)
  },

  async update(lunId: string, data: Partial<IscsiLun>): Promise<ApiResponse<IscsiLun>> {
    return apiClient.patch<ApiResponse<IscsiLun>>(`/storage/luns/${lunId}`, data)
  },

  async delete(lunId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/storage/luns/${lunId}`)
  },

  async assign(lunId: string, nodeId: string): Promise<ApiResponse<IscsiLun>> {
    return apiClient.post<ApiResponse<IscsiLun>>(`/storage/luns/${lunId}/assign`, {
      node_id: nodeId,
    })
  },

  async unassign(lunId: string): Promise<ApiResponse<IscsiLun>> {
    return apiClient.post<ApiResponse<IscsiLun>>(`/storage/luns/${lunId}/unassign`)
  },
}

// Sync Jobs API
export const syncJobsApi = {
  async list(): Promise<ApiListResponse<SyncJob>> {
    return apiClient.get<ApiListResponse<SyncJob>>('/storage/sync-jobs')
  },

  async get(jobId: string): Promise<ApiResponse<SyncJob>> {
    return apiClient.get<ApiResponse<SyncJob>>(`/storage/sync-jobs/${jobId}`)
  },

  async create(data: Partial<SyncJob>): Promise<ApiResponse<SyncJob>> {
    return apiClient.post<ApiResponse<SyncJob>>('/storage/sync-jobs', data)
  },

  async update(jobId: string, data: Partial<SyncJob>): Promise<ApiResponse<SyncJob>> {
    return apiClient.patch<ApiResponse<SyncJob>>(`/storage/sync-jobs/${jobId}`, data)
  },

  async delete(jobId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/storage/sync-jobs/${jobId}`)
  },

  async run(jobId: string): Promise<ApiResponse<SyncJobRun>> {
    return apiClient.post<ApiResponse<SyncJobRun>>(`/storage/sync-jobs/${jobId}/run`)
  },

  async getHistory(jobId: string): Promise<ApiListResponse<SyncJobRun>> {
    return apiClient.get<ApiListResponse<SyncJobRun>>(`/storage/sync-jobs/${jobId}/history`)
  },
}
```

**Step 2: Update api/index.ts**

```typescript
export { apiClient } from './client'
export { authApi } from './auth'
export { nodesApi, groupsApi } from './nodes'
export { storageBackendsApi, storageFilesApi, lunsApi, syncJobsApi } from './storage'
```

**Step 3: Commit**

```bash
git add frontend/src/api/
git commit -m "feat(frontend): add storage API client for backends, files, LUNs, and sync jobs"
```

---

## Task 3: Create Storage Hooks

**Files:**
- Create: `frontend/src/hooks/useStorage.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Create useStorage.ts**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { storageBackendsApi, storageFilesApi, lunsApi, syncJobsApi } from '@/api'
import type { StorageBackend, IscsiLun, SyncJob } from '@/types'

// Query key factories
export const storageKeys = {
  all: ['storage'] as const,
  backends: () => [...storageKeys.all, 'backends'] as const,
  backend: (id: string) => [...storageKeys.backends(), id] as const,
  files: (backendId: string, path: string) => [...storageKeys.all, 'files', backendId, path] as const,
  luns: () => [...storageKeys.all, 'luns'] as const,
  lun: (id: string) => [...storageKeys.luns(), id] as const,
  syncJobs: () => [...storageKeys.all, 'sync-jobs'] as const,
  syncJob: (id: string) => [...storageKeys.syncJobs(), id] as const,
  syncJobHistory: (id: string) => [...storageKeys.syncJob(id), 'history'] as const,
}

// Storage Backends Hooks
export function useStorageBackends() {
  return useQuery({
    queryKey: storageKeys.backends(),
    queryFn: () => storageBackendsApi.list(),
  })
}

export function useStorageBackend(backendId: string) {
  return useQuery({
    queryKey: storageKeys.backend(backendId),
    queryFn: () => storageBackendsApi.get(backendId),
    enabled: !!backendId,
  })
}

export function useCreateStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Partial<StorageBackend>) => storageBackendsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.backends() })
    },
  })
}

export function useUpdateStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ backendId, data }: { backendId: string; data: Partial<StorageBackend> }) =>
      storageBackendsApi.update(backendId, data),
    onSuccess: (_, { backendId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.backend(backendId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.backends() })
    },
  })
}

export function useDeleteStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (backendId: string) => storageBackendsApi.delete(backendId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.backends() })
    },
  })
}

export function useTestStorageBackend() {
  return useMutation({
    mutationFn: (backendId: string) => storageBackendsApi.test(backendId),
  })
}

// File Browser Hooks
export function useStorageFiles(backendId: string, path: string) {
  return useQuery({
    queryKey: storageKeys.files(backendId, path),
    queryFn: () => storageFilesApi.list(backendId, path),
    enabled: !!backendId,
  })
}

export function useCreateFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ backendId, path, name }: { backendId: string; path: string; name: string }) =>
      storageFilesApi.createFolder(backendId, path, name),
    onSuccess: (_, { backendId, path }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.files(backendId, path) })
    },
  })
}

export function useDeleteFiles() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ backendId, paths }: { backendId: string; paths: string[] }) =>
      storageFilesApi.delete(backendId, paths),
    onSuccess: (_, { backendId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.all })
    },
  })
}

export function useMoveFiles() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      backendId,
      sourcePaths,
      destinationPath,
    }: {
      backendId: string
      sourcePaths: string[]
      destinationPath: string
    }) => storageFilesApi.move(backendId, sourcePaths, destinationPath),
    onSuccess: (_, { backendId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.all })
    },
  })
}

// iSCSI LUN Hooks
export function useLuns() {
  return useQuery({
    queryKey: storageKeys.luns(),
    queryFn: () => lunsApi.list(),
  })
}

export function useLun(lunId: string) {
  return useQuery({
    queryKey: storageKeys.lun(lunId),
    queryFn: () => lunsApi.get(lunId),
    enabled: !!lunId,
  })
}

export function useCreateLun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Partial<IscsiLun>) => lunsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.luns() })
    },
  })
}

export function useUpdateLun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ lunId, data }: { lunId: string; data: Partial<IscsiLun> }) =>
      lunsApi.update(lunId, data),
    onSuccess: (_, { lunId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.lun(lunId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.luns() })
    },
  })
}

export function useDeleteLun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (lunId: string) => lunsApi.delete(lunId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.luns() })
    },
  })
}

export function useAssignLun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ lunId, nodeId }: { lunId: string; nodeId: string }) =>
      lunsApi.assign(lunId, nodeId),
    onSuccess: (_, { lunId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.lun(lunId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.luns() })
    },
  })
}

export function useUnassignLun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (lunId: string) => lunsApi.unassign(lunId),
    onSuccess: (_, lunId) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.lun(lunId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.luns() })
    },
  })
}

// Sync Jobs Hooks
export function useSyncJobs() {
  return useQuery({
    queryKey: storageKeys.syncJobs(),
    queryFn: () => syncJobsApi.list(),
  })
}

export function useSyncJob(jobId: string) {
  return useQuery({
    queryKey: storageKeys.syncJob(jobId),
    queryFn: () => syncJobsApi.get(jobId),
    enabled: !!jobId,
  })
}

export function useSyncJobHistory(jobId: string) {
  return useQuery({
    queryKey: storageKeys.syncJobHistory(jobId),
    queryFn: () => syncJobsApi.getHistory(jobId),
    enabled: !!jobId,
  })
}

export function useCreateSyncJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Partial<SyncJob>) => syncJobsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJobs() })
    },
  })
}

export function useUpdateSyncJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ jobId, data }: { jobId: string; data: Partial<SyncJob> }) =>
      syncJobsApi.update(jobId, data),
    onSuccess: (_, { jobId }) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJob(jobId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJobs() })
    },
  })
}

export function useDeleteSyncJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (jobId: string) => syncJobsApi.delete(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJobs() })
    },
  })
}

export function useRunSyncJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (jobId: string) => syncJobsApi.run(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJob(jobId) })
      queryClient.invalidateQueries({ queryKey: storageKeys.syncJobs() })
    },
  })
}
```

**Step 2: Update hooks/index.ts**

Add the storage hook exports:

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
export {
  useBulkAssignGroup,
  useBulkAssignWorkflow,
  useBulkAddTag,
  useBulkRemoveTag,
  useBulkChangeState,
} from './useBulkActions'
export {
  storageKeys,
  useStorageBackends,
  useStorageBackend,
  useCreateStorageBackend,
  useUpdateStorageBackend,
  useDeleteStorageBackend,
  useTestStorageBackend,
  useStorageFiles,
  useCreateFolder,
  useDeleteFiles,
  useMoveFiles,
  useLuns,
  useLun,
  useCreateLun,
  useUpdateLun,
  useDeleteLun,
  useAssignLun,
  useUnassignLun,
  useSyncJobs,
  useSyncJob,
  useSyncJobHistory,
  useCreateSyncJob,
  useUpdateSyncJob,
  useDeleteSyncJob,
  useRunSyncJob,
} from './useStorage'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add React Query hooks for storage management"
```

---

## Task 4: Create Tabs Component

**Files:**
- Create: `frontend/src/components/ui/tabs.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Create tabs.tsx**

```typescript
import * as React from 'react'
import { cn } from '@/lib/utils'

interface TabsContextValue {
  value: string
  onValueChange: (value: string) => void
}

const TabsContext = React.createContext<TabsContextValue | null>(null)

function useTabsContext() {
  const context = React.useContext(TabsContext)
  if (!context) {
    throw new Error('Tabs components must be used within a Tabs')
  }
  return context
}

interface TabsProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  children: React.ReactNode
  className?: string
}

function Tabs({ value, defaultValue, onValueChange, children, className }: TabsProps) {
  const [internalValue, setInternalValue] = React.useState(defaultValue ?? '')
  const isControlled = value !== undefined
  const currentValue = isControlled ? value : internalValue
  const setValue = isControlled ? onValueChange! : setInternalValue

  return (
    <TabsContext.Provider value={{ value: currentValue, onValueChange: setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

interface TabsListProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

function TabsList({ className, children, ...props }: TabsListProps) {
  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string
  children: React.ReactNode
}

function TabsTrigger({ value, className, children, ...props }: TabsTriggerProps) {
  const { value: selectedValue, onValueChange } = useTabsContext()
  const isSelected = selectedValue === value

  return (
    <button
      type="button"
      role="tab"
      aria-selected={isSelected}
      onClick={() => onValueChange(value)}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1',
        'text-sm font-medium ring-offset-background transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        isSelected
          ? 'bg-background text-foreground shadow'
          : 'hover:bg-background/50 hover:text-foreground',
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}

interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string
  children: React.ReactNode
}

function TabsContent({ value, className, children, ...props }: TabsContentProps) {
  const { value: selectedValue } = useTabsContext()

  if (selectedValue !== value) return null

  return (
    <div
      role="tabpanel"
      className={cn('mt-2 ring-offset-background focus-visible:outline-none', className)}
      {...props}
    >
      {children}
    </div>
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
```

**Step 2: Update ui/index.ts**

Add the tabs exports:

```typescript
export { Badge } from './badge'
export { Button } from './button'
export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent } from './card'
export { Checkbox } from './checkbox'
export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './dialog'
export { Input } from './input'
export { Label } from './label'
export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from './select'
export { Separator } from './separator'
export { Tabs, TabsList, TabsTrigger, TabsContent } from './tabs'
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(frontend): add tabs component"
```

---

## Task 5: Create BackendCard Component

**Files:**
- Create: `frontend/src/components/storage/BackendCard.tsx`
- Create: `frontend/src/components/storage/index.ts`

**Step 1: Create BackendCard.tsx**

```typescript
import { HardDrive, Server, Cloud, Globe, MoreVertical, Pencil, Trash2, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from '@/components/ui'
import {
  STORAGE_BACKEND_TYPE_LABELS,
  STORAGE_STATUS_COLORS,
  type StorageBackend,
  type StorageBackendType,
} from '@/types'
import { cn } from '@/lib/utils'

const TYPE_ICONS: Record<StorageBackendType, React.ElementType> = {
  nfs: Server,
  iscsi: HardDrive,
  s3: Cloud,
  http: Globe,
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function getBackendUrl(backend: StorageBackend): string {
  const { config, type } = backend
  switch (type) {
    case 'nfs':
      return `nfs://${(config as { server: string; export_path: string }).server}${(config as { export_path: string }).export_path}`
    case 'iscsi':
      return `iscsi://${(config as { target: string; port: number }).target}:${(config as { port: number }).port}`
    case 's3':
      return `s3://${(config as { bucket: string }).bucket}`
    case 'http':
      return (config as { base_url: string }).base_url
    default:
      return ''
  }
}

interface BackendCardProps {
  backend: StorageBackend
  onEdit: (backend: StorageBackend) => void
  onDelete: (backend: StorageBackend) => void
  onTest: (backend: StorageBackend) => void
}

export function BackendCard({ backend, onEdit, onDelete, onTest }: BackendCardProps) {
  const Icon = TYPE_ICONS[backend.type]
  const usagePercent = backend.stats.total_bytes
    ? Math.round((backend.stats.used_bytes / backend.stats.total_bytes) * 100)
    : null

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn('h-2 w-2 rounded-full', STORAGE_STATUS_COLORS[backend.status])} />
            <CardTitle className="text-lg flex items-center gap-2">
              <Icon className="h-5 w-5" />
              {backend.name}
            </CardTitle>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onTest(backend)}
              title="Test connection"
            >
              <Zap className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(backend)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => onDelete(backend)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-2 font-mono truncate">
          {getBackendUrl(backend)}
        </p>

        <div className="flex items-center justify-between text-sm mb-2">
          <Badge variant="outline">{STORAGE_BACKEND_TYPE_LABELS[backend.type]}</Badge>
          <span className="text-muted-foreground">
            {backend.stats.template_count} templates
          </span>
        </div>

        {usagePercent !== null && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{formatBytes(backend.stats.used_bytes)} used</span>
              <span>{formatBytes(backend.stats.total_bytes!)} total</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full',
                  usagePercent > 90 ? 'bg-red-500' : usagePercent > 70 ? 'bg-yellow-500' : 'bg-green-500'
                )}
                style={{ width: `${usagePercent}%` }}
              />
            </div>
          </div>
        )}

        {usagePercent === null && (
          <div className="text-sm text-muted-foreground">
            {formatBytes(backend.stats.used_bytes)} · {backend.stats.file_count} files
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

**Step 2: Create storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add storage backend card component"
```

---

## Task 6: Create BackendForm Component

**Files:**
- Create: `frontend/src/components/storage/BackendForm.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create BackendForm.tsx**

```typescript
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Checkbox,
} from '@/components/ui'
import {
  STORAGE_BACKEND_TYPE_LABELS,
  type StorageBackend,
  type StorageBackendType,
  type NfsConfig,
  type IscsiTargetConfig,
  type S3Config,
  type HttpConfig,
} from '@/types'

interface BackendFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  backend?: StorageBackend | null
  onSubmit: (data: Partial<StorageBackend>) => void
  isPending: boolean
}

const DEFAULT_NFS: NfsConfig = {
  server: '',
  export_path: '',
  mount_options: 'vers=4.1',
  auth_method: 'none',
}

const DEFAULT_ISCSI: IscsiTargetConfig = {
  target: '',
  port: 3260,
  chap_enabled: false,
}

const DEFAULT_S3: S3Config = {
  endpoint: '',
  bucket: '',
  region: '',
  access_key_id: '',
  cdn_enabled: false,
}

const DEFAULT_HTTP: HttpConfig = {
  base_url: '',
  auth_method: 'none',
}

export function BackendForm({ open, onOpenChange, backend, onSubmit, isPending }: BackendFormProps) {
  const [name, setName] = useState('')
  const [type, setType] = useState<StorageBackendType>('nfs')
  const [nfsConfig, setNfsConfig] = useState<NfsConfig>(DEFAULT_NFS)
  const [iscsiConfig, setIscsiConfig] = useState<IscsiTargetConfig>(DEFAULT_ISCSI)
  const [s3Config, setS3Config] = useState<S3Config>(DEFAULT_S3)
  const [httpConfig, setHttpConfig] = useState<HttpConfig>(DEFAULT_HTTP)

  const isEditing = !!backend

  useEffect(() => {
    if (backend) {
      setName(backend.name)
      setType(backend.type)
      switch (backend.type) {
        case 'nfs':
          setNfsConfig(backend.config as NfsConfig)
          break
        case 'iscsi':
          setIscsiConfig(backend.config as IscsiTargetConfig)
          break
        case 's3':
          setS3Config(backend.config as S3Config)
          break
        case 'http':
          setHttpConfig(backend.config as HttpConfig)
          break
      }
    } else {
      setName('')
      setType('nfs')
      setNfsConfig(DEFAULT_NFS)
      setIscsiConfig(DEFAULT_ISCSI)
      setS3Config(DEFAULT_S3)
      setHttpConfig(DEFAULT_HTTP)
    }
  }, [backend, open])

  const handleSubmit = () => {
    let config
    switch (type) {
      case 'nfs':
        config = nfsConfig
        break
      case 'iscsi':
        config = iscsiConfig
        break
      case 's3':
        config = s3Config
        break
      case 'http':
        config = httpConfig
        break
    }
    onSubmit({ name, type, config })
  }

  const isValid = name.trim() !== ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Storage Backend' : 'Add Storage Backend'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., NFS - Primary"
            />
          </div>

          <div className="space-y-2">
            <Label>Type</Label>
            <Select value={type} onValueChange={(v) => setType(v as StorageBackendType)} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(STORAGE_BACKEND_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {type === 'nfs' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="nfs-server">Server</Label>
                <Input
                  id="nfs-server"
                  value={nfsConfig.server}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, server: e.target.value })}
                  placeholder="storage.local"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nfs-path">Export Path</Label>
                <Input
                  id="nfs-path"
                  value={nfsConfig.export_path}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, export_path: e.target.value })}
                  placeholder="/pureboot"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nfs-options">Mount Options</Label>
                <Input
                  id="nfs-options"
                  value={nfsConfig.mount_options ?? ''}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, mount_options: e.target.value })}
                  placeholder="vers=4.1,rsize=1048576"
                />
              </div>
            </>
          )}

          {type === 'iscsi' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="iscsi-target">Target Address</Label>
                <Input
                  id="iscsi-target"
                  value={iscsiConfig.target}
                  onChange={(e) => setIscsiConfig({ ...iscsiConfig, target: e.target.value })}
                  placeholder="san.local"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="iscsi-port">Port</Label>
                <Input
                  id="iscsi-port"
                  type="number"
                  value={iscsiConfig.port}
                  onChange={(e) => setIscsiConfig({ ...iscsiConfig, port: parseInt(e.target.value) || 3260 })}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="iscsi-chap"
                  checked={iscsiConfig.chap_enabled}
                  onCheckedChange={(checked) => setIscsiConfig({ ...iscsiConfig, chap_enabled: !!checked })}
                />
                <Label htmlFor="iscsi-chap" className="font-normal">
                  Enable CHAP authentication
                </Label>
              </div>
            </>
          )}

          {type === 's3' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="s3-endpoint">Endpoint URL</Label>
                <Input
                  id="s3-endpoint"
                  value={s3Config.endpoint}
                  onChange={(e) => setS3Config({ ...s3Config, endpoint: e.target.value })}
                  placeholder="https://s3.amazonaws.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-bucket">Bucket</Label>
                <Input
                  id="s3-bucket"
                  value={s3Config.bucket}
                  onChange={(e) => setS3Config({ ...s3Config, bucket: e.target.value })}
                  placeholder="pureboot-images"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-region">Region (optional)</Label>
                <Input
                  id="s3-region"
                  value={s3Config.region ?? ''}
                  onChange={(e) => setS3Config({ ...s3Config, region: e.target.value })}
                  placeholder="us-east-1"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-access-key">Access Key ID</Label>
                <Input
                  id="s3-access-key"
                  value={s3Config.access_key_id}
                  onChange={(e) => setS3Config({ ...s3Config, access_key_id: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-secret-key">Secret Access Key</Label>
                <Input
                  id="s3-secret-key"
                  type="password"
                  value={s3Config.secret_access_key ?? ''}
                  onChange={(e) => setS3Config({ ...s3Config, secret_access_key: e.target.value })}
                  placeholder={isEditing ? '(unchanged)' : ''}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="s3-cdn"
                  checked={s3Config.cdn_enabled}
                  onCheckedChange={(checked) => setS3Config({ ...s3Config, cdn_enabled: !!checked })}
                />
                <Label htmlFor="s3-cdn" className="font-normal">
                  Enable CDN
                </Label>
              </div>
              {s3Config.cdn_enabled && (
                <div className="space-y-2">
                  <Label htmlFor="s3-cdn-url">CDN URL</Label>
                  <Input
                    id="s3-cdn-url"
                    value={s3Config.cdn_url ?? ''}
                    onChange={(e) => setS3Config({ ...s3Config, cdn_url: e.target.value })}
                    placeholder="https://cdn.example.com"
                  />
                </div>
              )}
            </>
          )}

          {type === 'http' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="http-url">Base URL</Label>
                <Input
                  id="http-url"
                  value={httpConfig.base_url}
                  onChange={(e) => setHttpConfig({ ...httpConfig, base_url: e.target.value })}
                  placeholder="https://files.example.com"
                />
              </div>
              <div className="space-y-2">
                <Label>Authentication</Label>
                <Select
                  value={httpConfig.auth_method}
                  onValueChange={(v) => setHttpConfig({ ...httpConfig, auth_method: v as 'none' | 'basic' | 'bearer' })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="basic">Basic Auth</SelectItem>
                    <SelectItem value="bearer">Bearer Token</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {httpConfig.auth_method === 'basic' && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="http-username">Username</Label>
                    <Input
                      id="http-username"
                      value={httpConfig.username ?? ''}
                      onChange={(e) => setHttpConfig({ ...httpConfig, username: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="http-password">Password</Label>
                    <Input
                      id="http-password"
                      type="password"
                      value={httpConfig.password ?? ''}
                      onChange={(e) => setHttpConfig({ ...httpConfig, password: e.target.value })}
                      placeholder={isEditing ? '(unchanged)' : ''}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || isPending}>
            {isPending ? 'Saving...' : isEditing ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add storage backend form dialog"
```

---

## Task 7: Create FileBrowser Component

**Files:**
- Create: `frontend/src/components/storage/FileBrowser.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create FileBrowser.tsx**

```typescript
import { useState } from 'react'
import {
  Folder,
  File,
  ChevronRight,
  Home,
  Upload,
  FolderPlus,
  Download,
  Trash2,
  Move,
} from 'lucide-react'
import {
  Button,
  Input,
  Checkbox,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useStorageFiles, useCreateFolder, useDeleteFiles, useStorageBackends } from '@/hooks'
import { storageFilesApi } from '@/api'
import type { StorageFile, StorageBackend } from '@/types'
import { cn } from '@/lib/utils'

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '—'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

interface FileBrowserProps {
  initialBackendId?: string
}

export function FileBrowser({ initialBackendId }: FileBrowserProps) {
  const [backendId, setBackendId] = useState(initialBackendId ?? '')
  const [currentPath, setCurrentPath] = useState('/')
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  const { data: backendsResponse } = useStorageBackends()
  const { data: filesResponse, isLoading } = useStorageFiles(backendId, currentPath)
  const createFolder = useCreateFolder()
  const deleteFiles = useDeleteFiles()

  const backends = backendsResponse?.data ?? []
  const files = filesResponse?.data ?? []

  const pathParts = currentPath.split('/').filter(Boolean)

  const toggleFile = (path: string) => {
    const newSet = new Set(selectedFiles)
    if (newSet.has(path)) {
      newSet.delete(path)
    } else {
      newSet.add(path)
    }
    setSelectedFiles(newSet)
  }

  const selectAll = () => {
    if (selectedFiles.size === files.length) {
      setSelectedFiles(new Set())
    } else {
      setSelectedFiles(new Set(files.map((f) => f.path)))
    }
  }

  const navigateTo = (path: string) => {
    setCurrentPath(path)
    setSelectedFiles(new Set())
  }

  const navigateToIndex = (index: number) => {
    const newPath = '/' + pathParts.slice(0, index + 1).join('/')
    navigateTo(newPath)
  }

  const handleFileClick = (file: StorageFile) => {
    if (file.type === 'directory') {
      navigateTo(file.path)
    }
  }

  const handleCreateFolder = () => {
    if (newFolderName.trim() && backendId) {
      createFolder.mutate(
        { backendId, path: currentPath, name: newFolderName.trim() },
        {
          onSuccess: () => {
            setIsNewFolderOpen(false)
            setNewFolderName('')
          },
        }
      )
    }
  }

  const handleDelete = () => {
    if (selectedFiles.size > 0 && backendId) {
      if (confirm(`Delete ${selectedFiles.size} item(s)?`)) {
        deleteFiles.mutate(
          { backendId, paths: Array.from(selectedFiles) },
          {
            onSuccess: () => setSelectedFiles(new Set()),
          }
        )
      }
    }
  }

  const handleDownload = () => {
    if (selectedFiles.size === 1 && backendId) {
      const path = Array.from(selectedFiles)[0]
      const url = storageFilesApi.getDownloadUrl(backendId, path)
      window.open(url, '_blank')
    }
  }

  const someSelected = selectedFiles.size > 0
  const allSelected = files.length > 0 && selectedFiles.size === files.length
  const singleFileSelected = selectedFiles.size === 1 && files.find((f) => f.path === Array.from(selectedFiles)[0])?.type === 'file'

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-4">
        <div className="w-64">
          <Select value={backendId} onValueChange={(v) => { setBackendId(v); setCurrentPath('/'); setSelectedFiles(new Set()) }}>
            <SelectTrigger>
              <SelectValue placeholder="Select backend..." />
            </SelectTrigger>
            <SelectContent>
              {backends.map((b) => (
                <SelectItem key={b.id} value={b.id}>
                  {b.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1" />

        <Button variant="outline" size="sm" onClick={() => setIsNewFolderOpen(true)} disabled={!backendId}>
          <FolderPlus className="h-4 w-4 mr-2" />
          New Folder
        </Button>

        <Button variant="outline" size="sm" disabled={!backendId}>
          <Upload className="h-4 w-4 mr-2" />
          Upload
        </Button>

        {someSelected && (
          <>
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={!singleFileSelected}>
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button variant="outline" size="sm" onClick={handleDelete} className="text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              Delete ({selectedFiles.size})
            </Button>
          </>
        )}
      </div>

      {/* Breadcrumb */}
      {backendId && (
        <div className="flex items-center gap-1 text-sm">
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => navigateTo('/')}>
            <Home className="h-4 w-4" />
          </Button>
          {pathParts.map((part, index) => (
            <div key={index} className="flex items-center">
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => navigateToIndex(index)}
              >
                {part}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* File List */}
      <div className="rounded-md border">
        {/* Header */}
        <div className="flex items-center border-b bg-muted/50 text-sm font-medium">
          <div className="w-12 p-3 flex items-center justify-center">
            <Checkbox
              checked={allSelected}
              indeterminate={someSelected && !allSelected}
              onCheckedChange={selectAll}
              disabled={!backendId || files.length === 0}
            />
          </div>
          <div className="flex-1 p-3">Name</div>
          <div className="w-24 p-3 text-right">Size</div>
          <div className="w-32 p-3">Type</div>
          <div className="w-32 p-3">Modified</div>
        </div>

        {/* Body */}
        <div className="max-h-[400px] overflow-auto">
          {!backendId ? (
            <div className="p-8 text-center text-muted-foreground">
              Select a storage backend to browse files
            </div>
          ) : isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : files.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              This folder is empty
            </div>
          ) : (
            files.map((file) => (
              <div
                key={file.path}
                className={cn(
                  'flex items-center border-b last:border-0 hover:bg-muted/30',
                  selectedFiles.has(file.path) && 'bg-muted/50'
                )}
              >
                <div className="w-12 p-3 flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selectedFiles.has(file.path)}
                    onCheckedChange={() => toggleFile(file.path)}
                  />
                </div>
                <div
                  className="flex-1 p-3 flex items-center gap-2 cursor-pointer"
                  onClick={() => handleFileClick(file)}
                >
                  {file.type === 'directory' ? (
                    <Folder className="h-4 w-4 text-blue-500" />
                  ) : (
                    <File className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="truncate">{file.name}</span>
                  {file.type === 'directory' && file.item_count !== undefined && (
                    <span className="text-xs text-muted-foreground">({file.item_count} items)</span>
                  )}
                </div>
                <div className="w-24 p-3 text-right text-sm text-muted-foreground">
                  {formatBytes(file.size)}
                </div>
                <div className="w-32 p-3 text-sm text-muted-foreground">
                  {file.type === 'directory' ? 'Folder' : file.mime_type ?? 'File'}
                </div>
                <div className="w-32 p-3 text-sm text-muted-foreground">
                  {formatDate(file.modified_at)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* New Folder Dialog */}
      <Dialog open={isNewFolderOpen} onOpenChange={setIsNewFolderOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Folder</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="folder-name">Folder Name</Label>
            <Input
              id="folder-name"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="New folder"
              className="mt-2"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNewFolderOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateFolder} disabled={!newFolderName.trim() || createFolder.isPending}>
              {createFolder.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
export { FileBrowser } from './FileBrowser'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add file browser component"
```

---

## Task 8: Create LunTable Component

**Files:**
- Create: `frontend/src/components/storage/LunTable.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create LunTable.tsx**

```typescript
import { useState } from 'react'
import { Plus, Pencil, Trash2, Link, Unlink } from 'lucide-react'
import {
  Button,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useLuns, useDeleteLun, useAssignLun, useUnassignLun, useNodes } from '@/hooks'
import { LUN_PURPOSE_LABELS, LUN_STATUS_COLORS, type IscsiLun } from '@/types'
import { cn } from '@/lib/utils'

interface LunTableProps {
  onEdit: (lun: IscsiLun) => void
  onCreate: () => void
}

export function LunTable({ onEdit, onCreate }: LunTableProps) {
  const { data: lunsResponse, isLoading } = useLuns()
  const { data: nodesResponse } = useNodes({ limit: 1000 })
  const deleteLun = useDeleteLun()
  const assignLun = useAssignLun()
  const unassignLun = useUnassignLun()

  const [assignDialogLun, setAssignDialogLun] = useState<IscsiLun | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [deletingLun, setDeletingLun] = useState<IscsiLun | null>(null)

  const luns = lunsResponse?.data ?? []
  const nodes = nodesResponse?.data ?? []

  const handleAssign = () => {
    if (assignDialogLun && selectedNodeId) {
      assignLun.mutate(
        { lunId: assignDialogLun.id, nodeId: selectedNodeId },
        {
          onSuccess: () => {
            setAssignDialogLun(null)
            setSelectedNodeId('')
          },
        }
      )
    }
  }

  const handleUnassign = (lun: IscsiLun) => {
    if (confirm(`Unassign LUN "${lun.name}" from ${lun.assigned_node_name}?`)) {
      unassignLun.mutate(lun.id)
    }
  }

  const handleDelete = () => {
    if (deletingLun) {
      deleteLun.mutate(deletingLun.id, {
        onSuccess: () => setDeletingLun(null),
      })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Create LUN
        </Button>
      </div>

      <div className="rounded-md border">
        {/* Header */}
        <div className="flex items-center border-b bg-muted/50 text-sm font-medium">
          <div className="flex-1 p-3">Name</div>
          <div className="w-24 p-3">Size</div>
          <div className="w-40 p-3">Assigned To</div>
          <div className="w-32 p-3">Purpose</div>
          <div className="w-24 p-3">Status</div>
          <div className="w-32 p-3">Actions</div>
        </div>

        {/* Body */}
        <div className="max-h-[500px] overflow-auto">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading LUNs...</div>
          ) : luns.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No iSCSI LUNs configured
            </div>
          ) : (
            luns.map((lun) => (
              <div key={lun.id} className="flex items-center border-b last:border-0 hover:bg-muted/30">
                <div className="flex-1 p-3">
                  <div className="font-medium">{lun.name}</div>
                  <div className="text-xs text-muted-foreground font-mono truncate">
                    {lun.iqn}
                  </div>
                </div>
                <div className="w-24 p-3 text-sm">{lun.size_gb} GB</div>
                <div className="w-40 p-3 text-sm">
                  {lun.assigned_node_name ?? (
                    <span className="text-muted-foreground">(unassigned)</span>
                  )}
                </div>
                <div className="w-32 p-3">
                  <Badge variant="outline">{LUN_PURPOSE_LABELS[lun.purpose]}</Badge>
                </div>
                <div className="w-24 p-3">
                  <div className="flex items-center gap-2">
                    <div className={cn('h-2 w-2 rounded-full', LUN_STATUS_COLORS[lun.status])} />
                    <span className="text-sm capitalize">{lun.status}</span>
                  </div>
                </div>
                <div className="w-32 p-3 flex gap-1">
                  {lun.assigned_node_id ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => handleUnassign(lun)}
                      title="Unassign"
                    >
                      <Unlink className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setAssignDialogLun(lun)}
                      title="Assign to node"
                    >
                      <Link className="h-4 w-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => onEdit(lun)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive"
                    onClick={() => setDeletingLun(lun)}
                    disabled={!!lun.assigned_node_id}
                    title={lun.assigned_node_id ? 'Unassign before deleting' : 'Delete'}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Assign Dialog */}
      <Dialog open={!!assignDialogLun} onOpenChange={(open) => !open && setAssignDialogLun(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign LUN to Node</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Assign <strong>{assignDialogLun?.name}</strong> to a node:
            </p>
            <Select value={selectedNodeId} onValueChange={setSelectedNodeId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a node..." />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((node) => (
                  <SelectItem key={node.id} value={node.id}>
                    {node.hostname ?? node.mac_address}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignDialogLun(null)}>
              Cancel
            </Button>
            <Button onClick={handleAssign} disabled={!selectedNodeId || assignLun.isPending}>
              {assignLun.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deletingLun} onOpenChange={(open) => !open && setDeletingLun(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete LUN</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingLun?.name}</strong>?
            This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingLun(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteLun.isPending}>
              {deleteLun.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
export { FileBrowser } from './FileBrowser'
export { LunTable } from './LunTable'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add iSCSI LUN table component"
```

---

## Task 9: Create LunForm Component

**Files:**
- Create: `frontend/src/components/storage/LunForm.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create LunForm.tsx**

```typescript
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Checkbox,
} from '@/components/ui'
import { useStorageBackends } from '@/hooks'
import { LUN_PURPOSE_LABELS, type IscsiLun, type LunPurpose } from '@/types'

interface LunFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  lun?: IscsiLun | null
  onSubmit: (data: Partial<IscsiLun>) => void
  isPending: boolean
}

export function LunForm({ open, onOpenChange, lun, onSubmit, isPending }: LunFormProps) {
  const [name, setName] = useState('')
  const [sizeGb, setSizeGb] = useState(100)
  const [targetId, setTargetId] = useState('')
  const [purpose, setPurpose] = useState<LunPurpose>('boot_from_san')
  const [chapEnabled, setChapEnabled] = useState(false)

  const { data: backendsResponse } = useStorageBackends()
  const backends = backendsResponse?.data ?? []
  const iscsiBackends = backends.filter((b) => b.type === 'iscsi')

  const isEditing = !!lun

  useEffect(() => {
    if (lun) {
      setName(lun.name)
      setSizeGb(lun.size_gb)
      setTargetId(lun.target_id)
      setPurpose(lun.purpose)
      setChapEnabled(lun.chap_enabled)
    } else {
      setName('')
      setSizeGb(100)
      setTargetId(iscsiBackends[0]?.id ?? '')
      setPurpose('boot_from_san')
      setChapEnabled(false)
    }
  }, [lun, open, iscsiBackends])

  const handleSubmit = () => {
    onSubmit({
      name,
      size_gb: sizeGb,
      target_id: targetId,
      purpose,
      chap_enabled: chapEnabled,
    })
  }

  const isValid = name.trim() !== '' && targetId !== '' && sizeGb > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit iSCSI LUN' : 'Create iSCSI LUN'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="lun-name">Name</Label>
            <Input
              id="lun-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., web-server-01-boot"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="lun-size">Size (GB)</Label>
            <Input
              id="lun-size"
              type="number"
              value={sizeGb}
              onChange={(e) => setSizeGb(parseInt(e.target.value) || 0)}
              min={1}
              disabled={isEditing}
            />
            {isEditing && (
              <p className="text-xs text-muted-foreground">Size cannot be changed after creation</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>iSCSI Target</Label>
            <Select value={targetId} onValueChange={setTargetId} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue placeholder="Select target..." />
              </SelectTrigger>
              <SelectContent>
                {iscsiBackends.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {iscsiBackends.length === 0 && (
              <p className="text-xs text-destructive">No iSCSI backends configured</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Purpose</Label>
            <Select value={purpose} onValueChange={(v) => setPurpose(v as LunPurpose)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(LUN_PURPOSE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {purpose === 'boot_from_san' && 'Node boots and runs from this LUN'}
              {purpose === 'install_source' && 'Mounted during installation only'}
              {purpose === 'auto_provision' && 'Assigned automatically to new nodes'}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="lun-chap"
              checked={chapEnabled}
              onCheckedChange={(checked) => setChapEnabled(!!checked)}
            />
            <Label htmlFor="lun-chap" className="font-normal">
              Enable CHAP authentication
            </Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || isPending}>
            {isPending ? 'Saving...' : isEditing ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
export { FileBrowser } from './FileBrowser'
export { LunTable } from './LunTable'
export { LunForm } from './LunForm'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add iSCSI LUN form dialog"
```

---

## Task 10: Create SyncJobCard Component

**Files:**
- Create: `frontend/src/components/storage/SyncJobCard.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create SyncJobCard.tsx**

```typescript
import { RefreshCw, Pencil, Trash2, Play, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from '@/components/ui'
import { SYNC_STATUS_COLORS, SYNC_SCHEDULE_LABELS, type SyncJob } from '@/types'
import { cn } from '@/lib/utils'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}

interface SyncJobCardProps {
  job: SyncJob
  onEdit: (job: SyncJob) => void
  onDelete: (job: SyncJob) => void
  onRun: (job: SyncJob) => void
  isRunning: boolean
}

export function SyncJobCard({ job, onEdit, onDelete, onRun, isRunning }: SyncJobCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn('h-2 w-2 rounded-full', SYNC_STATUS_COLORS[job.status])} />
            <CardTitle className="text-lg">{job.name}</CardTitle>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onRun(job)}
              disabled={isRunning || job.status === 'running'}
              title="Run now"
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(job)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => onDelete(job)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Source:</span>
            <span className="font-mono truncate">{job.source_url}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Destination:</span>
            <span>{job.destination_backend_name} {job.destination_path}</span>
          </div>

          <div className="flex items-center justify-between pt-2">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <Badge variant="outline">{SYNC_SCHEDULE_LABELS[job.schedule]}</Badge>
            </div>
            <span className="text-muted-foreground">
              Last: {formatDate(job.last_run_at)}
            </span>
          </div>

          {job.status === 'failed' && job.last_error && (
            <div className="mt-2 p-2 bg-destructive/10 rounded text-destructive text-xs">
              {job.last_error}
            </div>
          )}

          {job.status === 'running' && (
            <div className="flex items-center gap-2 text-yellow-600">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Syncing...</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
export { FileBrowser } from './FileBrowser'
export { LunTable } from './LunTable'
export { LunForm } from './LunForm'
export { SyncJobCard } from './SyncJobCard'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add sync job card component"
```

---

## Task 11: Create SyncJobForm Component

**Files:**
- Create: `frontend/src/components/storage/SyncJobForm.tsx`
- Modify: `frontend/src/components/storage/index.ts`

**Step 1: Create SyncJobForm.tsx**

```typescript
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Checkbox,
} from '@/components/ui'
import { useStorageBackends } from '@/hooks'
import { SYNC_SCHEDULE_LABELS, type SyncJob, type SyncSchedule } from '@/types'

interface SyncJobFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  job?: SyncJob | null
  onSubmit: (data: Partial<SyncJob>) => void
  isPending: boolean
}

const DAYS_OF_WEEK = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function SyncJobForm({ open, onOpenChange, job, onSubmit, isPending }: SyncJobFormProps) {
  const [name, setName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [destinationBackendId, setDestinationBackendId] = useState('')
  const [destinationPath, setDestinationPath] = useState('/')
  const [includePattern, setIncludePattern] = useState('')
  const [excludePattern, setExcludePattern] = useState('')
  const [schedule, setSchedule] = useState<SyncSchedule>('weekly')
  const [scheduleDay, setScheduleDay] = useState(0)
  const [scheduleTime, setScheduleTime] = useState('02:00')
  const [verifyChecksums, setVerifyChecksums] = useState(true)
  const [deleteRemoved, setDeleteRemoved] = useState(true)
  const [keepVersions, setKeepVersions] = useState(0)

  const { data: backendsResponse } = useStorageBackends()
  const backends = backendsResponse?.data ?? []

  const isEditing = !!job

  useEffect(() => {
    if (job) {
      setName(job.name)
      setSourceUrl(job.source_url)
      setDestinationBackendId(job.destination_backend_id)
      setDestinationPath(job.destination_path)
      setIncludePattern(job.include_pattern ?? '')
      setExcludePattern(job.exclude_pattern ?? '')
      setSchedule(job.schedule)
      setScheduleDay(job.schedule_day ?? 0)
      setScheduleTime(job.schedule_time ?? '02:00')
      setVerifyChecksums(job.verify_checksums)
      setDeleteRemoved(job.delete_removed)
      setKeepVersions(job.keep_versions)
    } else {
      setName('')
      setSourceUrl('')
      setDestinationBackendId(backends[0]?.id ?? '')
      setDestinationPath('/')
      setIncludePattern('')
      setExcludePattern('')
      setSchedule('weekly')
      setScheduleDay(0)
      setScheduleTime('02:00')
      setVerifyChecksums(true)
      setDeleteRemoved(true)
      setKeepVersions(0)
    }
  }, [job, open, backends])

  const handleSubmit = () => {
    onSubmit({
      name,
      source_url: sourceUrl,
      destination_backend_id: destinationBackendId,
      destination_path: destinationPath,
      include_pattern: includePattern || undefined,
      exclude_pattern: excludePattern || undefined,
      schedule,
      schedule_day: schedule === 'weekly' || schedule === 'monthly' ? scheduleDay : undefined,
      schedule_time: schedule !== 'manual' ? scheduleTime : undefined,
      verify_checksums: verifyChecksums,
      delete_removed: deleteRemoved,
      keep_versions: keepVersions,
    })
  }

  const isValid = name.trim() !== '' && sourceUrl.trim() !== '' && destinationBackendId !== ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Sync Job' : 'Create Sync Job'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="job-name">Name</Label>
            <Input
              id="job-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Ubuntu ISOs"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-source">Source URL</Label>
            <Input
              id="job-source"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://releases.ubuntu.com/24.04/"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Destination Backend</Label>
              <Select value={destinationBackendId} onValueChange={setDestinationBackendId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {backends.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="job-dest-path">Destination Path</Label>
              <Input
                id="job-dest-path"
                value={destinationPath}
                onChange={(e) => setDestinationPath(e.target.value)}
                placeholder="/isos/ubuntu/"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-include">Include Pattern (optional)</Label>
            <Input
              id="job-include"
              value={includePattern}
              onChange={(e) => setIncludePattern(e.target.value)}
              placeholder="*-live-server-amd64.iso"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-exclude">Exclude Pattern (optional)</Label>
            <Input
              id="job-exclude"
              value={excludePattern}
              onChange={(e) => setExcludePattern(e.target.value)}
              placeholder="*.zsync, *.torrent"
            />
          </div>

          <div className="space-y-2">
            <Label>Schedule</Label>
            <Select value={schedule} onValueChange={(v) => setSchedule(v as SyncSchedule)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SYNC_SCHEDULE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {schedule === 'weekly' && (
            <div className="space-y-2">
              <Label>Day of Week</Label>
              <Select value={scheduleDay.toString()} onValueChange={(v) => setScheduleDay(parseInt(v))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DAYS_OF_WEEK.map((day, i) => (
                    <SelectItem key={i} value={i.toString()}>
                      {day}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {schedule === 'monthly' && (
            <div className="space-y-2">
              <Label htmlFor="job-day">Day of Month</Label>
              <Input
                id="job-day"
                type="number"
                min={1}
                max={31}
                value={scheduleDay}
                onChange={(e) => setScheduleDay(parseInt(e.target.value) || 1)}
              />
            </div>
          )}

          {schedule !== 'manual' && (
            <div className="space-y-2">
              <Label htmlFor="job-time">Time</Label>
              <Input
                id="job-time"
                type="time"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label>Options</Label>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="job-verify"
                  checked={verifyChecksums}
                  onCheckedChange={(checked) => setVerifyChecksums(!!checked)}
                />
                <Label htmlFor="job-verify" className="font-normal">
                  Verify checksums (SHA256)
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="job-delete"
                  checked={deleteRemoved}
                  onCheckedChange={(checked) => setDeleteRemoved(!!checked)}
                />
                <Label htmlFor="job-delete" className="font-normal">
                  Delete removed files
                </Label>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-versions">Keep Previous Versions (0 = disabled)</Label>
            <Input
              id="job-versions"
              type="number"
              min={0}
              max={10}
              value={keepVersions}
              onChange={(e) => setKeepVersions(parseInt(e.target.value) || 0)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || isPending}>
            {isPending ? 'Saving...' : isEditing ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Update storage/index.ts**

```typescript
export { BackendCard } from './BackendCard'
export { BackendForm } from './BackendForm'
export { FileBrowser } from './FileBrowser'
export { LunTable } from './LunTable'
export { LunForm } from './LunForm'
export { SyncJobCard } from './SyncJobCard'
export { SyncJobForm } from './SyncJobForm'
```

**Step 3: Commit**

```bash
git add frontend/src/components/storage/
git commit -m "feat(frontend): add sync job form dialog"
```

---

## Task 12: Create Storage Page

**Files:**
- Create: `frontend/src/pages/Storage.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create Storage.tsx**

```typescript
import { useState } from 'react'
import { Plus, HardDrive, FolderOpen, Database, RefreshCw } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent, Button, Card, CardContent } from '@/components/ui'
import {
  BackendCard,
  BackendForm,
  FileBrowser,
  LunTable,
  LunForm,
  SyncJobCard,
  SyncJobForm,
} from '@/components/storage'
import {
  useStorageBackends,
  useCreateStorageBackend,
  useUpdateStorageBackend,
  useDeleteStorageBackend,
  useTestStorageBackend,
  useCreateLun,
  useUpdateLun,
  useSyncJobs,
  useCreateSyncJob,
  useUpdateSyncJob,
  useDeleteSyncJob,
  useRunSyncJob,
} from '@/hooks'
import type { StorageBackend, IscsiLun, SyncJob } from '@/types'

export function Storage() {
  const [activeTab, setActiveTab] = useState('backends')

  // Backends state
  const [isBackendFormOpen, setIsBackendFormOpen] = useState(false)
  const [editingBackend, setEditingBackend] = useState<StorageBackend | null>(null)

  // LUNs state
  const [isLunFormOpen, setIsLunFormOpen] = useState(false)
  const [editingLun, setEditingLun] = useState<IscsiLun | null>(null)

  // Sync Jobs state
  const [isSyncJobFormOpen, setIsSyncJobFormOpen] = useState(false)
  const [editingSyncJob, setEditingSyncJob] = useState<SyncJob | null>(null)

  // Queries
  const { data: backendsResponse, isLoading: backendsLoading } = useStorageBackends()
  const { data: syncJobsResponse, isLoading: syncJobsLoading } = useSyncJobs()

  // Mutations
  const createBackend = useCreateStorageBackend()
  const updateBackend = useUpdateStorageBackend()
  const deleteBackend = useDeleteStorageBackend()
  const testBackend = useTestStorageBackend()
  const createLun = useCreateLun()
  const updateLun = useUpdateLun()
  const createSyncJob = useCreateSyncJob()
  const updateSyncJob = useUpdateSyncJob()
  const deleteSyncJob = useDeleteSyncJob()
  const runSyncJob = useRunSyncJob()

  const backends = backendsResponse?.data ?? []
  const syncJobs = syncJobsResponse?.data ?? []

  // Backend handlers
  const handleBackendSubmit = (data: Partial<StorageBackend>) => {
    if (editingBackend) {
      updateBackend.mutate(
        { backendId: editingBackend.id, data },
        {
          onSuccess: () => {
            setIsBackendFormOpen(false)
            setEditingBackend(null)
          },
        }
      )
    } else {
      createBackend.mutate(data, {
        onSuccess: () => setIsBackendFormOpen(false),
      })
    }
  }

  const handleBackendDelete = (backend: StorageBackend) => {
    if (confirm(`Delete storage backend "${backend.name}"?`)) {
      deleteBackend.mutate(backend.id)
    }
  }

  const handleBackendTest = async (backend: StorageBackend) => {
    const result = await testBackend.mutateAsync(backend.id)
    alert(result.data?.message ?? 'Test completed')
  }

  // LUN handlers
  const handleLunSubmit = (data: Partial<IscsiLun>) => {
    if (editingLun) {
      updateLun.mutate(
        { lunId: editingLun.id, data },
        {
          onSuccess: () => {
            setIsLunFormOpen(false)
            setEditingLun(null)
          },
        }
      )
    } else {
      createLun.mutate(data, {
        onSuccess: () => setIsLunFormOpen(false),
      })
    }
  }

  // Sync Job handlers
  const handleSyncJobSubmit = (data: Partial<SyncJob>) => {
    if (editingSyncJob) {
      updateSyncJob.mutate(
        { jobId: editingSyncJob.id, data },
        {
          onSuccess: () => {
            setIsSyncJobFormOpen(false)
            setEditingSyncJob(null)
          },
        }
      )
    } else {
      createSyncJob.mutate(data, {
        onSuccess: () => setIsSyncJobFormOpen(false),
      })
    }
  }

  const handleSyncJobDelete = (job: SyncJob) => {
    if (confirm(`Delete sync job "${job.name}"?`)) {
      deleteSyncJob.mutate(job.id)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Storage</h2>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="backends" className="gap-2">
            <HardDrive className="h-4 w-4" />
            Backends
          </TabsTrigger>
          <TabsTrigger value="files" className="gap-2">
            <FolderOpen className="h-4 w-4" />
            Files
          </TabsTrigger>
          <TabsTrigger value="luns" className="gap-2">
            <Database className="h-4 w-4" />
            iSCSI LUNs
          </TabsTrigger>
          <TabsTrigger value="sync" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Sync Jobs
          </TabsTrigger>
        </TabsList>

        {/* Backends Tab */}
        <TabsContent value="backends">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button onClick={() => { setEditingBackend(null); setIsBackendFormOpen(true) }}>
                <Plus className="h-4 w-4 mr-2" />
                Add Backend
              </Button>
            </div>

            {backendsLoading ? (
              <div className="text-muted-foreground">Loading backends...</div>
            ) : backends.length === 0 ? (
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center text-muted-foreground">
                    <HardDrive className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No storage backends configured.</p>
                    <p className="text-sm mt-1">Add a backend to start managing storage.</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {backends.map((backend) => (
                  <BackendCard
                    key={backend.id}
                    backend={backend}
                    onEdit={(b) => { setEditingBackend(b); setIsBackendFormOpen(true) }}
                    onDelete={handleBackendDelete}
                    onTest={handleBackendTest}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Files Tab */}
        <TabsContent value="files">
          <FileBrowser />
        </TabsContent>

        {/* iSCSI LUNs Tab */}
        <TabsContent value="luns">
          <LunTable
            onEdit={(lun) => { setEditingLun(lun); setIsLunFormOpen(true) }}
            onCreate={() => { setEditingLun(null); setIsLunFormOpen(true) }}
          />
        </TabsContent>

        {/* Sync Jobs Tab */}
        <TabsContent value="sync">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button onClick={() => { setEditingSyncJob(null); setIsSyncJobFormOpen(true) }}>
                <Plus className="h-4 w-4 mr-2" />
                Create Job
              </Button>
            </div>

            {syncJobsLoading ? (
              <div className="text-muted-foreground">Loading sync jobs...</div>
            ) : syncJobs.length === 0 ? (
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center text-muted-foreground">
                    <RefreshCw className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No sync jobs configured.</p>
                    <p className="text-sm mt-1">Create a job to sync files from external sources.</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {syncJobs.map((job) => (
                  <SyncJobCard
                    key={job.id}
                    job={job}
                    onEdit={(j) => { setEditingSyncJob(j); setIsSyncJobFormOpen(true) }}
                    onDelete={handleSyncJobDelete}
                    onRun={(j) => runSyncJob.mutate(j.id)}
                    isRunning={runSyncJob.isPending}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <BackendForm
        open={isBackendFormOpen}
        onOpenChange={setIsBackendFormOpen}
        backend={editingBackend}
        onSubmit={handleBackendSubmit}
        isPending={createBackend.isPending || updateBackend.isPending}
      />

      <LunForm
        open={isLunFormOpen}
        onOpenChange={setIsLunFormOpen}
        lun={editingLun}
        onSubmit={handleLunSubmit}
        isPending={createLun.isPending || updateLun.isPending}
      />

      <SyncJobForm
        open={isSyncJobFormOpen}
        onOpenChange={setIsSyncJobFormOpen}
        job={editingSyncJob}
        onSubmit={handleSyncJobSubmit}
        isPending={createSyncJob.isPending || updateSyncJob.isPending}
      />
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
export { Storage } from './Storage'
export { NotFound } from './NotFound'
```

**Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(frontend): add storage page with tabs"
```

---

## Task 13: Update Router

**Files:**
- Modify: `frontend/src/router.tsx`

**Step 1: Update router.tsx**

Replace the placeholder storage route with the actual component:

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Login, Nodes, NodeDetail, Groups, GroupDetail, Storage, NotFound } from '@/pages'
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
      { path: 'storage', element: <Storage /> },
      { path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
      { path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
      { path: 'settings', element: <div>Settings (Coming Soon)</div> },
      { path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
```

**Step 2: Commit**

```bash
git add frontend/src/router.tsx
git commit -m "feat(frontend): add storage route"
```

---

## Task 14: Document Backend API Requirements

**Files:**
- Create: `docs/plans/backend-storage-api.md`

**Step 1: Create backend-storage-api.md**

```markdown
# Backend Storage API Requirements

**Status:** Not Implemented
**Priority:** Required for Phase 4 Frontend
**Created:** 2026-01-20

This document specifies the backend API endpoints required to support the Phase 4 Storage Infrastructure frontend.

---

## 1. Storage Backends API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/backends` | List all storage backends |
| GET | `/api/v1/storage/backends/{id}` | Get backend details |
| POST | `/api/v1/storage/backends` | Create backend |
| PATCH | `/api/v1/storage/backends/{id}` | Update backend |
| DELETE | `/api/v1/storage/backends/{id}` | Delete backend |
| POST | `/api/v1/storage/backends/{id}/test` | Test connection |

### Data Model

```python
class StorageBackend:
    id: str (UUID)
    name: str
    type: Literal['nfs', 'iscsi', 's3', 'http']
    status: Literal['online', 'offline', 'error']
    config: dict  # Type-specific configuration
    stats: {
        used_bytes: int
        total_bytes: int | None
        file_count: int
        template_count: int
    }
    created_at: datetime
    updated_at: datetime
```

### Implementation Notes

- **NFS**: Use subprocess to mount/unmount, check connectivity via stat
- **iSCSI**: Use targetcli or open-iscsi for target management
- **S3**: Use boto3 for S3-compatible storage
- **HTTP**: Simple HTTP HEAD requests for connectivity

---

## 2. File Browser API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/backends/{id}/files?path=/` | List files |
| POST | `/api/v1/storage/backends/{id}/files` | Upload file (multipart) |
| GET | `/api/v1/storage/backends/{id}/files/download?path=` | Download file |
| DELETE | `/api/v1/storage/backends/{id}/files` | Delete files (body: paths[]) |
| POST | `/api/v1/storage/backends/{id}/folders` | Create folder |
| POST | `/api/v1/storage/backends/{id}/files/move` | Move files |

### Data Model

```python
class StorageFile:
    name: str
    path: str
    type: Literal['file', 'directory']
    size: int | None
    mime_type: str | None
    modified_at: datetime
    item_count: int | None  # For directories
```

### Implementation Notes

- NFS: Direct filesystem operations on mounted share
- S3: Use boto3 list_objects_v2, get_object, put_object
- HTTP: Read-only listing via directory index parsing
- iSCSI: Not applicable (block storage, not file)

---

## 3. iSCSI LUN API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/luns` | List all LUNs |
| GET | `/api/v1/storage/luns/{id}` | Get LUN details |
| POST | `/api/v1/storage/luns` | Create LUN |
| PATCH | `/api/v1/storage/luns/{id}` | Update LUN |
| DELETE | `/api/v1/storage/luns/{id}` | Delete LUN |
| POST | `/api/v1/storage/luns/{id}/assign` | Assign to node |
| POST | `/api/v1/storage/luns/{id}/unassign` | Unassign from node |

### Data Model

```python
class IscsiLun:
    id: str (UUID)
    name: str
    size_gb: int
    target_id: str  # Reference to iSCSI backend
    target_name: str
    iqn: str  # Auto-generated IQN
    purpose: Literal['boot_from_san', 'install_source', 'auto_provision']
    status: Literal['active', 'ready', 'error', 'creating', 'deleting']
    assigned_node_id: str | None
    assigned_node_name: str | None
    chap_enabled: bool
    created_at: datetime
    updated_at: datetime
```

### Implementation Notes

- Use targetcli for LUN management
- IQN format: `iqn.2026-01.local.pureboot:{lun_name}`
- CHAP credentials stored in secrets vault
- Background task for LUN creation (can take time)

---

## 4. Sync Jobs API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/sync-jobs` | List sync jobs |
| GET | `/api/v1/storage/sync-jobs/{id}` | Get job details |
| POST | `/api/v1/storage/sync-jobs` | Create job |
| PATCH | `/api/v1/storage/sync-jobs/{id}` | Update job |
| DELETE | `/api/v1/storage/sync-jobs/{id}` | Delete job |
| POST | `/api/v1/storage/sync-jobs/{id}/run` | Trigger manual run |
| GET | `/api/v1/storage/sync-jobs/{id}/history` | Get run history |

### Data Model

```python
class SyncJob:
    id: str (UUID)
    name: str
    source_url: str
    destination_backend_id: str
    destination_backend_name: str
    destination_path: str
    include_pattern: str | None
    exclude_pattern: str | None
    schedule: Literal['manual', 'hourly', 'daily', 'weekly', 'monthly']
    schedule_day: int | None  # 0-6 for weekly, 1-31 for monthly
    schedule_time: str | None  # HH:MM
    verify_checksums: bool
    delete_removed: bool
    keep_versions: int
    status: Literal['idle', 'running', 'synced', 'failed']
    last_run_at: datetime | None
    last_error: str | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

class SyncJobRun:
    id: str (UUID)
    job_id: str
    started_at: datetime
    completed_at: datetime | None
    status: Literal['running', 'success', 'failed']
    files_synced: int
    bytes_transferred: int
    error: str | None
```

### Implementation Notes

- Use rclone or rsync for actual sync operations
- Scheduler integration (APScheduler or Celery Beat)
- WebSocket notifications for real-time status updates
- Keep last N run records per job

---

## Implementation Priority

1. **Storage Backends** - Foundation for all other features
2. **File Browser** - Most commonly used feature
3. **Sync Jobs** - Automated content updates
4. **iSCSI LUNs** - Advanced feature, can be deferred

---

## Security Considerations

- Validate all paths to prevent directory traversal
- Encrypt credentials at rest
- Rate limit upload endpoints
- Validate file types for uploads
- Audit log all operations
```

**Step 2: Commit**

```bash
git add docs/plans/backend-storage-api.md
git commit -m "docs: add backend storage API requirements"
```

---

## Task 15: Final Verification and Push

**Step 1: Verify all files are committed**

```bash
git status
```

**Step 2: Push the feature branch**

```bash
git push -u origin feature/storage
```

---

## Phase 4 Complete

**What was built:**
- Storage types (backends, files, LUNs, sync jobs)
- Storage API client with all endpoints
- React Query hooks for all storage operations
- Tabs component for UI navigation
- Backend card and form components
- File browser with navigation and actions
- LUN table and form components
- Sync job card and form components
- Storage page with tabbed interface
- Router updated with storage route
- Backend API requirements documented

**Backend Tasks Created:**
- `docs/plans/backend-storage-api.md` - Complete API specification for backend implementation

**Next Phase:** Hypervisor Integration (oVirt, Proxmox, VMware, Hyper-V, KVM)
