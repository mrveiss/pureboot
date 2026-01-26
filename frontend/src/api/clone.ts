import { apiClient } from './client'
import type { ApiResponse, ApiListResponse } from '@/types'
import type { CloneSession, CloneSessionCreate, CloneSessionUpdate } from '@/types/clone'

export interface CloneSessionListParams {
  status?: string
  limit?: number
  offset?: number
}

export interface SourceReadyData {
  ip: string
  port: number
  size_bytes: number
  device: string
}

export interface ProgressData {
  role: 'source' | 'target'
  bytes_transferred: number
  transfer_rate_bps?: number
}

export const cloneApi = {
  async list(params?: CloneSessionListParams): Promise<ApiListResponse<CloneSession>> {
    const queryParams: Record<string, string> = {}
    if (params?.status) queryParams.status = params.status
    if (params?.limit) queryParams.limit = String(params.limit)
    if (params?.offset) queryParams.offset = String(params.offset)

    return apiClient.get<ApiListResponse<CloneSession>>('/clone-sessions', queryParams)
  },

  async get(sessionId: string): Promise<ApiResponse<CloneSession>> {
    return apiClient.get<ApiResponse<CloneSession>>(`/clone-sessions/${sessionId}`)
  },

  async create(data: CloneSessionCreate): Promise<ApiResponse<CloneSession>> {
    return apiClient.post<ApiResponse<CloneSession>>('/clone-sessions', data)
  },

  async update(sessionId: string, data: CloneSessionUpdate): Promise<ApiResponse<CloneSession>> {
    return apiClient.patch<ApiResponse<CloneSession>>(`/clone-sessions/${sessionId}`, data)
  },

  async delete(sessionId: string): Promise<ApiResponse<{ id: string }>> {
    return apiClient.delete<ApiResponse<{ id: string }>>(`/clone-sessions/${sessionId}`)
  },

  // Callbacks (usually called by nodes, but available for testing)
  async sourceReady(sessionId: string, data: SourceReadyData): Promise<ApiResponse<{ status: string }>> {
    return apiClient.post<ApiResponse<{ status: string }>>(`/clone-sessions/${sessionId}/source-ready`, data)
  },

  async progress(sessionId: string, data: ProgressData): Promise<ApiResponse<{ progress_percent: number }>> {
    return apiClient.post<ApiResponse<{ progress_percent: number }>>(`/clone-sessions/${sessionId}/progress`, data)
  },

  async complete(sessionId: string): Promise<ApiResponse<{ status: string; duration_seconds: number }>> {
    return apiClient.post<ApiResponse<{ status: string; duration_seconds: number }>>(`/clone-sessions/${sessionId}/complete`, {})
  },

  async failed(sessionId: string, error: string): Promise<ApiResponse<{ status: string }>> {
    return apiClient.post<ApiResponse<{ status: string }>>(`/clone-sessions/${sessionId}/failed?error=${encodeURIComponent(error)}`, {})
  },

  // Resize plan endpoints
  async analyze(sessionId: string): Promise<ApiResponse<CloneAnalysisResponse>> {
    return apiClient.post<ApiResponse<CloneAnalysisResponse>>(`/clone-sessions/${sessionId}/analyze`, {})
  },

  async getResizePlan(sessionId: string): Promise<ApiResponse<ResizePlan | null>> {
    return apiClient.get<ApiResponse<ResizePlan | null>>(`/clone-sessions/${sessionId}/plan`)
  },

  async updateResizePlan(sessionId: string, plan: ResizePlan): Promise<ApiResponse<ResizePlan>> {
    return apiClient.put<ApiResponse<ResizePlan>>(`/clone-sessions/${sessionId}/plan`, plan)
  },
}

// ============== Resize Plan Types ==============

export interface PartitionPlanItem {
  partition: number
  current_size_bytes: number
  new_size_bytes: number
  filesystem: string | null
  action: 'keep' | 'shrink' | 'grow' | 'delete'
  min_size_bytes: number | null
  can_resize: boolean
}

export interface ResizePlan {
  source_disk_bytes: number
  target_disk_bytes: number
  resize_mode: 'none' | 'shrink_source' | 'grow_target'
  partitions: PartitionPlanItem[]
  feasible: boolean
  error_message: string | null
}

export interface CloneAnalysisResponse {
  source_disk: Record<string, unknown> | null
  target_disk: Record<string, unknown> | null
  size_difference_bytes: number
  resize_needed: boolean
  suggested_plan: ResizePlan | null
}
