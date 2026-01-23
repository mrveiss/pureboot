import { apiClient } from './client'
import type { ApiListResponse, ActivityEntry, ActivityFilters } from '@/types'

export const activityApi = {
  async list(filters?: ActivityFilters): Promise<ApiListResponse<ActivityEntry>> {
    const params: Record<string, string> = {}
    if (filters?.type) params.type = filters.type
    if (filters?.node_id) params.node_id = filters.node_id
    if (filters?.event_type) params.event_type = filters.event_type
    if (filters?.since) params.since = filters.since
    if (filters?.limit) params.limit = String(filters.limit)
    if (filters?.offset) params.offset = String(filters.offset)

    return apiClient.get<ApiListResponse<ActivityEntry>>('/activity', params)
  },
}
