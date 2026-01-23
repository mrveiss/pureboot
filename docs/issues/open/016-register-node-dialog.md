# Issue 016: Implement Register Node Dialog

**Priority:** MEDIUM
**Type:** Frontend Enhancement
**Component:** Frontend - Nodes Page
**Status:** Open

---

## Summary

The Nodes page has a disabled "Register Node" button. While nodes typically auto-register via PXE boot, manual registration is useful for pre-staging nodes before they boot.

## Current Behavior

**Location:** `frontend/src/pages/Nodes.tsx`
```typescript
<Button disabled>
  <Plus className="mr-2 h-4 w-4" />
  Register Node
</Button>
```

## Backend Ready

- `POST /api/v1/nodes` - Create node endpoint exists
- Accepts: mac_address (required), hostname, arch, boot_mode, vendor, model, etc.

## Expected Behavior

1. Button opens registration dialog
2. User enters node details (MAC address required)
3. Node created in "discovered" state
4. Node appears in table

## Implementation

### 1. Create RegisterNodeDialog component

```typescript
// frontend/src/components/nodes/RegisterNodeDialog.tsx

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
import { nodesApi } from '@/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { nodeKeys } from '@/hooks'

interface RegisterNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function RegisterNodeDialog({ open, onOpenChange }: RegisterNodeDialogProps) {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState({
    mac_address: '',
    hostname: '',
    arch: 'x86_64',
    boot_mode: 'uefi',
    vendor: '',
    model: '',
    serial_number: '',
  })

  const createNode = useMutation({
    mutationFn: () => nodesApi.create(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      onOpenChange(false)
      setFormData({
        mac_address: '',
        hostname: '',
        arch: 'x86_64',
        boot_mode: 'uefi',
        vendor: '',
        model: '',
        serial_number: '',
      })
    },
  })

  const isValidMac = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/.test(formData.mac_address)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Register Node</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="mac">MAC Address *</Label>
            <Input
              id="mac"
              placeholder="00:11:22:33:44:55"
              value={formData.mac_address}
              onChange={(e) => setFormData({ ...formData, mac_address: e.target.value })}
            />
            {formData.mac_address && !isValidMac && (
              <p className="text-sm text-destructive">Invalid MAC address format</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="hostname">Hostname</Label>
            <Input
              id="hostname"
              placeholder="server-01"
              value={formData.hostname}
              onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Architecture</Label>
              <Select
                value={formData.arch}
                onValueChange={(v) => setFormData({ ...formData, arch: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="x86_64">x86_64</SelectItem>
                  <SelectItem value="aarch64">aarch64</SelectItem>
                  <SelectItem value="armv7l">armv7l</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Boot Mode</Label>
              <Select
                value={formData.boot_mode}
                onValueChange={(v) => setFormData({ ...formData, boot_mode: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="uefi">UEFI</SelectItem>
                  <SelectItem value="bios">BIOS</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="vendor">Vendor</Label>
              <Input
                id="vendor"
                placeholder="Dell"
                value={formData.vendor}
                onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Input
                id="model"
                placeholder="PowerEdge R640"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="serial">Serial Number</Label>
            <Input
              id="serial"
              placeholder="ABC123XYZ"
              value={formData.serial_number}
              onChange={(e) => setFormData({ ...formData, serial_number: e.target.value })}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => createNode.mutate()}
            disabled={!isValidMac || createNode.isPending}
          >
            {createNode.isPending ? 'Registering...' : 'Register'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

### 2. Update Nodes.tsx

```typescript
import { RegisterNodeDialog } from '@/components/nodes'

export function Nodes() {
  const [registerOpen, setRegisterOpen] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2>Nodes</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => setRegisterOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Register Node
          </Button>
        </div>
      </div>

      {/* ... table ... */}

      <RegisterNodeDialog
        open={registerOpen}
        onOpenChange={setRegisterOpen}
      />
    </div>
  )
}
```

## Acceptance Criteria

- [ ] "Register Node" button is enabled
- [ ] Dialog opens with form fields
- [ ] MAC address validation (format check)
- [ ] Duplicate MAC check (409 error handled)
- [ ] Success creates node and closes dialog
- [ ] New node appears in table
- [ ] Form resets after successful creation

## Related Files

- `frontend/src/pages/Nodes.tsx`
- `frontend/src/components/nodes/RegisterNodeDialog.tsx` (new)
- `frontend/src/api/nodes.ts`
- `src/api/routes/nodes.py` (POST endpoint exists)
