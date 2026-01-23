import { apiClient } from './client'
import type { AuthTokens, User, LoginCredentials, UserApiResponse } from '@/types'

// Response wrapper from backend
interface AuthResponse {
  success: boolean
  message?: string
  data?: AuthTokens | User
}

export const authApi = {
  async login(credentials: LoginCredentials): Promise<AuthTokens> {
    const response = await apiClient.post<AuthResponse>('/auth/login', credentials)
    const tokens = response.data as AuthTokens
    apiClient.setAccessToken(tokens.access_token)
    return tokens
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout')
    } finally {
      apiClient.setAccessToken(null)
    }
  },

  async refresh(): Promise<AuthTokens> {
    // Refresh token is sent via httpOnly cookie automatically
    const response = await apiClient.post<AuthResponse>('/auth/refresh')
    const tokens = response.data as AuthTokens
    apiClient.setAccessToken(tokens.access_token)
    return tokens
  },

  async me(): Promise<User> {
    const response = await apiClient.get<AuthResponse>('/auth/me')
    return response.data as User
  },
}
