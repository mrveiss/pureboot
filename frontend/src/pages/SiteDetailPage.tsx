import { useParams, Link } from 'react-router-dom'
import { useState } from 'react'
import {
  ArrowLeft,
  Globe,
  Users,
  Wifi,
  AlertTriangle,
  Key,
  RefreshCw,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui'
import { SiteStatusBadge, AgentCard } from '@/components/sites'
import { NodeTable } from '@/components/nodes/NodeTable'
import { ConflictResolutionPage } from './ConflictResolutionPage'
import {
  useSite,
  useSiteNodes,
  useSiteHealth,
  useSiteConflicts,
  useGenerateAgentToken,
  useTriggerSiteSync,
} from '@/hooks'

export function SiteDetailPage() {
  const { groupId } = useParams<{ groupId: string }>()
  const siteId = groupId ?? ''

  const { data: siteResponse, isLoading: siteLoading } = useSite(siteId)
  const { data: nodesResponse, isLoading: nodesLoading } = useSiteNodes(siteId)
  const { data: healthResponse } = useSiteHealth(siteId)
  const { data: conflictsResponse } = useSiteConflicts(siteId)

  const generateToken = useGenerateAgentToken()
  const triggerSync = useTriggerSiteSync()

  const [tokenDialogOpen, setTokenDialogOpen] = useState(false)
  const [generatedToken, setGeneratedToken] = useState<string | null>(null)

  if (siteLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading site details...</div>
      </div>
    )
  }

  const site = siteResponse?.data
  const nodes = nodesResponse?.data ?? []
  const health = healthResponse?.data ?? null
  const conflictCount = conflictsResponse?.data?.length ?? 0

  if (!site) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/groups?tab=sites">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Sites
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">Site not found</div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const handleGenerateToken = () => {
    generateToken.mutate(siteId, {
      onSuccess: (response) => {
        setGeneratedToken(response.data.token)
        setTokenDialogOpen(true)
      },
    })
  }

  const handleSync = () => {
    triggerSync.mutate({ siteId })
  }

  const copyToken = () => {
    if (generatedToken) {
      navigator.clipboard.writeText(generatedToken)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/groups?tab=sites">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <Globe className="h-6 w-6" />
              {site.name}
            </h2>
            <p className="text-muted-foreground">
              {site.description || 'No description'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SiteStatusBadge site={site} />
          <Button variant="outline" size="sm" onClick={handleSync} disabled={triggerSync.isPending}>
            <RefreshCw className={triggerSync.isPending ? 'mr-2 h-4 w-4 animate-spin' : 'mr-2 h-4 w-4'} />
            Sync
          </Button>
          <Button variant="outline" size="sm" onClick={handleGenerateToken} disabled={generateToken.isPending}>
            <Key className="mr-2 h-4 w-4" />
            Generate Token
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Nodes</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{site.node_count}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Agent Status</CardTitle>
            <Wifi className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">
              {site.agent_status ?? 'Unknown'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conflicts</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{conflictCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Children</CardTitle>
            <Globe className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{site.children_count}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="nodes">
        <TabsList>
          <TabsTrigger value="nodes">Nodes</TabsTrigger>
          <TabsTrigger value="agent">
            Agent
          </TabsTrigger>
          <TabsTrigger value="conflicts">
            Conflicts
            {conflictCount > 0 && (
              <Badge variant="destructive" className="ml-1.5 h-5 min-w-5 px-1.5 text-xs">
                {conflictCount}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="nodes">
          <Card>
            <CardHeader>
              <CardTitle>Nodes at this Site</CardTitle>
            </CardHeader>
            <CardContent>
              <NodeTable
                nodes={nodes}
                isLoading={nodesLoading}
                enableSelection={true}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="agent">
          <AgentCard site={site} health={health} />
        </TabsContent>

        <TabsContent value="conflicts">
          <ConflictResolutionPage siteId={siteId} />
        </TabsContent>
      </Tabs>

      {/* Token Dialog */}
      <Dialog open={tokenDialogOpen} onOpenChange={setTokenDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agent Registration Token</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <p className="text-sm text-muted-foreground">
              Save this token now. It will not be shown again.
            </p>
            <div className="p-3 bg-muted rounded-md font-mono text-sm break-all">
              {generatedToken}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTokenDialogOpen(false)}>
              Close
            </Button>
            <Button onClick={copyToken}>
              Copy Token
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
