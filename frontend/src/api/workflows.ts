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
