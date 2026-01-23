import { apiClient } from './client'
import type { ApprovalRule, ApprovalRuleCreate, ApprovalRuleUpdate } from '@/types'

export const approvalRulesApi = {
  async list(): Promise<ApprovalRule[]> {
    return apiClient.get<ApprovalRule[]>('/approval-rules')
  },

  async get(id: string): Promise<ApprovalRule> {
    return apiClient.get<ApprovalRule>(`/approval-rules/${id}`)
  },

  async create(data: ApprovalRuleCreate): Promise<ApprovalRule> {
    return apiClient.post<ApprovalRule>('/approval-rules', data)
  },

  async update(id: string, data: ApprovalRuleUpdate): Promise<ApprovalRule> {
    return apiClient.patch<ApprovalRule>(`/approval-rules/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/approval-rules/${id}`)
  },
}
