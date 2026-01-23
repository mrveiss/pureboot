import { apiClient } from './client'
import type {
  Approval,
  ApprovalCreate,
  ApprovalListResponse,
  ApprovalStatsResponse,
  ApprovalApiResponse,
  VoteCreate,
  VoteResult,
} from '../types/approval'

export interface ApprovalFilters {
  status?: string
  requester_name?: string
  limit?: number
  offset?: number
}

export const approvalsApi = {
  getStats: async (): Promise<ApprovalStatsResponse> => {
    return apiClient.get<ApprovalStatsResponse>('/approvals/stats')
  },

  list: async (filters?: ApprovalFilters): Promise<ApprovalListResponse> => {
    const params = new URLSearchParams()
    if (filters?.status) params.append('status', filters.status)
    if (filters?.requester_name) params.append('requester_name', filters.requester_name)
    if (filters?.limit) params.append('limit', filters.limit.toString())
    if (filters?.offset) params.append('offset', filters.offset.toString())

    const query = params.toString()
    const url = query ? `/approvals?${query}` : '/approvals'
    return apiClient.get<ApprovalListResponse>(url)
  },

  getHistory: async (limit = 50, offset = 0): Promise<ApprovalListResponse> => {
    return apiClient.get<ApprovalListResponse>(
      `/approvals/history?limit=${limit}&offset=${offset}`
    )
  },

  get: async (id: string): Promise<Approval> => {
    const response = await apiClient.get<ApprovalApiResponse>(`/approvals/${id}`)
    return response.data!
  },

  create: async (data: ApprovalCreate): Promise<Approval> => {
    const response = await apiClient.post<ApprovalApiResponse>('/approvals', data)
    return response.data!
  },

  approve: async (id: string, data: VoteCreate): Promise<Approval> => {
    const response = await apiClient.post<ApprovalApiResponse>(`/approvals/${id}/approve`, data)
    return response.data!
  },

  reject: async (id: string, data: VoteCreate): Promise<Approval> => {
    const response = await apiClient.post<ApprovalApiResponse>(`/approvals/${id}/reject`, data)
    return response.data!
  },

  cancel: async (id: string, requester_name: string): Promise<Approval> => {
    const response = await apiClient.delete<ApprovalApiResponse>(
      `/approvals/${id}?requester_name=${encodeURIComponent(requester_name)}`
    )
    return response.data!
  },

  vote: async (approvalId: string, data: VoteCreate): Promise<VoteResult> => {
    return apiClient.post<VoteResult>(`/approvals/${approvalId}/vote`, data)
  },

  cancelById: async (approvalId: string): Promise<void> => {
    await apiClient.post(`/approvals/${approvalId}/cancel`)
  },

  listMyPending: async (): Promise<Approval[]> => {
    const response = await apiClient.get<ApprovalListResponse>('/approvals?my_pending=true')
    return response.data
  },
}
