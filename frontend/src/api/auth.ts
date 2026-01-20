import { apiClient } from './client'
import type { ApiResponse, AuthTokens, User, LoginCredentials } from '@/types'

export const authApi = {
  async login(credentials: LoginCredentials): Promise<AuthTokens> {
    const response = await apiClient.post<AuthTokens>('/auth/login', credentials)
    apiClient.setAccessToken(response.access_token)
    return response
  },

  async logout(): Promise<void> {
    await apiClient.post('/auth/logout')
    apiClient.setAccessToken(null)
  },

  async refresh(refreshToken: string): Promise<AuthTokens> {
    const response = await apiClient.post<AuthTokens>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    apiClient.setAccessToken(response.access_token)
    return response
  },

  async me(): Promise<ApiResponse<User>> {
    return apiClient.get<ApiResponse<User>>('/auth/me')
  },
}
