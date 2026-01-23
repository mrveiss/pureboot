import { useState } from 'react'
import {
  Plus,
  FileCode,
  Disc,
  Cloud,
  Terminal,
  Pencil,
  Trash2,
  HardDrive,
  Cpu,
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
} from '@/components/ui'
import {
  useTemplates,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useStorageBackends,
} from '@/hooks'
import type { Template, TemplateType } from '@/types'
import {
  TEMPLATE_TYPE_LABELS,
  OS_FAMILY_LABELS,
  ARCHITECTURE_LABELS,
} from '@/types'

const TEMPLATE_TYPES: TemplateType[] = ['iso', 'kickstart', 'preseed', 'autounattend', 'cloud-init', 'script']
const OS_FAMILIES = ['linux', 'windows', 'bsd']
const ARCHITECTURES = ['x86_64', 'aarch64', 'armv7l']

function formatBytes(bytes: number | null): string {
  if (!bytes) return 'N/A'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(1)} ${units[i]}`
}

function getTypeIcon(type: TemplateType) {
  switch (type) {
    case 'iso':
      return <Disc className="h-5 w-5" />
    case 'cloud-init':
      return <Cloud className="h-5 w-5" />
    case 'script':
      return <Terminal className="h-5 w-5" />
    default:
      return <FileCode className="h-5 w-5" />
  }
}

interface FormData {
  name: string
  type: TemplateType
  os_family: string
  os_name: string
  os_version: string
  architecture: string
  file_path: string
  storage_backend_id: string
  description: string
}

const initialFormData: FormData = {
  name: '',
  type: 'iso',
  os_family: '',
  os_name: '',
  os_version: '',
  architecture: 'x86_64',
  file_path: '',
  storage_backend_id: '',
  description: '',
}

export function Templates() {
  const { data: response, isLoading } = useTemplates()
  const { data: backendsResponse } = useStorageBackends()
  const createTemplate = useCreateTemplate()
  const updateTemplate = useUpdateTemplate()
  const deleteTemplate = useDeleteTemplate()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null)
  const [deletingTemplate, setDeletingTemplate] = useState<Template | null>(null)
  const [formData, setFormData] = useState<FormData>(initialFormData)

  const templates = response?.data ?? []
  const backends = backendsResponse?.data ?? []

  const handleCreate = () => {
    const payload: Record<string, string | null> = {
      name: formData.name,
      type: formData.type,
      architecture: formData.architecture,
    }
    if (formData.os_family) payload.os_family = formData.os_family
    if (formData.os_name) payload.os_name = formData.os_name
    if (formData.os_version) payload.os_version = formData.os_version
    if (formData.file_path) payload.file_path = formData.file_path
    if (formData.storage_backend_id && formData.storage_backend_id !== 'none') {
      payload.storage_backend_id = formData.storage_backend_id
    }
    if (formData.description) payload.description = formData.description

    createTemplate.mutate(payload as unknown as Parameters<typeof createTemplate.mutate>[0], {
      onSuccess: () => {
        setIsCreateOpen(false)
        setFormData(initialFormData)
      },
    })
  }

  const handleUpdate = () => {
    if (!editingTemplate) return
    const payload: Record<string, string | null> = {}
    if (formData.name !== editingTemplate.name) payload.name = formData.name
    if (formData.type !== editingTemplate.type) payload.type = formData.type
    if (formData.os_family !== (editingTemplate.os_family || '')) payload.os_family = formData.os_family || null
    if (formData.os_name !== (editingTemplate.os_name || '')) payload.os_name = formData.os_name || null
    if (formData.os_version !== (editingTemplate.os_version || '')) payload.os_version = formData.os_version || null
    if (formData.architecture !== editingTemplate.architecture) payload.architecture = formData.architecture
    if (formData.file_path !== (editingTemplate.file_path || '')) payload.file_path = formData.file_path || null
    if (formData.description !== (editingTemplate.description || '')) payload.description = formData.description || null

    const backendId = formData.storage_backend_id === 'none' ? null : formData.storage_backend_id
    if (backendId !== editingTemplate.storage_backend_id) {
      payload.storage_backend_id = backendId
    }

    updateTemplate.mutate(
      { templateId: editingTemplate.id, data: payload },
      {
        onSuccess: () => {
          setEditingTemplate(null)
          setFormData(initialFormData)
        },
      }
    )
  }

  const handleDelete = () => {
    if (!deletingTemplate) return
    deleteTemplate.mutate(deletingTemplate.id, {
      onSuccess: () => setDeletingTemplate(null),
    })
  }

  const openEdit = (template: Template) => {
    setFormData({
      name: template.name,
      type: template.type,
      os_family: template.os_family || '',
      os_name: template.os_name || '',
      os_version: template.os_version || '',
      architecture: template.architecture,
      file_path: template.file_path || '',
      storage_backend_id: template.storage_backend_id || 'none',
      description: template.description || '',
    })
    setEditingTemplate(template)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Templates</h2>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Template
        </Button>
      </div>

      <p className="text-muted-foreground">
        Manage OS installation templates including ISOs, kickstart files, preseeds, and cloud-init configs.
      </p>

      {isLoading ? (
        <div className="text-muted-foreground">Loading templates...</div>
      ) : templates.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <FileCode className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No templates configured.</p>
              <p className="text-sm mt-1">Add templates to enable OS provisioning.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => (
            <Card key={template.id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    {getTypeIcon(template.type)}
                    {template.name}
                  </CardTitle>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => openEdit(template)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => setDeletingTemplate(template)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">
                    {TEMPLATE_TYPE_LABELS[template.type] || template.type}
                  </Badge>
                  {template.os_family && (
                    <Badge variant="outline">
                      {OS_FAMILY_LABELS[template.os_family] || template.os_family}
                    </Badge>
                  )}
                  <Badge variant="outline" className="flex items-center gap-1">
                    <Cpu className="h-3 w-3" />
                    {template.architecture}
                  </Badge>
                </div>

                {(template.os_name || template.os_version) && (
                  <div className="text-sm">
                    <span className="text-muted-foreground">OS: </span>
                    {[template.os_name, template.os_version].filter(Boolean).join(' ')}
                  </div>
                )}

                {template.description && (
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {template.description}
                  </p>
                )}

                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
                  <div className="flex items-center gap-1">
                    <HardDrive className="h-3 w-3" />
                    {formatBytes(template.size_bytes)}
                  </div>
                  {template.storage_backend_name && (
                    <span>{template.storage_backend_name}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Add Template</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
            <div className="space-y-2">
              <Label htmlFor="name">Name <span className="text-destructive">*</span></Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Ubuntu 24.04 Server"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Type <span className="text-destructive">*</span></Label>
                <Select
                  value={formData.type}
                  onValueChange={(v) => setFormData({ ...formData, type: v as TemplateType })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TEMPLATE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {TEMPLATE_TYPE_LABELS[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Architecture</Label>
                <Select
                  value={formData.architecture}
                  onValueChange={(v) => setFormData({ ...formData, architecture: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ARCHITECTURES.map((arch) => (
                      <SelectItem key={arch} value={arch}>
                        {ARCHITECTURE_LABELS[arch] || arch}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>OS Family</Label>
                <Select
                  value={formData.os_family || 'none'}
                  onValueChange={(v) => setFormData({ ...formData, os_family: v === 'none' ? '' : v })}
                >
                  <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {OS_FAMILIES.map((family) => (
                      <SelectItem key={family} value={family}>
                        {OS_FAMILY_LABELS[family] || family}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="os_name">OS Name</Label>
                <Input
                  id="os_name"
                  value={formData.os_name}
                  onChange={(e) => setFormData({ ...formData, os_name: e.target.value })}
                  placeholder="Ubuntu"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="os_version">Version</Label>
                <Input
                  id="os_version"
                  value={formData.os_version}
                  onChange={(e) => setFormData({ ...formData, os_version: e.target.value })}
                  placeholder="24.04"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Storage Backend</Label>
              <Select
                value={formData.storage_backend_id || 'none'}
                onValueChange={(v) => setFormData({ ...formData, storage_backend_id: v })}
              >
                <SelectTrigger><SelectValue placeholder="Select backend..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {backends.map((backend) => (
                    <SelectItem key={backend.id} value={backend.id}>
                      {backend.name} ({backend.type})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="file_path">File Path</Label>
              <Input
                id="file_path"
                value={formData.file_path}
                onChange={(e) => setFormData({ ...formData, file_path: e.target.value })}
                placeholder="/isos/ubuntu-24.04-live-server-amd64.iso"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optional description..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!formData.name || createTemplate.isPending}>
              {createTemplate.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingTemplate} onOpenChange={(open) => !open && setEditingTemplate(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Edit Template</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Type</Label>
                <Select
                  value={formData.type}
                  onValueChange={(v) => setFormData({ ...formData, type: v as TemplateType })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TEMPLATE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {TEMPLATE_TYPE_LABELS[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Architecture</Label>
                <Select
                  value={formData.architecture}
                  onValueChange={(v) => setFormData({ ...formData, architecture: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ARCHITECTURES.map((arch) => (
                      <SelectItem key={arch} value={arch}>
                        {ARCHITECTURE_LABELS[arch] || arch}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>OS Family</Label>
                <Select
                  value={formData.os_family || 'none'}
                  onValueChange={(v) => setFormData({ ...formData, os_family: v === 'none' ? '' : v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {OS_FAMILIES.map((family) => (
                      <SelectItem key={family} value={family}>
                        {OS_FAMILY_LABELS[family] || family}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-os_name">OS Name</Label>
                <Input
                  id="edit-os_name"
                  value={formData.os_name}
                  onChange={(e) => setFormData({ ...formData, os_name: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-os_version">Version</Label>
                <Input
                  id="edit-os_version"
                  value={formData.os_version}
                  onChange={(e) => setFormData({ ...formData, os_version: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Storage Backend</Label>
              <Select
                value={formData.storage_backend_id || 'none'}
                onValueChange={(v) => setFormData({ ...formData, storage_backend_id: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {backends.map((backend) => (
                    <SelectItem key={backend.id} value={backend.id}>
                      {backend.name} ({backend.type})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-file_path">File Path</Label>
              <Input
                id="edit-file_path"
                value={formData.file_path}
                onChange={(e) => setFormData({ ...formData, file_path: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-description">Description</Label>
              <Input
                id="edit-description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingTemplate(null)}>
              Cancel
            </Button>
            <Button onClick={handleUpdate} disabled={!formData.name || updateTemplate.isPending}>
              {updateTemplate.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingTemplate} onOpenChange={(open) => !open && setDeletingTemplate(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Template</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingTemplate?.name}</strong>?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingTemplate(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteTemplate.isPending}
            >
              {deleteTemplate.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
