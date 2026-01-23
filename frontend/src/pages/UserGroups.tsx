import { useState, useEffect } from 'react'
import { Plus, Users, Shield, Pencil, Trash2 } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { userGroupsApi } from '@/api/userGroups'
import type { UserGroup } from '@/types'

export function UserGroups() {
  const [groups, setGroups] = useState<UserGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      setLoading(true)
      const data = await userGroupsApi.list()
      setGroups(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load user groups')
    } finally {
      setLoading(false)
    }
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
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">User Groups</h1>
          <p className="text-muted-foreground">
            Manage team-based access control and permissions
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Group
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {groups.map((group) => (
          <Card key={group.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <CardTitle className="text-lg">{group.name}</CardTitle>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                {group.description || 'No description'}
              </p>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  <span>{group.member_count} members</span>
                </div>
                <div className="flex items-center gap-1">
                  <Shield className="h-4 w-4 text-muted-foreground" />
                  <span>{group.role_names.length} roles</span>
                </div>
              </div>
              {group.requires_approval && (
                <div className="mt-2">
                  <span className="text-xs px-2 py-1 rounded bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200">
                    Requires Approval
                  </span>
                </div>
              )}
              {group.role_names.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {group.role_names.map((role) => (
                    <span
                      key={role}
                      className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary"
                    >
                      {role}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {groups.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No user groups found. Create one to get started.
        </div>
      )}
    </div>
  )
}

export default UserGroups
