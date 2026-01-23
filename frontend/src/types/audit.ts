export interface AuditLog {
  id: string
  timestamp: string
  actor_id: string | null
  actor_type: 'user' | 'service_account' | 'system' | 'anonymous'
  actor_username: string
  actor_ip: string | null
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  details: Record<string, unknown> | null
  result: 'success' | 'failure' | 'denied'
  error_message: string | null
  session_id: string | null
  auth_method: string | null
}

export interface AuditLogListResponse {
  items: AuditLog[]
  total: number
  page: number
  page_size: number
}

export interface AuditFilters {
  action?: string
  resource_type?: string
  actor_username?: string
  result?: string
  from_date?: string
  to_date?: string
}

export const AUDIT_RESULT_COLORS: Record<string, string> = {
  success: 'bg-green-100 text-green-800',
  failure: 'bg-red-100 text-red-800',
  denied: 'bg-yellow-100 text-yellow-800',
}

export const AUDIT_ACTOR_TYPE_LABELS: Record<string, string> = {
  user: 'User',
  service_account: 'Service Account',
  system: 'System',
  anonymous: 'Anonymous',
}
