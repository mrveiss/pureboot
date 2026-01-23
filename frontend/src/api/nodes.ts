import { apiClient } from './client'
import type {
  ApiResponse,
  ApiListResponse,
  Node,
  DeviceGroup,
  NodeFilterParams,
  NodeStats
} from '@/types'

export const nodesApi = {
  async stats(): Promise<ApiResponse<NodeStats>> {
    return apiClient.get<ApiResponse<NodeStats>>('/nodes/stats')
  },

  async list(params?: NodeFilterParams): Promise<ApiListResponse<Node>> {
    const queryParams: Record<string, string> = {}
    if (params?.state) queryParams.state = params.state
    if (params?.group_id) queryParams.group_id = params.group_id
    if (params?.tag) queryParams.tag = params.tag
    if (params?.search) queryParams.search = params.search
    if (params?.page) queryParams.page = String(params.page)
    if (params?.limit) queryParams.limit = String(params.limit)

    return apiClient.get<ApiListResponse<Node>>('/nodes', queryParams)
  },

  async get(nodeId: string): Promise<ApiResponse<Node>> {
    return apiClient.get<ApiResponse<Node>>(`/nodes/${nodeId}`)
  },

  async create(data: Partial<Node>): Promise<ApiResponse<Node>> {
    return apiClient.post<ApiResponse<Node>>('/nodes', data)
  },

  async update(nodeId: string, data: Partial<Node>): Promise<ApiResponse<Node>> {
    return apiClient.patch<ApiResponse<Node>>(`/nodes/${nodeId}`, data)
  },

  async updateState(nodeId: string, newState: string): Promise<ApiResponse<Node>> {
    return apiClient.patch<ApiResponse<Node>>(`/nodes/${nodeId}/state`, {
      new_state: newState
    })
  },

  async delete(nodeId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/nodes/${nodeId}`)
  },

  async addTag(nodeId: string, tag: string): Promise<ApiResponse<Node>> {
    return apiClient.post<ApiResponse<Node>>(`/nodes/${nodeId}/tags`, { tag })
  },

  async removeTag(nodeId: string, tag: string): Promise<ApiResponse<Node>> {
    return apiClient.delete<ApiResponse<Node>>(`/nodes/${nodeId}/tags/${tag}`)
  },

  async bulkAssignGroup(nodeIds: string[], groupId: string | null): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-group', {
      node_ids: nodeIds,
      group_id: groupId,
    })
  },

  async bulkAssignWorkflow(nodeIds: string[], workflowId: string | null): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/assign-workflow', {
      node_ids: nodeIds,
      workflow_id: workflowId,
    })
  },

  async bulkAddTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/add-tag', {
      node_ids: nodeIds,
      tag,
    })
  },

  async bulkRemoveTag(nodeIds: string[], tag: string): Promise<ApiResponse<{ updated: number }>> {
    return apiClient.post<ApiResponse<{ updated: number }>>('/nodes/bulk/remove-tag', {
      node_ids: nodeIds,
      tag,
    })
  },

  async bulkChangeState(nodeIds: string[], newState: string): Promise<ApiResponse<{ updated: number; failed: number }>> {
    return apiClient.post<ApiResponse<{ updated: number; failed: number }>>('/nodes/bulk/change-state', {
      node_ids: nodeIds,
      new_state: newState,
    })
  },
}

export const groupsApi = {
  async list(): Promise<ApiListResponse<DeviceGroup>> {
    return apiClient.get<ApiListResponse<DeviceGroup>>('/groups')
  },

  async get(groupId: string): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.get<ApiResponse<DeviceGroup>>(`/groups/${groupId}`)
  },

  async create(data: Partial<DeviceGroup>): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.post<ApiResponse<DeviceGroup>>('/groups', data)
  },

  async update(groupId: string, data: Partial<DeviceGroup>): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.patch<ApiResponse<DeviceGroup>>(`/groups/${groupId}`, data)
  },

  async delete(groupId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/groups/${groupId}`)
  },

  async getNodes(groupId: string): Promise<ApiListResponse<Node>> {
    return apiClient.get<ApiListResponse<Node>>(`/groups/${groupId}/nodes`)
  },
}
