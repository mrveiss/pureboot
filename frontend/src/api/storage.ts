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
