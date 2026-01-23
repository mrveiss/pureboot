# Issue 008: DHCP Status API Path Mismatch

**Priority:** LOW
**Type:** Bug - API Mismatch
**Component:** Frontend - Dashboard
**Status:** Open

---

## Summary

The frontend DHCP setup banner may be calling the wrong API path for DHCP status. The backend uses `/api/v1/system/dhcp-status` but frontend might be missing the `/system` prefix.

## Current Behavior

**Backend provides:** `GET /api/v1/system/dhcp-status`
**Frontend may call:** `GET /api/v1/dhcp-status` (needs verification)

**Backend location:** `src/api/routes/system.py:70`
```python
@router.get("/dhcp-status", response_model=DhcpStatusResponse)
async def get_dhcp_status(
    db: AsyncSession = Depends(get_db),
):
```

Note: The router is mounted under `/system` prefix in main.py.

## Investigation Needed

Check frontend code for DHCP status API call:
1. `frontend/src/components/dashboard/DhcpSetupBanner.tsx`
2. `frontend/src/api/system.ts` (if exists)
3. `frontend/src/hooks/useSystem.ts` (if exists)

## Expected Behavior

Frontend should call: `GET /api/v1/system/dhcp-status`

**Response:**
```json
{
  "server_ip": "192.168.1.100",
  "server_port": 8080,
  "tftp_enabled": true,
  "tftp_port": 69,
  "required_settings": {
    "next_server": "192.168.1.100",
    "filename_bios": "pxelinux.0",
    "filename_uefi": "ipxe.efi"
  },
  "status": {
    "nodes_connected": 15,
    "nodes_with_issues": 2,
    "last_connection": "2026-01-23T10:30:00Z",
    "issues": [
      "2 nodes received incorrect DHCP settings"
    ]
  },
  "first_run": false
}
```

## Implementation

If mismatch confirmed, update frontend API client:

**Create/Update `frontend/src/api/system.ts`:**
```typescript
import { apiClient } from './client'
import type { ApiResponse, DhcpStatus } from '@/types'

export const systemApi = {
  async getDhcpStatus(): Promise<ApiResponse<DhcpStatus>> {
    return apiClient.get<ApiResponse<DhcpStatus>>('/system/dhcp-status')
  },

  async getServerInfo(): Promise<ApiResponse<ServerInfo>> {
    return apiClient.get<ApiResponse<ServerInfo>>('/system/info')
  },
}
```

## Acceptance Criteria

- [ ] Verify actual API path used by frontend
- [ ] Fix path if mismatched
- [ ] DHCP setup banner displays correctly on Dashboard
- [ ] First-run detection works properly

## Related Files

- `frontend/src/components/dashboard/DhcpSetupBanner.tsx`
- `frontend/src/api/system.ts`
- `src/api/routes/system.py`
