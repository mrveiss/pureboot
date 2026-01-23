import { useState, useEffect } from 'react'
import { ldapApi } from '@/api'
import type { LdapConfig as LdapConfigType, LdapConfigCreate, LdapConfigUpdate, LdapTestResult } from '@/types'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Label,
  Switch,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui'
import {
  Plus,
  Pencil,
  Trash2,
  Server,
  Play,
  CheckCircle,
  XCircle,
  ChevronDown,
  Loader2,
} from 'lucide-react'

interface FormData {
  name: string
  server_url: string
  use_ssl: boolean
  use_start_tls: boolean
  bind_dn: string
  bind_password: string
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
}

const initialFormData: FormData = {
  name: '',
  server_url: '',
  use_ssl: true,
  use_start_tls: false,
  bind_dn: '',
  bind_password: '',
  base_dn: '',
  user_search_filter: '(objectClass=person)',
  group_search_filter: '(objectClass=group)',
  username_attribute: 'sAMAccountName',
  email_attribute: 'mail',
  display_name_attribute: 'displayName',
  group_attribute: 'memberOf',
  is_active: true,
  is_primary: false,
  sync_groups: true,
  auto_create_users: true,
}

export function LdapConfig() {
  const [configs, setConfigs] = useState<LdapConfigType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<LdapConfigType | null>(null)
  const [deletingConfig, setDeletingConfig] = useState<LdapConfigType | null>(null)
  const [testResults, setTestResults] = useState<Record<string, LdapTestResult>>({})
  const [testingId, setTestingId] = useState<string | null>(null)
  const [formData, setFormData] = useState<FormData>(initialFormData)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    loadConfigs()
  }, [])

  const loadConfigs = async () => {
    try {
      setLoading(true)
      const data = await ldapApi.list()
      setConfigs(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load LDAP configurations')
    } finally {
      setLoading(false)
    }
  }

  const handleTest = async (config: LdapConfigType) => {
    setTestingId(config.id)
    try {
      const result = await ldapApi.test(config.id)
      setTestResults((prev) => ({ ...prev, [config.id]: result }))
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [config.id]: {
          success: false,
          message: err instanceof Error ? err.message : 'Connection test failed',
        },
      }))
    } finally {
      setTestingId(null)
    }
  }

  const openCreateDialog = () => {
    setFormData(initialFormData)
    setEditingConfig(null)
    setAdvancedOpen(false)
    setDialogOpen(true)
  }

  const openEditDialog = (config: LdapConfigType) => {
    setFormData({
      name: config.name,
      server_url: config.server_url,
      use_ssl: config.use_ssl,
      use_start_tls: config.use_start_tls,
      bind_dn: config.bind_dn,
      bind_password: '', // Never pre-fill password
      base_dn: config.base_dn,
      user_search_filter: config.user_search_filter,
      group_search_filter: config.group_search_filter,
      username_attribute: config.username_attribute,
      email_attribute: config.email_attribute,
      display_name_attribute: config.display_name_attribute,
      group_attribute: config.group_attribute,
      is_active: config.is_active,
      is_primary: config.is_primary,
      sync_groups: config.sync_groups,
      auto_create_users: config.auto_create_users,
    })
    setEditingConfig(config)
    setAdvancedOpen(false)
    setDialogOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (editingConfig) {
        // Update existing config
        const updateData: LdapConfigUpdate = {
          name: formData.name,
          server_url: formData.server_url,
          use_ssl: formData.use_ssl,
          use_start_tls: formData.use_start_tls,
          bind_dn: formData.bind_dn,
          base_dn: formData.base_dn,
          user_search_filter: formData.user_search_filter,
          group_search_filter: formData.group_search_filter,
          username_attribute: formData.username_attribute,
          email_attribute: formData.email_attribute,
          display_name_attribute: formData.display_name_attribute,
          group_attribute: formData.group_attribute,
          is_active: formData.is_active,
          is_primary: formData.is_primary,
          sync_groups: formData.sync_groups,
          auto_create_users: formData.auto_create_users,
        }
        // Only include password if it was changed
        if (formData.bind_password) {
          updateData.bind_password = formData.bind_password
        }
        await ldapApi.update(editingConfig.id, updateData)
      } else {
        // Create new config
        const createData: LdapConfigCreate = {
          name: formData.name,
          server_url: formData.server_url,
          use_ssl: formData.use_ssl,
          use_start_tls: formData.use_start_tls,
          bind_dn: formData.bind_dn,
          bind_password: formData.bind_password,
          base_dn: formData.base_dn,
          user_search_filter: formData.user_search_filter,
          group_search_filter: formData.group_search_filter,
          username_attribute: formData.username_attribute,
          email_attribute: formData.email_attribute,
          display_name_attribute: formData.display_name_attribute,
          group_attribute: formData.group_attribute,
          is_active: formData.is_active,
          is_primary: formData.is_primary,
          sync_groups: formData.sync_groups,
          auto_create_users: formData.auto_create_users,
        }
        await ldapApi.create(createData)
      }
      setDialogOpen(false)
      loadConfigs()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save LDAP configuration')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deletingConfig) return
    setDeleting(true)
    try {
      await ldapApi.delete(deletingConfig.id)
      setDeletingConfig(null)
      loadConfigs()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete LDAP configuration')
    } finally {
      setDeleting(false)
    }
  }

  const isFormValid = () => {
    if (!formData.name || !formData.server_url || !formData.bind_dn || !formData.base_dn) {
      return false
    }
    // Password is required only for new configs
    if (!editingConfig && !formData.bind_password) {
      return false
    }
    return true
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">LDAP/AD Configuration</h1>
          <p className="text-muted-foreground">
            Configure LDAP or Active Directory servers for user authentication
          </p>
        </div>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4 mr-2" />
          Add LDAP Server
        </Button>
      </div>

      {error && (
        <div className="p-4 text-destructive bg-destructive/10 rounded-md">
          {error}
        </div>
      )}

      {configs.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <Server className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No LDAP servers configured.</p>
              <p className="text-sm mt-1">Add an LDAP or Active Directory server to enable external authentication.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {configs.map((config) => (
            <Card key={config.id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="h-5 w-5 text-primary" />
                    <CardTitle className="text-lg">{config.name}</CardTitle>
                  </div>
                  <div className="flex gap-1">
                    {config.is_active && (
                      <Badge variant="default" className="bg-green-100 text-green-800">
                        Active
                      </Badge>
                    )}
                    {config.is_primary && (
                      <Badge variant="secondary">Primary</Badge>
                    )}
                  </div>
                </div>
                <CardDescription className="mt-1">{config.server_url}</CardDescription>
              </CardHeader>
              <CardContent className="pb-2">
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Base DN:</span>
                    <span className="font-mono text-xs">{config.base_dn}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">SSL/TLS:</span>
                    <span>
                      {config.use_ssl ? 'SSL' : config.use_start_tls ? 'StartTLS' : 'None'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Auto-create users:</span>
                    <span>{config.auto_create_users ? 'Yes' : 'No'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Sync groups:</span>
                    <span>{config.sync_groups ? 'Yes' : 'No'}</span>
                  </div>
                </div>
                {testResults[config.id] && (
                  <div
                    className={`mt-3 p-2 rounded text-sm flex items-center gap-2 ${
                      testResults[config.id].success
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {testResults[config.id].success ? (
                      <CheckCircle className="h-4 w-4" />
                    ) : (
                      <XCircle className="h-4 w-4" />
                    )}
                    {testResults[config.id].message}
                  </div>
                )}
              </CardContent>
              <CardFooter className="pt-2 flex justify-between">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleTest(config)}
                  disabled={testingId === config.id}
                >
                  {testingId === config.id ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  Test Connection
                </Button>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => openEditDialog(config)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive"
                    onClick={() => setDeletingConfig(config)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[550px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingConfig ? `Edit: ${editingConfig.name}` : 'Add LDAP Server'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Basic Settings */}
            <div className="space-y-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Corporate AD"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="server_url">
                Server URL <span className="text-destructive">*</span>
              </Label>
              <Input
                id="server_url"
                value={formData.server_url}
                onChange={(e) => setFormData({ ...formData, server_url: e.target.value })}
                placeholder="ldaps://ad.example.com:636"
              />
            </div>

            <div className="flex gap-6">
              <div className="flex items-center gap-2">
                <Switch
                  id="use_ssl"
                  checked={formData.use_ssl}
                  onCheckedChange={(checked: boolean) =>
                    setFormData({ ...formData, use_ssl: checked, use_start_tls: checked ? false : formData.use_start_tls })
                  }
                />
                <Label htmlFor="use_ssl">Use SSL</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="use_start_tls"
                  checked={formData.use_start_tls}
                  onCheckedChange={(checked: boolean) =>
                    setFormData({ ...formData, use_start_tls: checked, use_ssl: checked ? false : formData.use_ssl })
                  }
                />
                <Label htmlFor="use_start_tls">Use StartTLS</Label>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="bind_dn">
                Bind DN <span className="text-destructive">*</span>
              </Label>
              <Input
                id="bind_dn"
                value={formData.bind_dn}
                onChange={(e) => setFormData({ ...formData, bind_dn: e.target.value })}
                placeholder="CN=svc_pureboot,OU=Service Accounts,DC=example,DC=com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="bind_password">
                Bind Password {!editingConfig && <span className="text-destructive">*</span>}
              </Label>
              <Input
                id="bind_password"
                type="password"
                value={formData.bind_password}
                onChange={(e) => setFormData({ ...formData, bind_password: e.target.value })}
                placeholder={editingConfig ? 'Leave blank to keep current' : 'Enter password'}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="base_dn">
                Base DN <span className="text-destructive">*</span>
              </Label>
              <Input
                id="base_dn"
                value={formData.base_dn}
                onChange={(e) => setFormData({ ...formData, base_dn: e.target.value })}
                placeholder="DC=example,DC=com"
              />
            </div>

            {/* Advanced Settings */}
            <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" className="w-full justify-between px-0 hover:bg-transparent">
                  <span className="font-medium">Advanced Settings</span>
                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`}
                  />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="user_search_filter">User Search Filter</Label>
                  <Input
                    id="user_search_filter"
                    value={formData.user_search_filter}
                    onChange={(e) => setFormData({ ...formData, user_search_filter: e.target.value })}
                    placeholder="(objectClass=person)"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="group_search_filter">Group Search Filter</Label>
                  <Input
                    id="group_search_filter"
                    value={formData.group_search_filter}
                    onChange={(e) => setFormData({ ...formData, group_search_filter: e.target.value })}
                    placeholder="(objectClass=group)"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="username_attribute">Username Attribute</Label>
                    <Input
                      id="username_attribute"
                      value={formData.username_attribute}
                      onChange={(e) => setFormData({ ...formData, username_attribute: e.target.value })}
                      placeholder="sAMAccountName"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email_attribute">Email Attribute</Label>
                    <Input
                      id="email_attribute"
                      value={formData.email_attribute}
                      onChange={(e) => setFormData({ ...formData, email_attribute: e.target.value })}
                      placeholder="mail"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="display_name_attribute">Display Name Attribute</Label>
                    <Input
                      id="display_name_attribute"
                      value={formData.display_name_attribute}
                      onChange={(e) => setFormData({ ...formData, display_name_attribute: e.target.value })}
                      placeholder="displayName"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="group_attribute">Group Attribute</Label>
                    <Input
                      id="group_attribute"
                      value={formData.group_attribute}
                      onChange={(e) => setFormData({ ...formData, group_attribute: e.target.value })}
                      placeholder="memberOf"
                    />
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>

            {/* Toggle Settings */}
            <div className="space-y-3 pt-2 border-t">
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="is_active">Active</Label>
                  <p className="text-sm text-muted-foreground">Enable this LDAP configuration</p>
                </div>
                <Switch
                  id="is_active"
                  checked={formData.is_active}
                  onCheckedChange={(checked: boolean) => setFormData({ ...formData, is_active: checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="is_primary">Primary</Label>
                  <p className="text-sm text-muted-foreground">Use as primary authentication source</p>
                </div>
                <Switch
                  id="is_primary"
                  checked={formData.is_primary}
                  onCheckedChange={(checked: boolean) => setFormData({ ...formData, is_primary: checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="sync_groups">Sync Groups</Label>
                  <p className="text-sm text-muted-foreground">Synchronize LDAP groups with user groups</p>
                </div>
                <Switch
                  id="sync_groups"
                  checked={formData.sync_groups}
                  onCheckedChange={(checked: boolean) => setFormData({ ...formData, sync_groups: checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="auto_create_users">Auto-create Users</Label>
                  <p className="text-sm text-muted-foreground">Automatically create users on first login</p>
                </div>
                <Switch
                  id="auto_create_users"
                  checked={formData.auto_create_users}
                  onCheckedChange={(checked: boolean) => setFormData({ ...formData, auto_create_users: checked })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!isFormValid() || saving}>
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : editingConfig ? (
                'Save Changes'
              ) : (
                'Create'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingConfig} onOpenChange={(open) => !open && setDeletingConfig(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete LDAP Configuration</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingConfig?.name}</strong>?
            Users authenticated via this LDAP server will no longer be able to log in.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingConfig(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default LdapConfig
