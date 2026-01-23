import { apiClient } from './client'
import type { ApiResponse, ApiListResponse, Template } from '@/types'

export interface TemplateCreate {
  name: string
  type: string
  os_family?: string | null
  os_name?: string | null
  os_version?: string | null
  architecture?: string
  file_path?: string | null
  storage_backend_id?: string | null
  size_bytes?: number | null
  checksum?: string | null
  description?: string | null
}

export interface TemplateUpdate {
  name?: string
  type?: string
  os_family?: string | null
  os_name?: string | null
  os_version?: string | null
  architecture?: string
  file_path?: string | null
  storage_backend_id?: string | null
  size_bytes?: number | null
  checksum?: string | null
  description?: string | null
}

export interface TemplateFilters {
  type?: string
  os_family?: string
  os_name?: string
  architecture?: string
}

export const templatesApi = {
  async list(filters?: TemplateFilters): Promise<ApiListResponse<Template>> {
    const params: Record<string, string> = {}
    if (filters?.type) params.type = filters.type
    if (filters?.os_family) params.os_family = filters.os_family
    if (filters?.os_name) params.os_name = filters.os_name
    if (filters?.architecture) params.architecture = filters.architecture

    return apiClient.get<ApiListResponse<Template>>('/templates', params)
  },

  async get(templateId: string): Promise<ApiResponse<Template>> {
    return apiClient.get<ApiResponse<Template>>(`/templates/${templateId}`)
  },

  async create(data: TemplateCreate): Promise<ApiResponse<Template>> {
    return apiClient.post<ApiResponse<Template>>('/templates', data)
  },

  async update(templateId: string, data: TemplateUpdate): Promise<ApiResponse<Template>> {
    return apiClient.patch<ApiResponse<Template>>(`/templates/${templateId}`, data)
  },

  async delete(templateId: string): Promise<ApiResponse<Template>> {
    return apiClient.delete<ApiResponse<Template>>(`/templates/${templateId}`)
  },
}
