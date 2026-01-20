# Web UI Phase 1: Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up the React frontend foundation with project structure, layout shell, authentication, API client, and WebSocket connection.

**Architecture:** Vite-based React 18 app with TypeScript. shadcn/ui components with Tailwind CSS for styling. TanStack Query for server state, Zustand for client state. JWT authentication with refresh tokens. Native WebSocket for real-time updates.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query, Zustand, React Router v6

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-web-ui/frontend`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run npm install, npm run dev, or any other commands that execute the application. Only create/edit files.

---

## Task 1: Initialize Vite React TypeScript Project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/.eslintrc.cjs`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.js`

**Step 1: Create package.json**

```json
{
  "name": "pureboot-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui"
  },
  "dependencies": {
    "@radix-ui/react-avatar": "^1.0.4",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "@radix-ui/react-label": "^2.0.2",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-separator": "^1.0.3",
    "@radix-ui/react-slot": "^1.0.2",
    "@radix-ui/react-toast": "^1.1.5",
    "@radix-ui/react-tooltip": "^1.0.7",
    "@tanstack/react-query": "^5.17.0",
    "@tanstack/react-query-devtools": "^5.17.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "lucide-react": "^0.309.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "tailwind-merge": "^2.2.0",
    "tailwindcss-animate": "^1.0.7",
    "zustand": "^4.4.7"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.2.0",
    "@testing-library/react": "^14.1.2",
    "@types/node": "^20.10.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.16",
    "eslint": "^8.56.0",
    "eslint-plugin-react-hooks": "^4.6.0",
    "eslint-plugin-react-refresh": "^0.4.5",
    "jsdom": "^23.2.0",
    "postcss": "^8.4.32",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vitest": "^1.2.0"
  }
}
```

**Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

**Step 3: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

**Step 4: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

**Step 5: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/png" href="/pureboot-logo.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PureBoot</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 6: Create .eslintrc.cjs**

```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
}
```

**Step 7: Create postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

**Step 8: Create tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
```

**Step 9: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): initialize vite react typescript project"
```

---

## Task 2: Create Base Styles and Utility Functions

**Files:**
- Create: `frontend/src/index.css`
- Create: `frontend/src/lib/utils.ts`

**Step 1: Create index.css with Tailwind and CSS variables**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 221.2 83.2% 53.3%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
    --primary: 217.2 91.2% 59.8%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 224.3 76.3% 48%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

**Step 2: Create utils.ts**

```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add base styles and utility functions"
```

---

## Task 3: Create TypeScript Types

**Files:**
- Create: `frontend/src/types/node.ts`
- Create: `frontend/src/types/auth.ts`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/types/index.ts`

**Step 1: Create node.ts**

```typescript
export type NodeState =
  | 'discovered'
  | 'ignored'
  | 'pending'
  | 'installing'
  | 'installed'
  | 'active'
  | 'reprovision'
  | 'migrating'
  | 'retired'
  | 'decommissioned'
  | 'wiping'

export type Architecture = 'x86_64' | 'arm64'
export type BootMode = 'bios' | 'uefi'

export interface Node {
  id: string
  mac_address: string
  hostname: string | null
  ip_address: string | null
  state: NodeState
  workflow_id: string | null
  vendor: string | null
  model: string | null
  serial_number: string | null
  system_uuid: string | null
  arch: Architecture
  boot_mode: BootMode
  group_id: string | null
  tags: string[]
  created_at: string
  updated_at: string
  last_seen_at: string | null
}

export interface DeviceGroup {
  id: string
  name: string
  description: string | null
  default_workflow_id: string | null
  auto_provision: boolean
  created_at: string
  updated_at: string
  node_count: number
}

export const NODE_STATE_COLORS: Record<NodeState, string> = {
  discovered: 'bg-blue-500',
  ignored: 'bg-gray-500',
  pending: 'bg-yellow-500',
  installing: 'bg-orange-500',
  installed: 'bg-teal-500',
  active: 'bg-green-500',
  reprovision: 'bg-purple-500',
  migrating: 'bg-indigo-500',
  retired: 'bg-gray-600',
  decommissioned: 'bg-gray-700',
  wiping: 'bg-red-500',
}

export const NODE_STATE_LABELS: Record<NodeState, string> = {
  discovered: 'Discovered',
  ignored: 'Ignored',
  pending: 'Pending',
  installing: 'Installing',
  installed: 'Installed',
  active: 'Active',
  reprovision: 'Reprovision',
  migrating: 'Migrating',
  retired: 'Retired',
  decommissioned: 'Decommissioned',
  wiping: 'Wiping',
}
```

**Step 2: Create auth.ts**

```typescript
export type UserRole = 'super_admin' | 'admin' | 'operator' | 'viewer'

export interface User {
  id: string
  email: string
  name: string
  role: UserRole
  status: 'active' | 'disabled'
  created_at: string
  updated_at: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
}
```

**Step 3: Create api.ts**

```typescript
export interface ApiResponse<T> {
  success: boolean
  data: T
  message?: string
}

export interface ApiListResponse<T> {
  success: boolean
  data: T[]
  total: number
}

export interface ApiError {
  success: false
  error: string
  detail: string
}

export interface PaginationParams {
  page?: number
  limit?: number
}

export interface NodeFilterParams extends PaginationParams {
  state?: string
  group_id?: string
  tag?: string
  search?: string
}
```

**Step 4: Create index.ts**

```typescript
export * from './node'
export * from './auth'
export * from './api'
```

**Step 5: Commit**

```bash
git add frontend/src/types/
git commit -m "feat(frontend): add TypeScript type definitions"
```

---

## Task 4: Create API Client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/api/nodes.ts`
- Create: `frontend/src/api/index.ts`

**Step 1: Create client.ts**

```typescript
import type { ApiError } from '@/types'

const API_BASE = '/api/v1'

class ApiClient {
  private accessToken: string | null = null

  setAccessToken(token: string | null) {
    this.accessToken = token
  }

  getAccessToken(): string | null {
    return this.accessToken
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({
        success: false,
        error: 'Network Error',
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }))
      throw new Error(error.detail || error.error)
    }

    return response.json()
  }

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    const url = params
      ? `${endpoint}?${new URLSearchParams(params)}`
      : endpoint
    return this.request<T>(url, { method: 'GET' })
  }

  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async patch<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }
}

export const apiClient = new ApiClient()
```

**Step 2: Create auth.ts**

```typescript
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
```

**Step 3: Create nodes.ts**

```typescript
import { apiClient } from './client'
import type {
  ApiResponse,
  ApiListResponse,
  Node,
  DeviceGroup,
  NodeFilterParams
} from '@/types'

export const nodesApi = {
  async list(params?: NodeFilterParams): Promise<ApiListResponse<Node>> {
    const queryParams: Record<string, string> = {}
    if (params?.state) queryParams.state = params.state
    if (params?.group_id) queryParams.group_id = params.group_id
    if (params?.tag) queryParams.tag = params.tag
    if (params?.search) queryParams.search = params.search
    if (params?.page) queryParams.page = String(params.page)
    if (params?.limit) queryParams.limit = String(params.limit)

    return apiClient.get<ApiListResponse<Node>>('/nodes', queryParams)
  },

  async get(nodeId: string): Promise<ApiResponse<Node>> {
    return apiClient.get<ApiResponse<Node>>(`/nodes/${nodeId}`)
  },

  async create(data: Partial<Node>): Promise<ApiResponse<Node>> {
    return apiClient.post<ApiResponse<Node>>('/nodes', data)
  },

  async update(nodeId: string, data: Partial<Node>): Promise<ApiResponse<Node>> {
    return apiClient.patch<ApiResponse<Node>>(`/nodes/${nodeId}`, data)
  },

  async updateState(nodeId: string, newState: string): Promise<ApiResponse<Node>> {
    return apiClient.patch<ApiResponse<Node>>(`/nodes/${nodeId}/state`, {
      new_state: newState
    })
  },

  async delete(nodeId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/nodes/${nodeId}`)
  },

  async addTag(nodeId: string, tag: string): Promise<ApiResponse<Node>> {
    return apiClient.post<ApiResponse<Node>>(`/nodes/${nodeId}/tags`, { tag })
  },

  async removeTag(nodeId: string, tag: string): Promise<ApiResponse<Node>> {
    return apiClient.delete<ApiResponse<Node>>(`/nodes/${nodeId}/tags/${tag}`)
  },
}

export const groupsApi = {
  async list(): Promise<ApiListResponse<DeviceGroup>> {
    return apiClient.get<ApiListResponse<DeviceGroup>>('/groups')
  },

  async get(groupId: string): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.get<ApiResponse<DeviceGroup>>(`/groups/${groupId}`)
  },

  async create(data: Partial<DeviceGroup>): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.post<ApiResponse<DeviceGroup>>('/groups', data)
  },

  async update(groupId: string, data: Partial<DeviceGroup>): Promise<ApiResponse<DeviceGroup>> {
    return apiClient.patch<ApiResponse<DeviceGroup>>(`/groups/${groupId}`, data)
  },

  async delete(groupId: string): Promise<ApiResponse<null>> {
    return apiClient.delete<ApiResponse<null>>(`/groups/${groupId}`)
  },

  async getNodes(groupId: string): Promise<ApiListResponse<Node>> {
    return apiClient.get<ApiListResponse<Node>>(`/groups/${groupId}/nodes`)
  },
}
```

**Step 4: Create index.ts**

```typescript
export { apiClient } from './client'
export { authApi } from './auth'
export { nodesApi, groupsApi } from './nodes'
```

**Step 5: Commit**

```bash
git add frontend/src/api/
git commit -m "feat(frontend): add API client with auth and nodes endpoints"
```

---

## Task 5: Create Zustand Stores

**Files:**
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/stores/theme.ts`
- Create: `frontend/src/stores/index.ts`

**Step 1: Create auth.ts**

```typescript
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
```

**Step 2: Create theme.ts**

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface ThemeStore {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: 'light' | 'dark'
}

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  const resolved = theme === 'system' ? getSystemTheme() : theme
  document.documentElement.classList.remove('light', 'dark')
  document.documentElement.classList.add(resolved)
  return resolved
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set, get) => ({
      theme: 'system',
      resolvedTheme: getSystemTheme(),

      setTheme: (theme: Theme) => {
        const resolved = applyTheme(theme)
        set({ theme, resolvedTheme: resolved })
      },
    }),
    {
      name: 'pureboot-theme',
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = applyTheme(state.theme)
          state.resolvedTheme = resolved
        }
      },
    }
  )
)

// Listen for system theme changes
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const { theme, setTheme } = useThemeStore.getState()
    if (theme === 'system') {
      setTheme('system')
    }
  })
}
```

**Step 3: Create index.ts**

```typescript
export { useAuthStore } from './auth'
export { useThemeStore } from './theme'
```

**Step 4: Commit**

```bash
git add frontend/src/stores/
git commit -m "feat(frontend): add Zustand stores for auth and theme"
```

---

## Task 6: Create Base UI Components (shadcn/ui style)

**Files:**
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/input.tsx`
- Create: `frontend/src/components/ui/label.tsx`
- Create: `frontend/src/components/ui/card.tsx`
- Create: `frontend/src/components/ui/badge.tsx`
- Create: `frontend/src/components/ui/separator.tsx`
- Create: `frontend/src/components/ui/index.ts`

**Step 1: Create button.tsx**

```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

**Step 2: Create input.tsx**

```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
```

**Step 3: Create label.tsx**

```typescript
import * as React from "react"
import * as LabelPrimitive from "@radix-ui/react-label"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
)

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
))
Label.displayName = LabelPrimitive.Root.displayName

export { Label }
```

**Step 4: Create card.tsx**

```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border bg-card text-card-foreground shadow-sm",
      className
    )}
    {...props}
  />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6", className)}
    {...props}
  />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      "text-2xl font-semibold leading-none tracking-tight",
      className
    )}
    {...props}
  />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center p-6 pt-0", className)}
    {...props}
  />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
```

**Step 5: Create badge.tsx**

```typescript
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
```

**Step 6: Create separator.tsx**

```typescript
import * as React from "react"
import * as SeparatorPrimitive from "@radix-ui/react-separator"
import { cn } from "@/lib/utils"

const Separator = React.forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(
  (
    { className, orientation = "horizontal", decorative = true, ...props },
    ref
  ) => (
    <SeparatorPrimitive.Root
      ref={ref}
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
        className
      )}
      {...props}
    />
  )
)
Separator.displayName = SeparatorPrimitive.Root.displayName

export { Separator }
```

**Step 7: Create index.ts**

```typescript
export { Button, buttonVariants } from './button'
export { Input } from './input'
export { Label } from './label'
export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent } from './card'
export { Badge, badgeVariants } from './badge'
export { Separator } from './separator'
```

**Step 8: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(frontend): add base shadcn/ui components"
```

---

## Task 7: Create Layout Components

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/index.ts`

**Step 1: Create Sidebar.tsx**

```typescript
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui'
import {
  LayoutDashboard,
  Server,
  Folders,
  Workflow,
  FileCode,
  HardDrive,
  Cloud,
  ClipboardCheck,
  Activity,
  Settings,
  Users,
} from 'lucide-react'

interface NavItemProps {
  to: string
  icon: React.ReactNode
  label: string
  badge?: number
}

function NavItem({ to, icon, label, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {icon}
      <span className="flex-1">{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
          {badge}
        </span>
      )}
    </NavLink>
  )
}

interface SidebarProps {
  pendingApprovals?: number
}

export function Sidebar({ pendingApprovals = 0 }: SidebarProps) {
  return (
    <aside className="flex h-full w-64 flex-col border-r bg-card">
      <div className="flex h-16 items-center gap-2 border-b px-4">
        <img src="/pureboot-logo.png" alt="PureBoot" className="h-8 w-8" />
        <span className="text-lg font-semibold">PureBoot</span>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        <NavItem to="/" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
        <NavItem to="/nodes" icon={<Server className="h-4 w-4" />} label="Nodes" />
        <NavItem to="/groups" icon={<Folders className="h-4 w-4" />} label="Device Groups" />
        <NavItem to="/workflows" icon={<Workflow className="h-4 w-4" />} label="Workflows" />
        <NavItem to="/templates" icon={<FileCode className="h-4 w-4" />} label="Templates" />
        <NavItem to="/hypervisors" icon={<Cloud className="h-4 w-4" />} label="Hypervisors" />
        <NavItem to="/storage" icon={<HardDrive className="h-4 w-4" />} label="Storage" />

        <Separator className="my-4" />

        <NavItem
          to="/approvals"
          icon={<ClipboardCheck className="h-4 w-4" />}
          label="Approvals"
          badge={pendingApprovals}
        />
        <NavItem to="/activity" icon={<Activity className="h-4 w-4" />} label="Activity Log" />

        <Separator className="my-4" />

        <NavItem to="/settings" icon={<Settings className="h-4 w-4" />} label="Settings" />
        <NavItem to="/users" icon={<Users className="h-4 w-4" />} label="Users & Roles" />
      </nav>
    </aside>
  )
}
```

**Step 2: Create Header.tsx**

```typescript
import { Bell, Moon, Sun, LogOut, User } from 'lucide-react'
import { Button } from '@/components/ui'
import { useAuthStore, useThemeStore } from '@/stores'

interface HeaderProps {
  notificationCount?: number
}

export function Header({ notificationCount = 0 }: HeaderProps) {
  const { user, logout } = useAuthStore()
  const { theme, setTheme, resolvedTheme } = useThemeStore()

  const toggleTheme = () => {
    if (theme === 'system') {
      setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
    } else {
      setTheme(theme === 'dark' ? 'light' : 'dark')
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">Node Lifecycle Management</h1>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
          <Bell className="h-5 w-5" />
          {notificationCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs text-destructive-foreground">
              {notificationCount > 99 ? '99+' : notificationCount}
            </span>
          )}
        </Button>

        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {resolvedTheme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        <div className="ml-2 flex items-center gap-2 border-l pl-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <User className="h-4 w-4" />
          </div>
          <div className="hidden flex-col sm:flex">
            <span className="text-sm font-medium">{user?.name || 'User'}</span>
            <span className="text-xs text-muted-foreground">{user?.role || 'Unknown'}</span>
          </div>
          <Button variant="ghost" size="icon" onClick={() => logout()} aria-label="Logout">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
```

**Step 3: Create AppShell.tsx**

```typescript
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar pendingApprovals={3} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header notificationCount={5} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

**Step 4: Create index.ts**

```typescript
export { Sidebar } from './Sidebar'
export { Header } from './Header'
export { AppShell } from './AppShell'
```

**Step 5: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "feat(frontend): add layout components (sidebar, header, shell)"
```

---

## Task 8: Create WebSocket Hook

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/hooks/index.ts`

**Step 1: Create useWebSocket.ts**

```typescript
import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuthStore } from '@/stores'

export type WebSocketEvent =
  | { type: 'node.created'; data: { id: string; mac_address: string } }
  | { type: 'node.state_changed'; data: { id: string; old_state: string; new_state: string } }
  | { type: 'node.updated'; data: { id: string } }
  | { type: 'approval.requested'; data: { id: string; action: string; target: string } }
  | { type: 'approval.resolved'; data: { id: string; status: 'approved' | 'rejected' } }
  | { type: 'wipe.progress'; data: { node_id: string; progress: number } }

type EventHandler = (event: WebSocketEvent) => void

interface UseWebSocketOptions {
  onMessage?: EventHandler
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Event) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

interface UseWebSocketReturn {
  isConnected: boolean
  send: (message: unknown) => void
  reconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options

  const { accessToken, isAuthenticated } = useAuthStore()
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    if (!isAuthenticated || !accessToken) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${accessToken}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      reconnectAttemptsRef.current = 0
      onConnect?.()
    }

    ws.onclose = () => {
      setIsConnected(false)
      onDisconnect?.()

      // Attempt to reconnect
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current++
          connect()
        }, reconnectInterval)
      }
    }

    ws.onerror = (error) => {
      onError?.(error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketEvent
        onMessage?.(data)
      } catch {
        console.error('Failed to parse WebSocket message:', event.data)
      }
    }
  }, [isAuthenticated, accessToken, onConnect, onDisconnect, onError, onMessage, reconnectInterval, maxReconnectAttempts])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const send = useCallback((message: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  const reconnect = useCallback(() => {
    disconnect()
    reconnectAttemptsRef.current = 0
    connect()
  }, [connect, disconnect])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { isConnected, send, reconnect }
}
```

**Step 2: Create index.ts**

```typescript
export { useWebSocket } from './useWebSocket'
export type { WebSocketEvent } from './useWebSocket'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add WebSocket hook for real-time updates"
```

---

## Task 9: Create Basic Pages

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/pages/Nodes.tsx`
- Create: `frontend/src/pages/NotFound.tsx`
- Create: `frontend/src/pages/index.ts`

**Step 1: Create Dashboard.tsx**

```typescript
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { Server, Activity, AlertCircle, CheckCircle } from 'lucide-react'

export function Dashboard() {
  // Placeholder data - will be replaced with real API calls
  const stats = {
    total: 42,
    active: 28,
    discovered: 5,
    installing: 3,
  }

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Nodes</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-xs text-muted-foreground">Across all states</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.active}</div>
            <p className="text-xs text-muted-foreground">Running in production</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Discovered</CardTitle>
            <AlertCircle className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.discovered}</div>
            <p className="text-xs text-muted-foreground">Awaiting assignment</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Installing</CardTitle>
            <Activity className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.installing}</div>
            <p className="text-xs text-muted-foreground">In progress</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>New Discoveries</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No new nodes discovered in the last hour.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Activity feed will be displayed here.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
```

**Step 2: Create Login.tsx**

```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Label, Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui'
import { useAuthStore } from '@/stores'

export function Login() {
  const navigate = useNavigate()
  const { login, isLoading } = useAuthStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <img src="/pureboot-logo.png" alt="PureBoot" className="h-16 w-16" />
          </div>
          <CardTitle className="text-2xl">Welcome to PureBoot</CardTitle>
          <CardDescription>
            Enter your credentials to sign in
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="admin@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 3: Create Nodes.tsx**

```typescript
import { Card, CardContent, CardHeader, CardTitle, Badge, Button } from '@/components/ui'
import { Plus, Search } from 'lucide-react'
import { Input } from '@/components/ui'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

// Placeholder data
const mockNodes = [
  { id: '1', hostname: 'web-server-01', mac_address: 'AA:BB:CC:DD:EE:01', state: 'active' as NodeState, arch: 'x86_64', last_seen_at: '2m ago' },
  { id: '2', hostname: 'db-server-01', mac_address: 'AA:BB:CC:DD:EE:02', state: 'pending' as NodeState, arch: 'x86_64', last_seen_at: '5m ago' },
  { id: '3', hostname: null, mac_address: 'AA:BB:CC:DD:EE:03', state: 'discovered' as NodeState, arch: 'arm64', last_seen_at: '1m ago' },
  { id: '4', hostname: 'old-server-03', mac_address: 'AA:BB:CC:DD:EE:04', state: 'retired' as NodeState, arch: 'x86_64', last_seen_at: '3d ago' },
]

function StateBadge({ state }: { state: NodeState }) {
  return (
    <Badge
      variant="outline"
      className={cn('border-0 text-white', NODE_STATE_COLORS[state])}
    >
      {NODE_STATE_LABELS[state]}
    </Badge>
  )
}

export function Nodes() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Nodes</h2>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Register Node
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search nodes..." className="pl-10" />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="p-3 text-left text-sm font-medium">Hostname</th>
                  <th className="p-3 text-left text-sm font-medium">MAC Address</th>
                  <th className="p-3 text-left text-sm font-medium">State</th>
                  <th className="p-3 text-left text-sm font-medium">Arch</th>
                  <th className="p-3 text-left text-sm font-medium">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {mockNodes.map((node) => (
                  <tr key={node.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="p-3 text-sm font-medium">
                      {node.hostname || <span className="text-muted-foreground">(undiscovered)</span>}
                    </td>
                    <td className="p-3 text-sm font-mono text-muted-foreground">
                      {node.mac_address}
                    </td>
                    <td className="p-3">
                      <StateBadge state={node.state} />
                    </td>
                    <td className="p-3 text-sm">{node.arch}</td>
                    <td className="p-3 text-sm text-muted-foreground">{node.last_seen_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 4: Create NotFound.tsx**

```typescript
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui'
import { Home } from 'lucide-react'

export function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
      <h1 className="text-6xl font-bold text-muted-foreground">404</h1>
      <h2 className="mt-4 text-2xl font-semibold">Page Not Found</h2>
      <p className="mt-2 text-muted-foreground">
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">
          <Home className="mr-2 h-4 w-4" />
          Back to Dashboard
        </Link>
      </Button>
    </div>
  )
}
```

**Step 5: Create index.ts**

```typescript
export { Dashboard } from './Dashboard'
export { Login } from './Login'
export { Nodes } from './Nodes'
export { NotFound } from './NotFound'
```

**Step 6: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(frontend): add basic pages (dashboard, login, nodes, 404)"
```

---

## Task 10: Create App Entry Point and Router

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/router.tsx`

**Step 1: Create router.tsx**

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Login, Nodes, NotFound } from '@/pages'
import { useAuthStore } from '@/stores'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <PublicRoute>
        <Login />
      </PublicRoute>
    ),
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'nodes', element: <Nodes /> },
      { path: 'groups', element: <div>Device Groups (Coming Soon)</div> },
      { path: 'workflows', element: <div>Workflows (Coming Soon)</div> },
      { path: 'templates', element: <div>Templates (Coming Soon)</div> },
      { path: 'hypervisors', element: <div>Hypervisors (Coming Soon)</div> },
      { path: 'storage', element: <div>Storage (Coming Soon)</div> },
      { path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
      { path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
      { path: 'settings', element: <div>Settings (Coming Soon)</div> },
      { path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
```

**Step 2: Create App.tsx**

```typescript
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { router } from './router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      retry: 1,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

**Step 3: Create main.tsx**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add app entry point and router configuration"
```

---

## Task 11: Copy Logo Asset

**Files:**
- Copy: `assets/pureboot-logo.png` to `frontend/public/pureboot-logo.png`

**Step 1: Copy the logo file**

```bash
cp ../assets/pureboot-logo.png frontend/public/
```

**Step 2: Commit**

```bash
git add frontend/public/
git commit -m "feat(frontend): add PureBoot logo to public assets"
```

---

## Task 12: Final Phase 1 Commit and Push

**Step 1: Verify all files are committed**

```bash
git status
```

**Step 2: Push the feature branch**

```bash
git push -u origin feature/web-ui
```

---

## Phase 1 Complete

**What was built:**
- Vite + React + TypeScript project structure
- Tailwind CSS with dark/light mode support
- shadcn/ui base components (Button, Input, Card, Badge, etc.)
- TypeScript types for Node, Auth, and API responses
- API client with authentication support
- Zustand stores for auth and theme state
- Layout components (Sidebar, Header, AppShell)
- WebSocket hook for real-time updates
- Basic pages (Dashboard, Login, Nodes, 404)
- React Router with protected routes

**Next Phase:** Core Node Management (Dashboard with real data, Nodes table with filtering, Node detail page, State machine visualization)
