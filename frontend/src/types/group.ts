import type { NodeState } from './node'

export interface ApprovalRule {
  action: BulkActionType
  required: boolean
  min_approvers: number
}

export type BulkActionType =
  | 'assign_workflow'
  | 'assign_group'
  | 'add_tag'
  | 'remove_tag'
  | 'change_state'
  | 'retire'
  | 'wipe'

export interface BulkAction {
  type: BulkActionType
  label: string
  icon: string
  requiresApproval: boolean
  dangerLevel: 'safe' | 'warning' | 'danger'
  allowedFromStates?: NodeState[]
}

export const BULK_ACTIONS: BulkAction[] = [
  {
    type: 'assign_workflow',
    label: 'Assign Workflow',
    icon: 'GitBranch',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'assign_group',
    label: 'Assign Group',
    icon: 'FolderOpen',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'add_tag',
    label: 'Add Tag',
    icon: 'Tag',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'remove_tag',
    label: 'Remove Tag',
    icon: 'TagOff',
    requiresApproval: false,
    dangerLevel: 'safe',
  },
  {
    type: 'change_state',
    label: 'Change State',
    icon: 'RefreshCw',
    requiresApproval: true,
    dangerLevel: 'warning',
  },
  {
    type: 'retire',
    label: 'Retire Nodes',
    icon: 'Archive',
    requiresApproval: true,
    dangerLevel: 'warning',
    allowedFromStates: ['active'],
  },
  {
    type: 'wipe',
    label: 'Wipe Nodes',
    icon: 'Trash2',
    requiresApproval: true,
    dangerLevel: 'danger',
    allowedFromStates: ['decommissioned'],
  },
]

export interface BulkOperationResult {
  success: boolean
  total: number
  succeeded: number
  failed: number
  errors: { nodeId: string; error: string }[]
}
