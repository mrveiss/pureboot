import { useState, useEffect } from 'react'
import { Plus, Key, User, Clock } from 'lucide-react'
import { Button, Card, CardContent } from '@/components/ui'
import { serviceAccountsApi } from '@/api/serviceAccounts'
import type { ServiceAccount } from '@/types'

export function ServiceAccounts() {
  const [accounts, setAccounts] = useState<ServiceAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAccounts()
  }, [])

  const loadAccounts = async () => {
    try {
      setLoading(true)
      const data = await serviceAccountsApi.list()
      setAccounts(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load service accounts')
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
          <h1 className="text-2xl font-bold">Service Accounts</h1>
          <p className="text-muted-foreground">
            Manage machine identities for API access
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Service Account
        </Button>
      </div>

      <div className="grid gap-4">
        {accounts.map((account) => (
          <Card key={account.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{account.username}</h3>
                    <p className="text-sm text-muted-foreground">
                      {account.description || 'No description'}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-sm">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        account.is_active
                          ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                          : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                      }`}>
                        {account.is_active ? 'Active' : 'Disabled'}
                      </span>
                      {account.role && (
                        <span className="text-muted-foreground">
                          Role: {account.role}
                        </span>
                      )}
                      {account.owner_username && (
                        <span className="text-muted-foreground">
                          Owner: {account.owner_username}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-sm">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <span>{account.api_key_count} API keys</span>
                    </div>
                    {account.expires_at && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                        <Clock className="h-3 w-3" />
                        <span>Expires: {new Date(account.expires_at).toLocaleDateString()}</span>
                      </div>
                    )}
                  </div>
                  <Button variant="outline" size="sm">
                    Manage Keys
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {accounts.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No service accounts found. Create one for API access.
        </div>
      )}
    </div>
  )
}

export default ServiceAccounts
