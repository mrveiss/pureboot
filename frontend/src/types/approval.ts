// Approval Rule types
export interface ApprovalRule {
  id: string
  name: string
  scope_type: 'device_group' | 'user_group' | 'global'
  scope_id: string | null
  operations: string[]
  required_approvers: number
  escalation_timeout_hours: number
  escalation_role_id: string | null
  is_active: boolean
  priority: number
  created_at: string
  updated_at: string
}

export interface ApprovalRuleCreate {
  name: string
  scope_type: 'device_group' | 'user_group' | 'global'
  scope_id?: string
  operations: string[]
  required_approvers?: number
  escalation_timeout_hours?: number
  escalation_role_id?: string
  is_active?: boolean
  priority?: number
}

export interface ApprovalRuleUpdate {
  name?: string
  scope_type?: 'device_group' | 'user_group' | 'global'
  scope_id?: string | null
  operations?: string[]
  required_approvers?: number
  escalation_timeout_hours?: number
  escalation_role_id?: string | null
  is_active?: boolean
  priority?: number
}

// Vote types
export interface ApprovalVote {
  id: string
  user_id: string
  username: string
  vote: 'approve' | 'reject'
  comment: string | null
  is_escalation_vote: boolean
  created_at: string
}

export interface VoteCreate {
  vote: 'approve' | 'reject'
  comment?: string
}

export interface VoteResult {
  vote: ApprovalVote
  is_complete: boolean
  approval_status: string
}

// Enhanced Approval types
export interface Approval {
  id: string
  requester_id: string
  requester_username?: string
  target_type: string
  target_id: string
  description: string
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  operation_type: string
  rule_id: string | null
  required_approvers: number
  escalation_count: number
  escalated_at: string | null
  expires_at: string | null
  metadata: Record<string, unknown> | null
  votes: ApprovalVote[]
  created_at: string
  updated_at: string
}

export interface ApprovalCreate {
  target_type: string
  target_id: string
  description: string
  operation_type: string
  metadata?: Record<string, unknown>
}

export interface ApprovalListResponse {
  data: Approval[]
  total: number
}

export interface ApprovalStatsResponse {
  pending_count: number
}

export interface ApprovalApiResponse {
  success: boolean
  message?: string
  data?: Approval
}

// Operation types for approval rules
export const APPROVAL_OPERATIONS = [
  'node.provision',
  'node.retire',
  'node.delete',
  'workflow.execute',
  'group.modify',
  'user.create',
  'user.delete',
  'role.modify',
] as const

export type ApprovalOperation = typeof APPROVAL_OPERATIONS[number]

// Scope type labels
export const SCOPE_TYPE_LABELS: Record<string, string> = {
  device_group: 'Device Group',
  user_group: 'User Group',
  global: 'Global',
}

export const ACTION_TYPE_LABELS: Record<string, string> = {
  bulk_wipe: 'Bulk Wipe',
  bulk_retire: 'Bulk Retire',
  delete_template: 'Delete Template',
  production_state_change: 'Production State Change',
  'node.provision': 'Node Provision',
  'node.retire': 'Node Retire',
  'node.delete': 'Node Delete',
  'workflow.execute': 'Workflow Execute',
  'group.modify': 'Group Modify',
  'user.create': 'User Create',
  'user.delete': 'User Delete',
  'role.modify': 'Role Modify',
}

export const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  cancelled: 'Cancelled',
}

export const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-gray-100 text-gray-800',
  cancelled: 'bg-gray-100 text-gray-500',
}
