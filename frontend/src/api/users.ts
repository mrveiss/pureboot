import { apiClient } from './client'
import type {
  User,
  UserCreate,
  UserUpdate,
  PasswordChange,
  UserListResponse,
  UserApiResponse,
} from '../types/auth'

export interface UserFilters {
  role?: string
  is_active?: boolean
  limit?: number
  offset?: number
}

export const usersApi = {
  list: async (filters?: UserFilters): Promise<UserListResponse> => {
    const params = new URLSearchParams()
    if (filters?.role) params.append('role', filters.role)
    if (filters?.is_active !== undefined) params.append('is_active', String(filters.is_active))
    if (filters?.limit) params.append('limit', filters.limit.toString())
    if (filters?.offset) params.append('offset', filters.offset.toString())

    const query = params.toString()
    const url = query ? `/users?${query}` : '/users'
    return apiClient.get<UserListResponse>(url)
  },

  get: async (id: string): Promise<User> => {
    const response = await apiClient.get<UserApiResponse>(`/users/${id}`)
    return response.data as User
  },

  create: async (data: UserCreate): Promise<User> => {
    const response = await apiClient.post<UserApiResponse>('/users', data)
    return response.data as User
  },

  update: async (id: string, data: UserUpdate): Promise<User> => {
    const response = await apiClient.patch<UserApiResponse>(`/users/${id}`, data)
    return response.data as User
  },

  changePassword: async (id: string, data: PasswordChange): Promise<void> => {
    await apiClient.post<UserApiResponse>(`/users/${id}/password`, data)
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete<UserApiResponse>(`/users/${id}`)
  },
}
