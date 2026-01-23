import { apiClient } from './client'
import type { AuditLogListResponse, AuditFilters } from '@/types'

export const auditApi = {
  async list(
    page: number = 1,
    pageSize: number = 50,
    filters?: AuditFilters
  ): Promise<AuditLogListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })

    if (filters?.action) params.set('action', filters.action)
    if (filters?.resource_type) params.set('resource_type', filters.resource_type)
    if (filters?.actor_username) params.set('actor_username', filters.actor_username)
    if (filters?.result) params.set('result', filters.result)
    if (filters?.from_date) params.set('from_date', filters.from_date)
    if (filters?.to_date) params.set('to_date', filters.to_date)

    return apiClient.get<AuditLogListResponse>(`/audit?${params}`)
  },

  async getActions(): Promise<{ actions: string[] }> {
    return apiClient.get('/audit/actions')
  },

  async getResourceTypes(): Promise<{ resource_types: string[] }> {
    return apiClient.get('/audit/resource-types')
  },
}
