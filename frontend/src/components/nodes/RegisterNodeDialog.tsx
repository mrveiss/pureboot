import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useCreateNode, useGroups } from '@/hooks'

interface RegisterNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface FormData {
  mac_address: string
  hostname: string
  arch: string
  boot_mode: string
  group_id: string
  vendor: string
  model: string
  serial_number: string
}

const initialFormData: FormData = {
  mac_address: '',
  hostname: '',
  arch: 'x86_64',
  boot_mode: 'uefi',
  group_id: '',
  vendor: '',
  model: '',
  serial_number: '',
}

export function RegisterNodeDialog({ open, onOpenChange }: RegisterNodeDialogProps) {
  const [formData, setFormData] = useState<FormData>(initialFormData)
  const [error, setError] = useState<string | null>(null)

  const createNode = useCreateNode()
  const { data: groupsResponse } = useGroups()
  const groups = groupsResponse?.data ?? []

  const macRegex = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/
  const isValidMac = macRegex.test(formData.mac_address)

  const handleChange = (field: keyof FormData) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }))
    setError(null)
  }

  const handleSelectChange = (field: keyof FormData) => (value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
    setError(null)
  }

  const handleSubmit = () => {
    if (!isValidMac) {
      setError('Please enter a valid MAC address (e.g., 00:11:22:33:44:55)')
      return
    }

    const payload: Record<string, string | undefined> = {
      mac_address: formData.mac_address.toLowerCase(),
      arch: formData.arch,
      boot_mode: formData.boot_mode,
    }

    if (formData.hostname.trim()) payload.hostname = formData.hostname.trim()
    if (formData.group_id && formData.group_id !== 'none') payload.group_id = formData.group_id
    if (formData.vendor.trim()) payload.vendor = formData.vendor.trim()
    if (formData.model.trim()) payload.model = formData.model.trim()
    if (formData.serial_number.trim()) payload.serial_number = formData.serial_number.trim()

    createNode.mutate(payload, {
      onSuccess: () => {
        setFormData(initialFormData)
        setError(null)
        onOpenChange(false)
      },
      onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
        const detail = err.response?.data?.detail
        if (detail?.includes('already exists')) {
          setError('A node with this MAC address already exists')
        } else {
          setError(detail ?? 'Failed to register node')
        }
      },
    })
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setFormData(initialFormData)
      setError(null)
    }
    onOpenChange(isOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Register Node</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
              {error}
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="mac_address">
              MAC Address <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mac_address"
              placeholder="00:11:22:33:44:55"
              value={formData.mac_address}
              onChange={handleChange('mac_address')}
              className={!formData.mac_address || isValidMac ? '' : 'border-destructive'}
            />
            {formData.mac_address && !isValidMac && (
              <p className="text-xs text-destructive">
                Enter MAC in format XX:XX:XX:XX:XX:XX
              </p>
            )}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="hostname">Hostname</Label>
            <Input
              id="hostname"
              placeholder="server-01"
              value={formData.hostname}
              onChange={handleChange('hostname')}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Architecture</Label>
              <Select
                value={formData.arch}
                onValueChange={handleSelectChange('arch')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="x86_64">x86_64</SelectItem>
                  <SelectItem value="aarch64">aarch64 (ARM64)</SelectItem>
                  <SelectItem value="armv7l">armv7l (ARM32)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Boot Mode</Label>
              <Select
                value={formData.boot_mode}
                onValueChange={handleSelectChange('boot_mode')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="uefi">UEFI</SelectItem>
                  <SelectItem value="bios">BIOS (Legacy)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Device Group</Label>
            <Select
              value={formData.group_id || 'none'}
              onValueChange={handleSelectChange('group_id')}
            >
              <SelectTrigger>
                <SelectValue placeholder="No group" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Group</SelectItem>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="vendor">Vendor</Label>
              <Input
                id="vendor"
                placeholder="Dell, HP, etc."
                value={formData.vendor}
                onChange={handleChange('vendor')}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="model">Model</Label>
              <Input
                id="model"
                placeholder="PowerEdge R640"
                value={formData.model}
                onChange={handleChange('model')}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="serial_number">Serial Number</Label>
            <Input
              id="serial_number"
              placeholder="ABC123XYZ"
              value={formData.serial_number}
              onChange={handleChange('serial_number')}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValidMac || createNode.isPending}
          >
            {createNode.isPending ? 'Registering...' : 'Register Node'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
