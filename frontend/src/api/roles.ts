import { apiClient } from './client'
import type { Role, RoleDetail, Permission } from '@/types'

export const rolesApi = {
  async list(): Promise<Role[]> {
    return apiClient.get<Role[]>('/roles')
  },

  async listPermissions(): Promise<Permission[]> {
    return apiClient.get<Permission[]>('/roles/permissions')
  },

  async get(id: string): Promise<RoleDetail> {
    return apiClient.get<RoleDetail>(`/roles/${id}`)
  },

  async create(data: {
    name: string
    description?: string
    permission_ids?: string[]
  }): Promise<RoleDetail> {
    return apiClient.post<RoleDetail>('/roles', data)
  },

  async update(
    id: string,
    data: {
      name?: string
      description?: string
      permission_ids?: string[]
    }
  ): Promise<RoleDetail> {
    return apiClient.patch<RoleDetail>(`/roles/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/roles/${id}`)
  },
}
