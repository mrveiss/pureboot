export interface ApprovalVote {
  id: string
  user_id: string | null
  user_name: string
  vote: 'approve' | 'reject'
  comment: string | null
  created_at: string
}

export interface Approval {
  id: string
  action_type: string
  action_data: Record<string, unknown>
  requester_id: string | null
  requester_name: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled'
  required_approvers: number
  current_approvals: number
  current_rejections: number
  expires_at: string
  resolved_at: string | null
  created_at: string
  votes: ApprovalVote[]
}

export interface ApprovalCreate {
  action_type: string
  action_data: Record<string, unknown>
  requester_name: string
  requester_id?: string
  required_approvers?: number
}

export interface VoteCreate {
  user_name: string
  user_id?: string
  comment?: string
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

export const ACTION_TYPE_LABELS: Record<string, string> = {
  bulk_wipe: 'Bulk Wipe',
  bulk_retire: 'Bulk Retire',
  delete_template: 'Delete Template',
  production_state_change: 'Production State Change',
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
