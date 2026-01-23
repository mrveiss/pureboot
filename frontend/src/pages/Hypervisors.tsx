import { useState } from 'react'
import {
  Server,
  Plus,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertCircle,
  Trash2,
  Play,
  Monitor,
  Cpu,
  HardDrive,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Badge,
  Button,
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
import { cn } from '@/lib/utils'
import {
  useHypervisors,
  useCreateHypervisor,
  useDeleteHypervisor,
  useTestHypervisor,
  useHypervisorVMs,
} from '@/hooks/useHypervisors'
import {
  HYPERVISOR_TYPE_LABELS,
  HYPERVISOR_STATUS_COLORS,
  type Hypervisor,
  type HypervisorCreate,
} from '@/types'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleString()
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'online':
      return <CheckCircle className="h-4 w-4 text-green-500" />
    case 'error':
      return <XCircle className="h-4 w-4 text-red-500" />
    case 'offline':
      return <AlertCircle className="h-4 w-4 text-gray-500" />
    default:
      return <AlertCircle className="h-4 w-4 text-yellow-500" />
  }
}

function HypervisorCard({
  hypervisor,
  onTest,
  onDelete,
  onViewVMs,
  isTestPending,
}: {
  hypervisor: Hypervisor
  onTest: () => void
  onDelete: () => void
  onViewVMs: () => void
  isTestPending: boolean
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Server className="h-5 w-5" />
            {hypervisor.name}
          </CardTitle>
          <div className="flex items-center gap-2">
            <StatusIcon status={hypervisor.status} />
            <Badge
              variant="outline"
              className={cn('border-0 text-white', HYPERVISOR_STATUS_COLORS[hypervisor.status])}
            >
              {hypervisor.status}
            </Badge>
          </div>
        </div>
        <CardDescription>
          {HYPERVISOR_TYPE_LABELS[hypervisor.type] || hypervisor.type}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">API URL</span>
            <span className="font-mono text-xs truncate max-w-[200px]" title={hypervisor.api_url}>
              {hypervisor.api_url}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Username</span>
            <span>{hypervisor.username || '-'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">VMs</span>
            <span className="font-medium">{hypervisor.vm_count}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Hosts</span>
            <span className="font-medium">{hypervisor.host_count}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Last Sync</span>
            <span className="text-xs">{formatDate(hypervisor.last_sync_at)}</span>
          </div>
        </div>

        {hypervisor.last_error && (
          <div className="rounded-lg bg-destructive/10 p-2 text-xs text-destructive">
            {hypervisor.last_error}
          </div>
        )}

        <div className="flex gap-2 pt-2 border-t">
          <Button
            variant="outline"
            size="sm"
            onClick={onTest}
            disabled={isTestPending}
            className="flex-1"
          >
            {isTestPending ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Test
          </Button>
          <Button variant="outline" size="sm" onClick={onViewVMs} className="flex-1">
            <Monitor className="h-4 w-4 mr-2" />
            VMs
          </Button>
          <Button variant="ghost" size="icon" onClick={onDelete} className="text-destructive">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function AddHypervisorDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [formData, setFormData] = useState<HypervisorCreate>({
    name: '',
    type: 'ovirt',
    api_url: '',
    username: '',
    password: '',
    verify_ssl: true,
  })

  const createHypervisor = useCreateHypervisor()

  const handleSubmit = () => {
    createHypervisor.mutate(formData, {
      onSuccess: () => {
        onOpenChange(false)
        setFormData({
          name: '',
          type: 'ovirt',
          api_url: '',
          username: '',
          password: '',
          verify_ssl: true,
        })
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Hypervisor</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              placeholder="Production oVirt"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label>Type</Label>
            <Select
              value={formData.type}
              onValueChange={(v) => setFormData({ ...formData, type: v as 'ovirt' | 'proxmox' })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ovirt">oVirt / RHV</SelectItem>
                <SelectItem value="proxmox">Proxmox VE</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>API URL</Label>
            <Input
              placeholder={
                formData.type === 'ovirt'
                  ? 'https://ovirt.example.com/ovirt-engine/api'
                  : 'https://proxmox.example.com:8006/api2/json'
              }
              value={formData.api_url}
              onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label>Username</Label>
            <Input
              placeholder={formData.type === 'ovirt' ? 'admin@internal' : 'root@pam'}
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label>Password</Label>
            <Input
              type="password"
              placeholder="Password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!formData.name || !formData.api_url || createHypervisor.isPending}
          >
            {createHypervisor.isPending ? 'Adding...' : 'Add Hypervisor'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function VMListDialog({
  hypervisorId,
  hypervisorName,
  open,
  onOpenChange,
}: {
  hypervisorId: string
  hypervisorName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: response, isLoading } = useHypervisorVMs(open ? hypervisorId : '')
  const vms = response?.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>VMs on {hypervisorName}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[400px] overflow-y-auto">
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">Loading VMs...</div>
          ) : vms.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">No VMs found</div>
          ) : (
            <div className="space-y-2">
              {vms.map((vm) => (
                <div
                  key={vm.id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div className="flex items-center gap-3">
                    <Monitor className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <div className="font-medium">{vm.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {vm.ip_addresses.length > 0 ? vm.ip_addresses.join(', ') : 'No IP'}
                        {vm.host && ` • ${vm.host}`}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-muted-foreground text-right">
                      {vm.cpu_cores && (
                        <span className="flex items-center gap-1">
                          <Cpu className="h-3 w-3" />
                          {vm.cpu_cores} vCPU
                        </span>
                      )}
                      {vm.memory_mb && (
                        <span className="flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          {Math.round(vm.memory_mb / 1024)} GB
                        </span>
                      )}
                    </div>
                    <Badge
                      variant={vm.status === 'up' || vm.status === 'running' ? 'default' : 'secondary'}
                    >
                      {vm.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function Hypervisors() {
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [vmDialogOpen, setVmDialogOpen] = useState(false)
  const [selectedHypervisor, setSelectedHypervisor] = useState<Hypervisor | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const { data: response, isLoading, refetch, isFetching } = useHypervisors()
  const deleteHypervisor = useDeleteHypervisor()
  const testHypervisor = useTestHypervisor()

  const hypervisors = response?.data ?? []

  const handleTest = (hypervisor: Hypervisor) => {
    setTestingId(hypervisor.id)
    testHypervisor.mutate(hypervisor.id, {
      onSettled: () => setTestingId(null),
    })
  }

  const handleDelete = (hypervisor: Hypervisor) => {
    if (confirm(`Delete hypervisor "${hypervisor.name}"?`)) {
      deleteHypervisor.mutate(hypervisor.id)
    }
  }

  const handleViewVMs = (hypervisor: Hypervisor) => {
    setSelectedHypervisor(hypervisor)
    setVmDialogOpen(true)
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Server className="h-8 w-8 text-muted-foreground" />
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Hypervisors</h2>
            <p className="text-muted-foreground">Loading...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Server className="h-8 w-8 text-muted-foreground" />
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Hypervisors</h2>
            <p className="text-muted-foreground">
              Manage oVirt/RHV and Proxmox VE connections
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button onClick={() => setAddDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Hypervisor
          </Button>
        </div>
      </div>

      {hypervisors.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <Server className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No hypervisors configured.</p>
              <p className="text-sm mt-1">
                Add an oVirt/RHV or Proxmox VE connection to manage VMs.
              </p>
              <Button className="mt-4" onClick={() => setAddDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Hypervisor
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {hypervisors.map((hypervisor) => (
            <HypervisorCard
              key={hypervisor.id}
              hypervisor={hypervisor}
              onTest={() => handleTest(hypervisor)}
              onDelete={() => handleDelete(hypervisor)}
              onViewVMs={() => handleViewVMs(hypervisor)}
              isTestPending={testingId === hypervisor.id}
            />
          ))}
        </div>
      )}

      <AddHypervisorDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} />

      {selectedHypervisor && (
        <VMListDialog
          hypervisorId={selectedHypervisor.id}
          hypervisorName={selectedHypervisor.name}
          open={vmDialogOpen}
          onOpenChange={setVmDialogOpen}
        />
      )}
    </div>
  )
}
