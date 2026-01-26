import { useState, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Copy,
  Server,
  HardDrive,
  Database,
  AlertTriangle,
  Check,
  Loader2,
} from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useNodes, useStorageBackends, useCreateCloneSession } from '@/hooks'
import type { CloneMode, ResizeMode } from '@/types/clone'
import type { StorageBackend } from '@/types/storage'
import { cn } from '@/lib/utils'

/**
 * Clone Mode option card component
 */
function CloneModeCard({
  mode,
  title,
  description,
  icon: Icon,
  selected,
  onSelect,
}: {
  mode: CloneMode
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  selected: boolean
  onSelect: () => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => e.key === 'Enter' && onSelect()}
      className={cn(
        'relative flex flex-col p-4 rounded-lg border-2 cursor-pointer transition-all',
        'hover:border-primary/50',
        selected
          ? 'border-primary bg-primary/5'
          : 'border-muted hover:bg-muted/50'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'p-2 rounded-md',
            selected ? 'bg-primary text-primary-foreground' : 'bg-muted'
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <h4 className="font-medium">{title}</h4>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
        {selected && (
          <div className="absolute top-2 right-2">
            <Check className="h-4 w-4 text-primary" />
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Clone Wizard page for creating new clone sessions
 */
export function CloneWizard() {
  const navigate = useNavigate()

  // Form state
  const [name, setName] = useState('')
  const [sourceNodeId, setSourceNodeId] = useState('')
  const [targetNodeId, setTargetNodeId] = useState('')
  const [sourceDevice, setSourceDevice] = useState('/dev/sda')
  const [targetDevice, setTargetDevice] = useState('/dev/sda')
  const [cloneMode, setCloneMode] = useState<CloneMode>('direct')
  const [stagingBackendId, setStagingBackendId] = useState('')
  const [resizeMode, setResizeMode] = useState<ResizeMode>('none')

  // Fetch nodes and storage backends
  const { data: nodesResponse, isLoading: nodesLoading } = useNodes()
  const { data: backendsResponse, isLoading: backendsLoading } = useStorageBackends()
  const createSession = useCreateCloneSession()

  const nodes = nodesResponse?.data ?? []
  const storageBackends = backendsResponse?.data ?? []

  // Filter storage backends to only show NFS and iSCSI (suitable for staging)
  const stagingBackends = useMemo(() => {
    return storageBackends.filter(
      (backend: StorageBackend) => backend.type === 'nfs' || backend.type === 'iscsi'
    )
  }, [storageBackends])

  // Get selected nodes for display
  const selectedSourceNode = nodes.find((n) => n.id === sourceNodeId)
  const selectedTargetNode = nodes.find((n) => n.id === targetNodeId)

  // Check if source and target are the same
  const isSameNode = sourceNodeId && targetNodeId && sourceNodeId === targetNodeId

  // Validation
  const isValid = useMemo(() => {
    if (!sourceNodeId) return false
    if (isSameNode) return false
    if (cloneMode === 'staged' && !stagingBackendId) return false
    return true
  }, [sourceNodeId, isSameNode, cloneMode, stagingBackendId])

  // Handle form submission
  const handleSubmit = async () => {
    if (!isValid) return

    try {
      const sessionData = {
        name: name || undefined,
        source_node_id: sourceNodeId,
        target_node_id: targetNodeId || undefined,
        source_device: sourceDevice,
        target_device: targetDevice,
        clone_mode: cloneMode,
        staging_backend_id: cloneMode === 'staged' ? stagingBackendId : undefined,
        resize_mode: resizeMode,
      }

      const response = await createSession.mutateAsync(sessionData)
      if (response?.data?.id) {
        navigate(`/clone/${response.data.id}`)
      } else {
        navigate('/clone')
      }
    } catch (error) {
      console.error('Failed to create clone session:', error)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" asChild>
          <Link to="/clone">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Link>
        </Button>
        <div>
          <h2 className="text-2xl font-bold">Create Clone Session</h2>
          <p className="text-muted-foreground">
            Clone a disk from one node to another
          </p>
        </div>
      </div>

      {/* Session Name */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Copy className="h-5 w-5" />
            Session Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <Label htmlFor="name">Session Name (optional)</Label>
              <Input
                id="name"
                placeholder="e.g., Clone web-server-01 to web-server-02"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1.5"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Clone Mode Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Clone Mode
          </CardTitle>
          <CardDescription>
            Choose how the disk data will be transferred
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <CloneModeCard
              mode="direct"
              title="Direct Clone"
              description="Transfer data directly from source to target over the network. Both nodes must be online simultaneously."
              icon={Server}
              selected={cloneMode === 'direct'}
              onSelect={() => {
                setCloneMode('direct')
                setStagingBackendId('')
              }}
            />
            <CloneModeCard
              mode="staged"
              title="Staged Clone"
              description="Upload disk image to storage backend first, then download to target. Nodes can be cloned at different times."
              icon={Database}
              selected={cloneMode === 'staged'}
              onSelect={() => setCloneMode('staged')}
            />
          </div>

          {/* Staging Backend Selection (only for staged mode) */}
          {cloneMode === 'staged' && (
            <div className="mt-6 p-4 bg-muted/50 rounded-lg border">
              <Label htmlFor="staging-backend">Staging Storage Backend</Label>
              <p className="text-sm text-muted-foreground mb-3">
                Select where the disk image will be stored during the clone process
              </p>
              {backendsLoading ? (
                <div className="text-sm text-muted-foreground">
                  Loading storage backends...
                </div>
              ) : stagingBackends.length === 0 ? (
                <div className="flex items-start gap-2 text-sm text-yellow-600 bg-yellow-500/10 p-3 rounded-md">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    No suitable storage backends available. Staged cloning requires
                    an NFS or iSCSI storage backend.{' '}
                    <Link to="/storage" className="underline">
                      Configure storage
                    </Link>
                  </div>
                </div>
              ) : (
                <Select
                  value={stagingBackendId}
                  onValueChange={setStagingBackendId}
                >
                  <SelectTrigger id="staging-backend" className="mt-1.5">
                    <SelectValue placeholder="Select storage backend" />
                  </SelectTrigger>
                  <SelectContent>
                    {stagingBackends.map((backend: StorageBackend) => (
                      <SelectItem key={backend.id} value={backend.id}>
                        <div className="flex items-center gap-2">
                          <span>{backend.name}</span>
                          <span className="text-xs text-muted-foreground uppercase">
                            ({backend.type})
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Source and Target Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Source and Target
          </CardTitle>
          <CardDescription>
            Select the nodes and devices for cloning
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 md:grid-cols-2">
            {/* Source Node */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="source-node">Source Node *</Label>
                <p className="text-sm text-muted-foreground mb-2">
                  The node to clone from
                </p>
                {nodesLoading ? (
                  <div className="text-sm text-muted-foreground">
                    Loading nodes...
                  </div>
                ) : (
                  <Select value={sourceNodeId} onValueChange={setSourceNodeId}>
                    <SelectTrigger id="source-node">
                      <SelectValue placeholder="Select source node" />
                    </SelectTrigger>
                    <SelectContent>
                      {nodes.map((node) => (
                        <SelectItem key={node.id} value={node.id}>
                          {node.hostname || node.mac_address}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {selectedSourceNode && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    MAC: {selectedSourceNode.mac_address}
                    {selectedSourceNode.ip_address && ` | IP: ${selectedSourceNode.ip_address}`}
                  </div>
                )}
              </div>
              <div>
                <Label htmlFor="source-device">
                  <HardDrive className="h-3 w-3 inline mr-1" />
                  Source Device
                </Label>
                <Input
                  id="source-device"
                  value={sourceDevice}
                  onChange={(e) => setSourceDevice(e.target.value)}
                  placeholder="/dev/sda"
                  className="mt-1.5 font-mono"
                />
              </div>
            </div>

            {/* Target Node */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="target-node">
                  Target Node {cloneMode === 'direct' && '(optional)'}
                </Label>
                <p className="text-sm text-muted-foreground mb-2">
                  The node to clone to
                </p>
                {nodesLoading ? (
                  <div className="text-sm text-muted-foreground">
                    Loading nodes...
                  </div>
                ) : (
                  <Select value={targetNodeId} onValueChange={setTargetNodeId}>
                    <SelectTrigger id="target-node">
                      <SelectValue placeholder="Select target node (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">
                        <span className="text-muted-foreground">
                          Assign later
                        </span>
                      </SelectItem>
                      {nodes
                        .filter((n) => n.id !== sourceNodeId)
                        .map((node) => (
                          <SelectItem key={node.id} value={node.id}>
                            {node.hostname || node.mac_address}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                )}
                {selectedTargetNode && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    MAC: {selectedTargetNode.mac_address}
                    {selectedTargetNode.ip_address && ` | IP: ${selectedTargetNode.ip_address}`}
                  </div>
                )}
              </div>
              <div>
                <Label htmlFor="target-device">
                  <HardDrive className="h-3 w-3 inline mr-1" />
                  Target Device
                </Label>
                <Input
                  id="target-device"
                  value={targetDevice}
                  onChange={(e) => setTargetDevice(e.target.value)}
                  placeholder="/dev/sda"
                  className="mt-1.5 font-mono"
                />
              </div>
            </div>
          </div>

          {/* Warning for same node */}
          {isSameNode && (
            <div className="mt-4 flex items-start gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>Source and target cannot be the same node</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resize Mode */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Resize Options
          </CardTitle>
          <CardDescription>
            Handle disk size differences between source and target
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div>
            <Label htmlFor="resize-mode">Resize Mode</Label>
            <Select
              value={resizeMode}
              onValueChange={(v) => setResizeMode(v as ResizeMode)}
            >
              <SelectTrigger id="resize-mode" className="mt-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">
                  <div>
                    <div>None</div>
                    <div className="text-xs text-muted-foreground">
                      Keep partitions as-is (source and target must be same size)
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="shrink_source">
                  <div>
                    <div>Shrink Source</div>
                    <div className="text-xs text-muted-foreground">
                      Shrink source partitions to fit smaller target disk
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="grow_target">
                  <div>
                    <div>Grow Target</div>
                    <div className="text-xs text-muted-foreground">
                      Expand partitions to fill larger target disk
                    </div>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {resizeMode !== 'none' && (
            <div className="mt-4 flex items-start gap-2 text-sm text-yellow-600 bg-yellow-500/10 p-3 rounded-md">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                {resizeMode === 'shrink_source'
                  ? 'Shrinking partitions may cause data loss if the source disk has more data than the target can hold.'
                  : 'Growing partitions will be performed after the clone completes on the target node.'}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Submit */}
      <div className="flex items-center justify-end gap-4">
        <Button variant="outline" asChild>
          <Link to="/clone">Cancel</Link>
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!isValid || createSession.isPending}
        >
          {createSession.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating...
            </>
          ) : (
            <>
              <Copy className="mr-2 h-4 w-4" />
              Create Clone Session
            </>
          )}
        </Button>
      </div>

      {/* Error message */}
      {createSession.isError && (
        <div className="flex items-start gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-md">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            {createSession.error instanceof Error
              ? createSession.error.message
              : 'Failed to create clone session'}
          </span>
        </div>
      )}
    </div>
  )
}
