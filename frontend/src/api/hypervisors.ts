import { apiClient } from './client'
import type {
  ApiResponse,
  ApiListResponse,
  Hypervisor,
  HypervisorCreate,
  HypervisorUpdate,
  HypervisorTestResult,
  HypervisorVM,
  HypervisorTemplate,
} from '@/types'

export const hypervisorsApi = {
  async list(): Promise<ApiListResponse<Hypervisor>> {
    return apiClient.get<ApiListResponse<Hypervisor>>('/hypervisors')
  },

  async get(hypervisorId: string): Promise<ApiResponse<Hypervisor>> {
    return apiClient.get<ApiResponse<Hypervisor>>(`/hypervisors/${hypervisorId}`)
  },

  async create(data: HypervisorCreate): Promise<ApiResponse<Hypervisor>> {
    return apiClient.post<ApiResponse<Hypervisor>>('/hypervisors', data)
  },

  async update(hypervisorId: string, data: HypervisorUpdate): Promise<ApiResponse<Hypervisor>> {
    return apiClient.patch<ApiResponse<Hypervisor>>(`/hypervisors/${hypervisorId}`, data)
  },

  async delete(hypervisorId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/hypervisors/${hypervisorId}`)
  },

  async test(hypervisorId: string): Promise<ApiResponse<HypervisorTestResult>> {
    return apiClient.post<ApiResponse<HypervisorTestResult>>(`/hypervisors/${hypervisorId}/test`)
  },

  async listVMs(hypervisorId: string): Promise<ApiListResponse<HypervisorVM>> {
    return apiClient.get<ApiListResponse<HypervisorVM>>(`/hypervisors/${hypervisorId}/vms`)
  },

  async listTemplates(hypervisorId: string): Promise<ApiListResponse<HypervisorTemplate>> {
    return apiClient.get<ApiListResponse<HypervisorTemplate>>(`/hypervisors/${hypervisorId}/templates`)
  },
}
