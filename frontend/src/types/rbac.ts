// User Groups
export interface UserGroup {
  id: string
  name: string
  description: string | null
  requires_approval: boolean
  ldap_group_dn: string | null
  member_count: number
  role_names: string[]
  created_at: string
  updated_at?: string
}

export interface UserGroupMember {
  id: string
  username: string
  email: string | null
}

export interface UserGroupRole {
  id: string
  name: string
  description: string | null
}

export interface UserGroupAccess {
  device_groups: { id: string; name: string }[]
  tags: string[]
  node_ids: string[]
}

export interface UserGroupDetail extends UserGroup {
  members: UserGroupMember[]
  roles: UserGroupRole[]
  access: UserGroupAccess
}

// Roles & Permissions
export interface Permission {
  id: string
  resource: string
  action: string
  description: string | null
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permission_count: number
  created_at: string
}

export interface RoleDetail extends Role {
  permissions: Permission[]
  updated_at: string
}

// Service Accounts
export interface ServiceAccount {
  id: string
  username: string
  description: string | null
  role: string | null
  is_active: boolean
  expires_at: string | null
  owner_username: string | null
  api_key_count: number
  created_at: string
}

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  is_active: boolean
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  last_used_ip: string | null
}

export interface ApiKeyCreate extends ApiKey {
  full_key: string // Only at creation
}

export interface ServiceAccountDetail extends ServiceAccount {
  updated_at: string
  api_keys: ApiKey[]
}
