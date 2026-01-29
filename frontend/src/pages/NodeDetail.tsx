import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Server, Clock, Cpu, Network, Tag, Workflow, X, Play, RotateCcw, HardDrive, AlertTriangle, Power, RefreshCw } from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Separator,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { StateMachine } from '@/components/nodes/StateMachine'
import { useNode, useUpdateNodeState, useUpdateNode, useWorkflows, useSendNodeCommand } from '@/hooks'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, NODE_STATE_TRANSITIONS, ARCHITECTURE_LABELS, BOOT_MODE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleString()
}

export function NodeDetail() {
  const { nodeId } = useParams<{ nodeId: string }>()
  const { data: response, isLoading, error } = useNode(nodeId ?? '')
  const updateState = useUpdateNodeState()
  const updateNode = useUpdateNode()
  const sendCommand = useSendNodeCommand()
  const { data: workflowsResponse } = useWorkflows()

  const [workflowDialogOpen, setWorkflowDialogOpen] = useState(false)
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>('')
  const [forceStateDialogOpen, setForceStateDialogOpen] = useState(false)
  const [selectedForceState, setSelectedForceState] = useState<string>('')
  const [commandDialogOpen, setCommandDialogOpen] = useState(false)
  const [pendingCommand, setPendingCommand] = useState<'poweroff' | 'reboot' | null>(null)

  const workflows = workflowsResponse?.data ?? []
  const allStates: NodeState[] = [
    'discovered', 'ignored', 'pending', 'installing', 'install_failed', 'installed',
    'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping'
  ]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading node details...</div>
      </div>
    )
  }

  if (error || !response?.data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/nodes">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Nodes
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">
              {error instanceof Error ? error.message : 'Node not found'}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const node = response.data
  const validTransitions = NODE_STATE_TRANSITIONS[node.state] ?? []

  const handleStateTransition = (newState: NodeState) => {
    if (!validTransitions.includes(newState)) return

    // For wiping, would need confirmation dialog - simplified for now
    if (newState === 'wiping') {
      if (!confirm('This will securely erase all data on this node. Are you sure?')) {
        return
      }
    }

    updateState.mutate({ nodeId: node.id, newState })
  }

  const handleAssignWorkflow = () => {
    const workflowId = selectedWorkflow === 'none' ? null : selectedWorkflow
    updateNode.mutate(
      { nodeId: node.id, data: { workflow_id: workflowId } },
      {
        onSuccess: () => {
          setWorkflowDialogOpen(false)
          setSelectedWorkflow('')
        },
      }
    )
  }

  const handleClearWorkflow = () => {
    updateNode.mutate({ nodeId: node.id, data: { workflow_id: null } })
  }

  const openWorkflowDialog = () => {
    setSelectedWorkflow(node.workflow_id || 'none')
    setWorkflowDialogOpen(true)
  }

  const handleForceState = () => {
    if (!selectedForceState) return
    updateState.mutate(
      { nodeId: node.id, newState: selectedForceState as NodeState, force: true },
      {
        onSuccess: () => {
          setForceStateDialogOpen(false)
          setSelectedForceState('')
        },
      }
    )
  }

  const handleSendCommand = (command: 'poweroff' | 'reboot') => {
    setPendingCommand(command)
    setCommandDialogOpen(true)
  }

  const confirmCommand = () => {
    if (!pendingCommand) return
    sendCommand.mutate(
      { nodeId: node.id, command: pendingCommand },
      {
        onSuccess: () => {
          setCommandDialogOpen(false)
          setPendingCommand(null)
        },
      }
    )
  }

  const handleRescan = () => {
    sendCommand.mutate({ nodeId: node.id, command: 'rescan' })
  }

  const currentWorkflow = workflows.find((w) => w.id === node.workflow_id)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/nodes">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold">
              {node.hostname || node.mac_address}
            </h2>
            <p className="text-muted-foreground">
              {node.hostname ? node.mac_address : 'Hostname not assigned'}
            </p>
          </div>
        </div>
        <Badge
          variant="outline"
          className={cn('text-lg px-4 py-1 border-0 text-white', NODE_STATE_COLORS[node.state])}
        >
          {NODE_STATE_LABELS[node.state]}
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column - Node info */}
        <div className="space-y-6">
          {/* Basic Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Node Information
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Hostname</div>
                  <div className="font-medium">{node.hostname || 'Not assigned'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">IP Address</div>
                  <div className="font-medium font-mono">{node.ip_address || 'N/A'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">MAC Address</div>
                  <div className="font-medium font-mono">{node.mac_address}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">System UUID</div>
                  <div className="font-medium font-mono text-xs">{node.system_uuid || 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Hardware Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5" />
                Hardware
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Architecture</div>
                  <div className="font-medium">{node.arch}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Boot Mode</div>
                  <div className="font-medium uppercase">{node.boot_mode}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Vendor</div>
                  <div className="font-medium">{node.vendor || 'Unknown'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Model</div>
                  <div className="font-medium">{node.model || 'Unknown'}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-muted-foreground">Serial Number</div>
                  <div className="font-medium font-mono">{node.serial_number || 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Timestamps */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">First Discovered</div>
                  <div className="font-medium">{formatDate(node.created_at)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Last Updated</div>
                  <div className="font-medium">{formatDate(node.updated_at)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Last Seen</div>
                  <div className="font-medium">{formatDate(node.last_seen_at)}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tags */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Tag className="h-5 w-5" />
                Tags
              </CardTitle>
            </CardHeader>
            <CardContent>
              {node.tags.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {node.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">{tag}</Badge>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">No tags assigned</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column - State machine */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Network className="h-5 w-5" />
                State Machine
              </CardTitle>
            </CardHeader>
            <CardContent>
              <StateMachine
                currentState={node.state}
                onStateClick={handleStateTransition}
                highlightTransitions={true}
              />

              <Separator className="my-4" />

              <div className="space-y-2">
                <div className="text-sm font-medium">Available Transitions</div>
                {validTransitions.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {validTransitions.map((state) => (
                      <Button
                        key={state}
                        variant="outline"
                        size="sm"
                        onClick={() => handleStateTransition(state)}
                        disabled={updateState.isPending}
                        className={cn(
                          'hover:text-white',
                          `hover:${NODE_STATE_COLORS[state]}`
                        )}
                      >
                        Transition to {NODE_STATE_LABELS[state]}
                      </Button>
                    ))}
                  </div>
                ) : (
                  <div className="text-muted-foreground text-sm">
                    No transitions available from this state
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          {(node.state === 'discovered' || node.state === 'pending' || node.state === 'installing' || node.state === 'installed') && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Play className="h-5 w-5" />
                  Quick Actions
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Discovered state: Approve for provisioning */}
                {node.state === 'discovered' && (
                  <div className="space-y-2">
                    <Button
                      className="w-full"
                      onClick={() => handleStateTransition('pending')}
                      disabled={updateState.isPending || !node.workflow_id}
                    >
                      <Play className="mr-2 h-4 w-4" />
                      Approve for Provisioning
                    </Button>
                    {!node.workflow_id && (
                      <p className="text-xs text-muted-foreground">
                        Assign a workflow first to approve this node for provisioning
                      </p>
                    )}
                  </div>
                )}

                {/* Pending state: Ready to boot */}
                {node.state === 'pending' && (
                  <div className="rounded-lg border p-3 bg-muted/50">
                    <div className="flex items-center gap-2 text-sm">
                      <div className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
                      <span>Waiting for node to PXE boot</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      The node will automatically transition to &apos;Installing&apos; when it boots from the network
                    </p>
                  </div>
                )}

                {/* Installing state: Progress indicator */}
                {node.state === 'installing' && (
                  <div className="space-y-3">
                    <div className="rounded-lg border p-3 bg-muted/50">
                      <div className="flex items-center gap-2 text-sm">
                        <div className="h-2 w-2 rounded-full bg-orange-500 animate-pulse" />
                        <span>Installation in progress</span>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => handleStateTransition('pending')}
                      disabled={updateState.isPending}
                    >
                      <RotateCcw className="mr-2 h-4 w-4" />
                      Retry Installation
                    </Button>
                  </div>
                )}

                {/* Installed state: Activate */}
                {node.state === 'installed' && (
                  <div className="space-y-2">
                    <div className="rounded-lg border p-3 bg-muted/50">
                      <div className="flex items-center gap-2 text-sm">
                        <div className="h-2 w-2 rounded-full bg-teal-500" />
                        <span>Installation complete</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        Waiting for first boot from local disk
                      </p>
                    </div>
                    <Button
                      className="w-full"
                      onClick={() => handleStateTransition('active')}
                      disabled={updateState.isPending}
                    >
                      <Play className="mr-2 h-4 w-4" />
                      Mark as Active
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Disk Management - available when node is in deploy environment */}
          {(node.state === 'pending' || node.state === 'installing') && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HardDrive className="h-5 w-5" />
                  Disk Management
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">
                  Manage disk partitions while the node is booted into the deploy environment.
                </p>
                <Button variant="outline" className="w-full" asChild>
                  <Link to={`/nodes/${node.id}/partitions`}>
                    <HardDrive className="mr-2 h-4 w-4" />
                    Open Partition Manager
                  </Link>
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Node Control - available when node is polling (pending/installing state) */}
          {(node.state === 'pending' || node.state === 'installing') && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Power className="h-5 w-5" />
                  Node Control
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Control the node while it is booted into the deploy environment.
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <Button
                    variant="outline"
                    onClick={handleRescan}
                    disabled={sendCommand.isPending}
                  >
                    <RefreshCw className={cn("mr-2 h-4 w-4", sendCommand.isPending && "animate-spin")} />
                    Scan
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleSendCommand('reboot')}
                    disabled={sendCommand.isPending}
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Reboot
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleSendCommand('poweroff')}
                    disabled={sendCommand.isPending}
                    className="text-destructive hover:text-destructive"
                  >
                    <Power className="mr-2 h-4 w-4" />
                    Off
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Admin Override - Force State */}
          <Card className="border-amber-500/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-500">
                <AlertTriangle className="h-5 w-5" />
                Admin Override
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Force state changes bypass the state machine validation. Use with caution.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setSelectedForceState('')
                    setForceStateDialogOpen(true)
                  }}
                >
                  Force State Change
                </Button>
                {node.state !== 'discovered' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedForceState('discovered')
                      setForceStateDialogOpen(true)
                    }}
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Reset to Discovered
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Workflow assignment */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-5 w-5" />
                Workflow
              </CardTitle>
            </CardHeader>
            <CardContent>
              {currentWorkflow ? (
                <div className="space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium">{currentWorkflow.name}</div>
                      <code className="text-xs text-muted-foreground">{currentWorkflow.id}</code>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                      onClick={handleClearWorkflow}
                      disabled={updateNode.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex gap-2 text-xs">
                    <Badge variant="secondary">
                      {ARCHITECTURE_LABELS[currentWorkflow.architecture] || currentWorkflow.architecture}
                    </Badge>
                    <Badge variant="outline">
                      {BOOT_MODE_LABELS[currentWorkflow.boot_mode] || currentWorkflow.boot_mode}
                    </Badge>
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">
                  No workflow assigned
                </div>
              )}
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={openWorkflowDialog}
              >
                {currentWorkflow ? 'Change Workflow' : 'Assign Workflow'}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Workflow Assignment Dialog */}
      <Dialog open={workflowDialogOpen} onOpenChange={setWorkflowDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign Workflow</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            {workflows.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No workflows available. Add workflow YAML files to the workflows directory.
              </p>
            ) : (
              <Select value={selectedWorkflow} onValueChange={setSelectedWorkflow}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a workflow..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No Workflow</SelectItem>
                  {workflows.map((workflow) => (
                    <SelectItem key={workflow.id} value={workflow.id}>
                      <div className="flex items-center gap-2">
                        <span>{workflow.name}</span>
                        <span className="text-xs text-muted-foreground">
                          ({workflow.architecture}/{workflow.boot_mode})
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWorkflowDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAssignWorkflow}
              disabled={!selectedWorkflow || updateNode.isPending || workflows.length === 0}
            >
              {updateNode.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Force State Dialog */}
      <Dialog open={forceStateDialogOpen} onOpenChange={setForceStateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-500">
              <AlertTriangle className="h-5 w-5" />
              Force State Change
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-3">
              <p className="text-sm text-amber-200">
                This will bypass state machine validation and force the node to the selected state.
                Install attempts and error counters will be reset.
              </p>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Select Target State</label>
              <Select value={selectedForceState} onValueChange={setSelectedForceState}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a state..." />
                </SelectTrigger>
                <SelectContent>
                  {allStates.filter((state) => state !== node.state).map((state) => (
                    <SelectItem key={state} value={state}>
                      <div className="flex items-center gap-2">
                        <div className={cn('h-2 w-2 rounded-full', NODE_STATE_COLORS[state])} />
                        <span>{NODE_STATE_LABELS[state]}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setForceStateDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleForceState}
              disabled={!selectedForceState || selectedForceState === node.state || updateState.isPending}
            >
              {updateState.isPending ? 'Forcing...' : 'Force Change'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Node Command Confirmation Dialog */}
      <Dialog open={commandDialogOpen} onOpenChange={setCommandDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {pendingCommand === 'poweroff' ? (
                <Power className="h-5 w-5 text-destructive" />
              ) : (
                <RotateCcw className="h-5 w-5" />
              )}
              Confirm {pendingCommand === 'poweroff' ? 'Power Off' : 'Reboot'}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground">
              {pendingCommand === 'poweroff' ? (
                <>Are you sure you want to power off this node? You will need physical access or remote management to power it back on.</>
              ) : (
                <>Are you sure you want to reboot this node? It will boot back into the deploy environment.</>
              )}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCommandDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant={pendingCommand === 'poweroff' ? 'destructive' : 'default'}
              onClick={confirmCommand}
              disabled={sendCommand.isPending}
            >
              {sendCommand.isPending ? 'Sending...' : (pendingCommand === 'poweroff' ? 'Power Off' : 'Reboot')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
