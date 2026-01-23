# Issue 011: Implement Hypervisors Page and API

**Priority:** LOW
**Type:** Full Stack Feature
**Component:** Frontend + Backend
**Status:** Open

---

## Summary

The Hypervisors page shows "Coming Soon" placeholder. Per the PRD, PureBoot should integrate with oVirt/RHV and Proxmox VE for VM lifecycle management.

## Current Behavior

**Router:** `frontend/src/router.tsx:25`
```typescript
{ path: 'hypervisors', element: <div>Hypervisors (Coming Soon)</div> },
```

## Backend Status

Hypervisors API is NOT implemented. Integration requires external SDK connections.

## Expected Functionality

### Supported Hypervisors (per PRD)

1. **oVirt/RHV** - Red Hat Virtualization
2. **Proxmox VE** - Open source virtualization

### Backend API Design

```
GET    /api/v1/hypervisors                     - List hypervisor connections
GET    /api/v1/hypervisors/{id}                - Get hypervisor details
POST   /api/v1/hypervisors                     - Add hypervisor connection
PATCH  /api/v1/hypervisors/{id}                - Update connection
DELETE /api/v1/hypervisors/{id}                - Remove connection
POST   /api/v1/hypervisors/{id}/test           - Test connection
GET    /api/v1/hypervisors/{id}/vms            - List VMs
POST   /api/v1/hypervisors/{id}/vms            - Create VM
GET    /api/v1/hypervisors/{id}/templates      - List VM templates
```

### Hypervisor Model

```python
class Hypervisor(Base):
    __tablename__ = "hypervisors"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # ovirt, proxmox
    api_url = Column(String, nullable=False)
    username = Column(String)
    password_encrypted = Column(String)  # Encrypted credentials
    verify_ssl = Column(Boolean, default=True)
    status = Column(String, default="unknown")  # online, offline, error
    last_sync_at = Column(DateTime)
    vm_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### Frontend Page Features

1. List configured hypervisors with status
2. Add new hypervisor connections
3. Test connectivity
4. Browse VMs on each hypervisor
5. Create VMs from templates
6. Associate VMs with PureBoot nodes

## Implementation Steps

### Phase 1: Backend
1. Create Hypervisor model
2. Implement oVirt SDK integration
3. Implement Proxmox API integration
4. Create CRUD endpoints
5. Add VM listing and creation

### Phase 2: Frontend
1. Create types
2. Create API client
3. Create hooks
4. Create Hypervisors page
5. Create VM browser component

## Dependencies

- oVirt SDK: `ovirt-engine-sdk-python`
- Proxmox API: `proxmoxer`

## Acceptance Criteria

- [ ] Can add oVirt/RHV connection
- [ ] Can add Proxmox connection
- [ ] Connection test works
- [ ] Can list VMs from hypervisor
- [ ] Can create VM from template
- [ ] Credentials stored securely (encrypted)

## Related Files

- `frontend/src/router.tsx`
- `src/db/models.py`
- `src/api/routes/hypervisors.py` (new)
- `src/core/hypervisors/` (new directory)

## PRD Reference

See `docs/PureBoot_Product_Requirements_Document.md` sections on:
- oVirt/RHV Integration
- Proxmox VE Integration
