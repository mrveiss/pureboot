import { apiClient } from './client'
import type {
  ApiResponse,
  ApiListResponse,
} from '@/types'
import type {
  Site,
  SiteCreate,
  SiteUpdate,
  SiteHealth,
  SiteSyncResponse,
  AgentTokenResponse,
  SiteConflict,
} from '@/types/site'
import type { Node } from '@/types'

export const sitesApi = {
  async list(parentId?: string): Promise<ApiListResponse<Site>> {
    const params: Record<string, string> = {}
    if (parentId) params.parent_id = parentId
    return apiClient.get<ApiListResponse<Site>>('/sites', params)
  },

  async get(siteId: string): Promise<ApiResponse<Site>> {
    return apiClient.get<ApiResponse<Site>>(`/sites/${siteId}`)
  },

  async create(data: SiteCreate): Promise<ApiResponse<Site>> {
    return apiClient.post<ApiResponse<Site>>('/sites', data)
  },

  async update(siteId: string, data: SiteUpdate): Promise<ApiResponse<Site>> {
    return apiClient.patch<ApiResponse<Site>>(`/sites/${siteId}`, data)
  },

  async delete(siteId: string): Promise<ApiResponse<{ id: string }>> {
    return apiClient.delete<ApiResponse<{ id: string }>>(`/sites/${siteId}`)
  },

  async listNodes(siteId: string, includeDescendants?: boolean): Promise<ApiListResponse<Node>> {
    const params: Record<string, string> = {}
    if (includeDescendants) params.include_descendant_sites = 'true'
    return apiClient.get<ApiListResponse<Node>>(`/sites/${siteId}/nodes`, params)
  },

  async getHealth(siteId: string): Promise<ApiResponse<SiteHealth>> {
    return apiClient.get<ApiResponse<SiteHealth>>(`/sites/${siteId}/health`)
  },

  async triggerSync(siteId: string, fullSync?: boolean): Promise<ApiResponse<SiteSyncResponse>> {
    return apiClient.post<ApiResponse<SiteSyncResponse>>(`/sites/${siteId}/sync`, {
      full_sync: fullSync ?? false,
    })
  },

  async generateAgentToken(siteId: string): Promise<ApiResponse<AgentTokenResponse>> {
    return apiClient.post<ApiResponse<AgentTokenResponse>>(`/sites/${siteId}/agent-token`)
  },

  async listConflicts(siteId: string): Promise<ApiListResponse<SiteConflict>> {
    return apiClient.get<ApiListResponse<SiteConflict>>(`/sites/${siteId}/conflicts`)
  },

  async resolveConflict(
    siteId: string,
    conflictId: string,
    resolution: string,
  ): Promise<ApiResponse<SiteConflict>> {
    return apiClient.post<ApiResponse<SiteConflict>>(
      `/sites/${siteId}/conflicts/${conflictId}/resolve`,
      { resolution },
    )
  },

  async resolveAllConflicts(
    siteId: string,
    resolution: string,
  ): Promise<ApiResponse<{ resolved: number }>> {
    return apiClient.post<ApiResponse<{ resolved: number }>>(
      `/sites/${siteId}/conflicts/resolve-all`,
      { resolution },
    )
  },
}
