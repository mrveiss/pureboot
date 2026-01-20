import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, AuthTokens } from '@/types'
import { authApi } from '@/api'
import { apiClient } from '@/api/client'

interface AuthStore {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshTokens: () => Promise<void>
  setTokens: (tokens: AuthTokens) => void
  clearAuth: () => void
  fetchUser: () => Promise<void>
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email: string, password: string) => {
        set({ isLoading: true })
        try {
          const tokens = await authApi.login({ email, password })
          set({
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            isAuthenticated: true,
          })
          await get().fetchUser()
        } finally {
          set({ isLoading: false })
        }
      },

      logout: async () => {
        try {
          await authApi.logout()
        } catch {
          // Ignore errors during logout
        }
        get().clearAuth()
      },

      refreshTokens: async () => {
        const { refreshToken } = get()
        if (!refreshToken) {
          get().clearAuth()
          return
        }
        try {
          const tokens = await authApi.refresh(refreshToken)
          set({
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
          })
        } catch {
          get().clearAuth()
        }
      },

      setTokens: (tokens: AuthTokens) => {
        apiClient.setAccessToken(tokens.access_token)
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          isAuthenticated: true,
        })
      },

      clearAuth: () => {
        apiClient.setAccessToken(null)
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        })
      },

      fetchUser: async () => {
        try {
          const response = await authApi.me()
          set({ user: response.data })
        } catch {
          get().clearAuth()
        }
      },
    }),
    {
      name: 'pureboot-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.accessToken) {
          apiClient.setAccessToken(state.accessToken)
          state.isAuthenticated = true
        }
      },
    }
  )
)
