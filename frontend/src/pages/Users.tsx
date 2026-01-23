import { useState } from 'react'
import {
  Users as UsersIcon,
  Plus,
  Pencil,
  Trash2,
  Key,
  Shield,
  UserX,
  UserCheck,
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
  useUsers,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useChangePassword,
} from '@/hooks/useUsers'
import type { User, UserRole, UserCreate } from '@/types'
import { ROLE_LABELS, ROLE_COLORS, ROLE_DESCRIPTIONS } from '@/types'

const ROLES: UserRole[] = ['admin', 'operator', 'approver', 'viewer']

function formatDate(dateString: string | null): string {
  if (!dateString) return 'Never'
  return new Date(dateString).toLocaleString()
}

interface UserFormData {
  username: string
  email: string
  password: string
  role: UserRole
}

const initialFormData: UserFormData = {
  username: '',
  email: '',
  password: '',
  role: 'viewer',
}

export function Users() {
  const { data: response, isLoading } = useUsers()
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()
  const deleteUser = useDeleteUser()
  const changePassword = useChangePassword()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [deletingUser, setDeletingUser] = useState<User | null>(null)
  const [passwordUser, setPasswordUser] = useState<User | null>(null)
  const [formData, setFormData] = useState<UserFormData>(initialFormData)
  const [newPassword, setNewPassword] = useState('')

  const users = response?.data ?? []

  const handleCreate = () => {
    const data: UserCreate = {
      username: formData.username,
      password: formData.password,
      role: formData.role,
    }
    if (formData.email) data.email = formData.email

    createUser.mutate(data, {
      onSuccess: () => {
        setIsCreateOpen(false)
        setFormData(initialFormData)
      },
    })
  }

  const handleUpdate = () => {
    if (!editingUser) return
    updateUser.mutate(
      {
        id: editingUser.id,
        data: {
          email: formData.email || null,
          role: formData.role,
        },
      },
      {
        onSuccess: () => {
          setEditingUser(null)
          setFormData(initialFormData)
        },
      }
    )
  }

  const handleDelete = () => {
    if (!deletingUser) return
    deleteUser.mutate(deletingUser.id, {
      onSuccess: () => setDeletingUser(null),
    })
  }

  const handlePasswordChange = () => {
    if (!passwordUser || !newPassword) return
    changePassword.mutate(
      { id: passwordUser.id, data: { new_password: newPassword } },
      {
        onSuccess: () => {
          setPasswordUser(null)
          setNewPassword('')
        },
      }
    )
  }

  const toggleUserStatus = (user: User) => {
    updateUser.mutate({
      id: user.id,
      data: { is_active: !user.is_active },
    })
  }

  const openEdit = (user: User) => {
    setFormData({
      username: user.username,
      email: user.email || '',
      password: '',
      role: user.role,
    })
    setEditingUser(user)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Users</h2>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add User
        </Button>
      </div>

      <p className="text-muted-foreground">
        Manage user accounts and their roles. Roles determine what actions users can perform.
      </p>

      {/* Role explanations */}
      <div className="grid gap-4 md:grid-cols-4">
        {ROLES.map((role) => (
          <Card key={role} className="bg-muted/50">
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 mb-1">
                <Shield className="h-4 w-4" />
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS[role]}`}>
                  {ROLE_LABELS[role]}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[role]}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading users...</div>
      ) : users.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <UsersIcon className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No users found.</p>
              <p className="text-sm mt-1">Create a user to get started.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>All Users ({users.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {users.map((user) => (
                <div
                  key={user.id}
                  className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        user.is_active ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      <UsersIcon className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{user.username}</span>
                        <Badge
                          variant={user.is_active ? 'default' : 'secondary'}
                          className={user.is_active ? 'bg-green-100 text-green-800' : ''}
                        >
                          {user.is_active ? 'Active' : 'Disabled'}
                        </Badge>
                        <span className={`px-2 py-0.5 rounded text-xs ${ROLE_COLORS[user.role]}`}>
                          {ROLE_LABELS[user.role]}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {user.email || 'No email'} &middot; Last login: {formatDate(user.last_login_at)}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setPasswordUser(user)}
                      title="Change password"
                    >
                      <Key className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => toggleUserStatus(user)}
                      title={user.is_active ? 'Disable user' : 'Enable user'}
                    >
                      {user.is_active ? (
                        <UserX className="h-4 w-4" />
                      ) : (
                        <UserCheck className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => openEdit(user)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => setDeletingUser(user)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Create User</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username <span className="text-destructive">*</span></Label>
              <Input
                id="username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                placeholder="johndoe"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="john@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password <span className="text-destructive">*</span></Label>
              <Input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="Min 8 characters"
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select
                value={formData.role}
                onValueChange={(v) => setFormData({ ...formData, role: v as UserRole })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!formData.username || !formData.password || createUser.isPending}
            >
              {createUser.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingUser} onOpenChange={(open) => !open && setEditingUser(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Edit User: {editingUser?.username}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-email">Email</Label>
              <Input
                id="edit-email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select
                value={formData.role}
                onValueChange={(v) => setFormData({ ...formData, role: v as UserRole })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingUser(null)}>
              Cancel
            </Button>
            <Button onClick={handleUpdate} disabled={updateUser.isPending}>
              {updateUser.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingUser} onOpenChange={(open) => !open && setDeletingUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete User</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete user <strong>{deletingUser?.username}</strong>?
            This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingUser(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteUser.isPending}
            >
              {deleteUser.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change Password Dialog */}
      <Dialog open={!!passwordUser} onOpenChange={(open) => !open && setPasswordUser(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Change Password: {passwordUser?.username}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Min 8 characters"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordUser(null)}>
              Cancel
            </Button>
            <Button
              onClick={handlePasswordChange}
              disabled={!newPassword || newPassword.length < 8 || changePassword.isPending}
            >
              {changePassword.isPending ? 'Changing...' : 'Change Password'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
