import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus,
  FolderOpen,
  MoreVertical,
  Pencil,
  Trash2,
  Users,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Label,
  Checkbox,
} from '@/components/ui'
import { useGroups, useCreateGroup, useUpdateGroup, useDeleteGroup } from '@/hooks'
import type { DeviceGroup } from '@/types'
import { cn } from '@/lib/utils'

export function Groups() {
  const { data: response, isLoading } = useGroups()
  const createGroup = useCreateGroup()
  const updateGroup = useUpdateGroup()
  const deleteGroup = useDeleteGroup()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<DeviceGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<DeviceGroup | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    auto_provision: false,
  })

  const groups = response?.data ?? []

  const handleCreate = () => {
    createGroup.mutate(formData, {
      onSuccess: () => {
        setIsCreateOpen(false)
        setFormData({ name: '', description: '', auto_provision: false })
      },
    })
  }

  const handleUpdate = () => {
    if (!editingGroup) return
    updateGroup.mutate(
      { groupId: editingGroup.id, data: formData },
      {
        onSuccess: () => {
          setEditingGroup(null)
          setFormData({ name: '', description: '', auto_provision: false })
        },
      }
    )
  }

  const handleDelete = () => {
    if (!deletingGroup) return
    deleteGroup.mutate(deletingGroup.id, {
      onSuccess: () => setDeletingGroup(null),
    })
  }

  const openEdit = (group: DeviceGroup) => {
    setFormData({
      name: group.name,
      description: group.description ?? '',
      auto_provision: group.auto_provision,
    })
    setEditingGroup(group)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Device Groups</h2>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Group
        </Button>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading groups...</div>
      ) : groups.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <FolderOpen className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No groups created yet.</p>
              <p className="text-sm mt-1">Create a group to organize your nodes.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => (
            <Card key={group.id} className="relative">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <FolderOpen className="h-5 w-5" />
                    {group.name}
                  </CardTitle>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => openEdit(group)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => setDeletingGroup(group)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">
                  {group.description || 'No description'}
                </p>
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1">
                    <Users className="h-4 w-4" />
                    <span>{group.node_count} nodes</span>
                  </div>
                  {group.auto_provision && (
                    <span className="text-xs bg-green-500/10 text-green-600 px-2 py-1 rounded">
                      Auto-provision
                    </span>
                  )}
                </div>
                <Link
                  to={`/groups/${group.id}`}
                  className="absolute inset-0"
                  aria-label={`View ${group.name}`}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Device Group</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Production Servers"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optional description"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="auto_provision"
                checked={formData.auto_provision}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, auto_provision: !!checked })
                }
              />
              <Label htmlFor="auto_provision" className="font-normal">
                Auto-provision new nodes in this group
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!formData.name || createGroup.isPending}>
              {createGroup.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingGroup} onOpenChange={(open) => !open && setEditingGroup(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Device Group</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
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
            <div className="flex items-center gap-2">
              <Checkbox
                id="edit-auto_provision"
                checked={formData.auto_provision}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, auto_provision: !!checked })
                }
              />
              <Label htmlFor="edit-auto_provision" className="font-normal">
                Auto-provision new nodes in this group
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingGroup(null)}>
              Cancel
            </Button>
            <Button onClick={handleUpdate} disabled={!formData.name || updateGroup.isPending}>
              {updateGroup.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingGroup} onOpenChange={(open) => !open && setDeletingGroup(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Group</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingGroup?.name}</strong>?
            {deletingGroup?.node_count && deletingGroup.node_count > 0 && (
              <span className="block mt-2 text-sm text-muted-foreground">
                This group has {deletingGroup.node_count} nodes. They will be unassigned from this group.
              </span>
            )}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingGroup(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteGroup.isPending}
            >
              {deleteGroup.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
