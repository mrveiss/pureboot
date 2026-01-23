export interface LdapConfig {
  id: string
  name: string
  server_url: string
  use_ssl: boolean
  use_start_tls: boolean
  bind_dn: string
  base_dn: string
  user_search_filter: string
  group_search_filter: string
  username_attribute: string
  email_attribute: string
  display_name_attribute: string
  group_attribute: string
  is_active: boolean
  is_primary: boolean
  sync_groups: boolean
  auto_create_users: boolean
  created_at: string
  updated_at: string
  last_sync_at: string | null
}

export interface LdapConfigCreate {
  name: string
  server_url: string
  use_ssl?: boolean
  use_start_tls?: boolean
  bind_dn: string
  bind_password: string
  base_dn: string
  user_search_filter?: string
  group_search_filter?: string
  username_attribute?: string
  email_attribute?: string
  display_name_attribute?: string
  group_attribute?: string
  is_active?: boolean
  is_primary?: boolean
  sync_groups?: boolean
  auto_create_users?: boolean
}

export interface LdapConfigUpdate {
  name?: string
  server_url?: string
  use_ssl?: boolean
  use_start_tls?: boolean
  bind_dn?: string
  bind_password?: string
  base_dn?: string
  user_search_filter?: string
  group_search_filter?: string
  username_attribute?: string
  email_attribute?: string
  display_name_attribute?: string
  group_attribute?: string
  is_active?: boolean
  is_primary?: boolean
  sync_groups?: boolean
  auto_create_users?: boolean
}

export interface LdapTestResult {
  success: boolean
  message: string
}
