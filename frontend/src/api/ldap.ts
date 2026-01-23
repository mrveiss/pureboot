import { apiClient } from './client'
import type { LdapConfig, LdapConfigCreate, LdapConfigUpdate, LdapTestResult } from '@/types'

export const ldapApi = {
  async list(): Promise<LdapConfig[]> {
    return apiClient.get<LdapConfig[]>('/ldap-configs')
  },

  async get(id: string): Promise<LdapConfig> {
    return apiClient.get<LdapConfig>(`/ldap-configs/${id}`)
  },

  async create(data: LdapConfigCreate): Promise<LdapConfig> {
    return apiClient.post<LdapConfig>('/ldap-configs', data)
  },

  async update(id: string, data: LdapConfigUpdate): Promise<LdapConfig> {
    return apiClient.patch<LdapConfig>(`/ldap-configs/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/ldap-configs/${id}`)
  },

  async test(id: string): Promise<LdapTestResult> {
    return apiClient.post<LdapTestResult>(`/ldap-configs/${id}/test`)
  },
}
