import { apiClient } from './client'
import type { UserGroup, UserGroupDetail } from '@/types'

export const userGroupsApi = {
  async list(): Promise<UserGroup[]> {
    return apiClient.get<UserGroup[]>('/user-groups')
  },

  async get(id: string): Promise<UserGroupDetail> {
    return apiClient.get<UserGroupDetail>(`/user-groups/${id}`)
  },

  async create(data: {
    name: string
    description?: string
    requires_approval?: boolean
  }): Promise<UserGroup> {
    return apiClient.post<UserGroup>('/user-groups', data)
  },

  async update(
    id: string,
    data: {
      name?: string
      description?: string
      requires_approval?: boolean
    }
  ): Promise<UserGroup> {
    return apiClient.patch<UserGroup>(`/user-groups/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/user-groups/${id}`)
  },

  async assignMembers(id: string, userIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/members`, { user_ids: userIds })
  },

  async assignRoles(id: string, roleIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/roles`, { role_ids: roleIds })
  },

  async assignDeviceGroups(id: string, deviceGroupIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/device-groups`, {
      device_group_ids: deviceGroupIds,
    })
  },

  async assignTags(id: string, tags: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/tags`, { tags })
  },

  async assignNodes(id: string, nodeIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/nodes`, { node_ids: nodeIds })
  },
}
