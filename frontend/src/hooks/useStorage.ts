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
