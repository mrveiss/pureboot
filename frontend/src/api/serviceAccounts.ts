import { apiClient } from './client'
import type { ServiceAccount, ServiceAccountDetail, ApiKeyCreate } from '@/types'

export const serviceAccountsApi = {
  async list(): Promise<ServiceAccount[]> {
    return apiClient.get<ServiceAccount[]>('/service-accounts')
  },

  async get(id: string): Promise<ServiceAccountDetail> {
    return apiClient.get<ServiceAccountDetail>(`/service-accounts/${id}`)
  },

  async create(data: {
    username: string
    description?: string
    role_id?: string
    expires_at?: string
  }): Promise<ServiceAccount> {
    return apiClient.post<ServiceAccount>('/service-accounts', data)
  },

  async update(
    id: string,
    data: {
      description?: string
      role_id?: string
      expires_at?: string
      is_active?: boolean
    }
  ): Promise<ServiceAccount> {
    return apiClient.patch<ServiceAccount>(`/service-accounts/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/service-accounts/${id}`)
  },

  async createApiKey(
    accountId: string,
    data: {
      name: string
      expires_at?: string
    }
  ): Promise<ApiKeyCreate> {
    return apiClient.post<ApiKeyCreate>(`/service-accounts/${accountId}/api-keys`, data)
  },

  async revokeApiKey(accountId: string, keyId: string): Promise<void> {
    await apiClient.delete(`/service-accounts/${accountId}/api-keys/${keyId}`)
  },
}
