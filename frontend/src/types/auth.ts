export type UserRole = 'admin' | 'operator' | 'approver' | 'viewer'

export interface User {
  id: string
  username: string
  email: string | null
  role: UserRole
  is_active: boolean
  last_login_at: string | null
  created_at: string
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthTokens {
  access_token: string
  token_type: string
  expires_in: number
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
}

export interface UserCreate {
  username: string
  email?: string
  password: string
  role?: UserRole
}

export interface UserUpdate {
  email?: string | null
  role?: UserRole
  is_active?: boolean
}

export interface PasswordChange {
  current_password?: string
  new_password: string
}

export interface UserListResponse {
  data: User[]
  total: number
}

export interface UserApiResponse {
  success: boolean
  message?: string
  data?: User | AuthTokens
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Administrator',
  operator: 'Operator',
  approver: 'Approver',
  viewer: 'Viewer',
}

export const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  admin: 'Full system access, user management',
  operator: 'Manage nodes, workflows, and templates',
  approver: 'Approve sensitive operations',
  viewer: 'Read-only access',
}

export const ROLE_COLORS: Record<UserRole, string> = {
  admin: 'bg-red-100 text-red-800',
  operator: 'bg-blue-100 text-blue-800',
  approver: 'bg-purple-100 text-purple-800',
  viewer: 'bg-gray-100 text-gray-800',
}
