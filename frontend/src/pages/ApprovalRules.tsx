import { useState, useEffect } from 'react'
import {
  Plus,
  Shield,
  Pencil,
  Trash2,
  Globe,
  Users,
  Folders,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Checkbox,
} from '@/components/ui'
import { approvalRulesApi } from '@/api/approvalRules'
import { rolesApi } from '@/api/roles'
import { groupsApi } from '@/api/nodes'
import { userGroupsApi } from '@/api/userGroups'
import type { ApprovalRule, ApprovalRuleCreate, ApprovalRuleUpdate, Role, DeviceGroup, UserGroup } from '@/types'
import { APPROVAL_OPERATIONS, SCOPE_TYPE_LABELS, ACTION_TYPE_LABELS } from '@/types/approval'

type ScopeType = 'device_group' | 'user_group' | 'global'

interface FormData {
  name: string
  scope_type: ScopeType
  scope_id: string
  operations: string[]
  required_approvers: number
  escalation_timeout_hours: number
  escalation_role_id: string
  priority: number
  is_active: boolean
}

const initialFormData: FormData = {
  name: '',
  scope_type: 'global',
  scope_id: '',
  operations: [],
  required_approvers: 1,
  escalation_timeout_hours: 24,
  escalation_role_id: '',
  priority: 0,
  is_active: true,
}

function getScopeIcon(scopeType: ScopeType) {
  switch (scopeType) {
    case 'global':
      return <Globe className="h-4 w-4" />
    case 'device_group':
      return <Folders className="h-4 w-4" />
    case 'user_group':
      return <Users className="h-4 w-4" />
  }
}

function getScopeBadgeColor(scopeType: ScopeType): string {
  switch (scopeType) {
    case 'global':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
    case 'device_group':
      return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
    case 'user_group':
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
  }
}

export function ApprovalRules() {
  const [rules, setRules] = useState<ApprovalRule[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [deviceGroups, setDeviceGroups] = useState<DeviceGroup[]>([])
  const [userGroups, setUserGroups] = useState<UserGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<ApprovalRule | null>(null)
  const [deletingRule, setDeletingRule] = useState<ApprovalRule | null>(null)
  const [formData, setFormData] = useState<FormData>(initialFormData)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [rulesData, rolesData, deviceGroupsResponse, userGroupsData] = await Promise.all([
        approvalRulesApi.list(),
        rolesApi.list(),
        groupsApi.list(),
        userGroupsApi.list(),
      ])
      setRules(rulesData)
      setRoles(rolesData)
      setDeviceGroups(deviceGroupsResponse.data || [])
      setUserGroups(userGroupsData)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!formData.name || formData.operations.length === 0) return

    setSubmitting(true)
    try {
      const payload: ApprovalRuleCreate = {
        name: formData.name,
        scope_type: formData.scope_type,
        operations: formData.operations,
        required_approvers: formData.required_approvers,
        escalation_timeout_hours: formData.escalation_timeout_hours,
        is_active: formData.is_active,
        priority: formData.priority,
      }

      if (formData.scope_type !== 'global' && formData.scope_id) {
        payload.scope_id = formData.scope_id
      }

      if (formData.escalation_role_id) {
        payload.escalation_role_id = formData.escalation_role_id
      }

      const newRule = await approvalRulesApi.create(payload)
      setRules([...rules, newRule])
      setIsCreateOpen(false)
      setFormData(initialFormData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create rule')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUpdate = async () => {
    if (!editingRule || !formData.name || formData.operations.length === 0) return

    setSubmitting(true)
    try {
      const payload: ApprovalRuleUpdate = {
        name: formData.name,
        scope_type: formData.scope_type,
        scope_id: formData.scope_type === 'global' ? null : (formData.scope_id || null),
        operations: formData.operations,
        required_approvers: formData.required_approvers,
        escalation_timeout_hours: formData.escalation_timeout_hours,
        escalation_role_id: formData.escalation_role_id || null,
        is_active: formData.is_active,
        priority: formData.priority,
      }

      const updatedRule = await approvalRulesApi.update(editingRule.id, payload)
      setRules(rules.map(r => r.id === updatedRule.id ? updatedRule : r))
      setEditingRule(null)
      setFormData(initialFormData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update rule')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deletingRule) return

    setSubmitting(true)
    try {
      await approvalRulesApi.delete(deletingRule.id)
      setRules(rules.filter(r => r.id !== deletingRule.id))
      setDeletingRule(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete rule')
    } finally {
      setSubmitting(false)
    }
  }

  const openEdit = (rule: ApprovalRule) => {
    setFormData({
      name: rule.name,
      scope_type: rule.scope_type,
      scope_id: rule.scope_id || '',
      operations: rule.operations,
      required_approvers: rule.required_approvers,
      escalation_timeout_hours: rule.escalation_timeout_hours,
      escalation_role_id: rule.escalation_role_id || '',
      priority: rule.priority,
      is_active: rule.is_active,
    })
    setEditingRule(rule)
  }

  const toggleOperation = (operation: string) => {
    if (formData.operations.includes(operation)) {
      setFormData({
        ...formData,
        operations: formData.operations.filter(op => op !== operation),
      })
    } else {
      setFormData({
        ...formData,
        operations: [...formData.operations, operation],
      })
    }
  }

  const getScopeGroups = () => {
    if (formData.scope_type === 'device_group') {
      return deviceGroups
    } else if (formData.scope_type === 'user_group') {
      return userGroups
    }
    return []
  }

  const getRoleName = (roleId: string | null): string => {
    if (!roleId) return 'None'
    const role = roles.find(r => r.id === roleId)
    return role?.name || 'Unknown'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-destructive bg-destructive/10 rounded-md">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          <span>{error}</span>
        </div>
        <Button variant="outline" size="sm" className="mt-2" onClick={loadData}>
          Retry
        </Button>
      </div>
    )
  }

  const renderForm = () => (
    <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
      {/* Name */}
      <div className="space-y-2">
        <Label htmlFor="name">Name <span className="text-destructive">*</span></Label>
        <Input
          id="name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="Production Node Retirement"
        />
      </div>

      {/* Scope Type and Scope ID */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Scope Type</Label>
          <Select
            value={formData.scope_type}
            onValueChange={(v) => setFormData({
              ...formData,
              scope_type: v as ScopeType,
              scope_id: '', // Reset scope_id when type changes
            })}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="global">Global</SelectItem>
              <SelectItem value="device_group">Device Group</SelectItem>
              <SelectItem value="user_group">User Group</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {formData.scope_type !== 'global' && (
          <div className="space-y-2">
            <Label>
              {formData.scope_type === 'device_group' ? 'Device Group' : 'User Group'}
            </Label>
            <Select
              value={formData.scope_id || 'none'}
              onValueChange={(v) => setFormData({ ...formData, scope_id: v === 'none' ? '' : v })}
            >
              <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None (All)</SelectItem>
                {getScopeGroups().map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* Operations */}
      <div className="space-y-2">
        <Label>Operations <span className="text-destructive">*</span></Label>
        <div className="grid grid-cols-2 gap-2 p-3 border rounded-md max-h-40 overflow-y-auto">
          {APPROVAL_OPERATIONS.map((operation) => (
            <label
              key={operation}
              className="flex items-center gap-2 cursor-pointer text-sm hover:bg-muted/50 p-1 rounded"
            >
              <Checkbox
                checked={formData.operations.includes(operation)}
                onCheckedChange={() => toggleOperation(operation)}
              />
              <span>{ACTION_TYPE_LABELS[operation] || operation}</span>
            </label>
          ))}
        </div>
        {formData.operations.length === 0 && (
          <p className="text-sm text-destructive">Select at least one operation</p>
        )}
      </div>

      {/* Approvers and Priority */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="required_approvers">Required Approvers</Label>
          <Input
            id="required_approvers"
            type="number"
            min="1"
            max="10"
            value={formData.required_approvers}
            onChange={(e) => setFormData({
              ...formData,
              required_approvers: Math.max(1, parseInt(e.target.value) || 1),
            })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="priority">Priority</Label>
          <Input
            id="priority"
            type="number"
            min="0"
            value={formData.priority}
            onChange={(e) => setFormData({
              ...formData,
              priority: parseInt(e.target.value) || 0,
            })}
          />
          <p className="text-xs text-muted-foreground">Higher priority rules are evaluated first</p>
        </div>
      </div>

      {/* Escalation */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="escalation_timeout_hours">Escalation Timeout (hours)</Label>
          <Input
            id="escalation_timeout_hours"
            type="number"
            min="1"
            value={formData.escalation_timeout_hours}
            onChange={(e) => setFormData({
              ...formData,
              escalation_timeout_hours: Math.max(1, parseInt(e.target.value) || 24),
            })}
          />
        </div>

        <div className="space-y-2">
          <Label>Escalation Role</Label>
          <Select
            value={formData.escalation_role_id || 'none'}
            onValueChange={(v) => setFormData({ ...formData, escalation_role_id: v === 'none' ? '' : v })}
          >
            <SelectTrigger><SelectValue placeholder="Select role..." /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {roles.map((role) => (
                <SelectItem key={role.id} value={role.id}>
                  {role.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Is Active */}
      <div className="flex items-center gap-2 pt-2">
        <Checkbox
          id="is_active"
          checked={formData.is_active}
          onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
        />
        <Label htmlFor="is_active" className="cursor-pointer">
          Rule is active
        </Label>
      </div>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Approval Rules</h1>
          <p className="text-muted-foreground">
            Configure policies that require approval for sensitive operations
          </p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Rule
        </Button>
      </div>

      {rules.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <Shield className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No approval rules configured.</p>
              <p className="text-sm mt-1">Create rules to require approval for sensitive operations.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {rules.map((rule) => (
            <Card key={rule.id} className={!rule.is_active ? 'opacity-60' : undefined}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-primary" />
                    <CardTitle className="text-lg">{rule.name}</CardTitle>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => openEdit(rule)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => setDeletingRule(rule)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Scope Badge */}
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded ${getScopeBadgeColor(rule.scope_type)}`}>
                    {getScopeIcon(rule.scope_type)}
                    {SCOPE_TYPE_LABELS[rule.scope_type]}
                  </span>
                  {!rule.is_active && (
                    <span className="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                      Inactive
                    </span>
                  )}
                </div>

                {/* Operations as pills */}
                <div className="flex flex-wrap gap-1">
                  {rule.operations.slice(0, 3).map((op) => (
                    <Badge key={op} variant="secondary" className="text-xs">
                      {ACTION_TYPE_LABELS[op] || op}
                    </Badge>
                  ))}
                  {rule.operations.length > 3 && (
                    <Badge variant="outline" className="text-xs">
                      +{rule.operations.length - 3} more
                    </Badge>
                  )}
                </div>

                {/* Stats row */}
                <div className="flex items-center justify-between text-sm text-muted-foreground pt-2 border-t">
                  <div className="flex items-center gap-1">
                    <Users className="h-4 w-4" />
                    <span>{rule.required_approvers} approver{rule.required_approvers !== 1 ? 's' : ''}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="h-4 w-4" />
                    <span>{rule.escalation_timeout_hours}h escalation</span>
                  </div>
                </div>

                {/* Escalation role */}
                {rule.escalation_role_id && (
                  <div className="text-xs text-muted-foreground">
                    Escalates to: <span className="font-medium">{getRoleName(rule.escalation_role_id)}</span>
                  </div>
                )}

                {/* Priority badge */}
                <div className="text-xs text-muted-foreground">
                  Priority: <span className="font-medium">{rule.priority}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[550px]">
          <DialogHeader>
            <DialogTitle>Create Approval Rule</DialogTitle>
          </DialogHeader>
          {renderForm()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!formData.name || formData.operations.length === 0 || submitting}
            >
              {submitting ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingRule} onOpenChange={(open) => !open && setEditingRule(null)}>
        <DialogContent className="sm:max-w-[550px]">
          <DialogHeader>
            <DialogTitle>Edit Approval Rule</DialogTitle>
          </DialogHeader>
          {renderForm()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingRule(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={!formData.name || formData.operations.length === 0 || submitting}
            >
              {submitting ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingRule} onOpenChange={(open) => !open && setDeletingRule(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Approval Rule</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingRule?.name}</strong>?
            This will remove the approval requirement for the associated operations.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingRule(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={submitting}
            >
              {submitting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ApprovalRules
