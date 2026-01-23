# Frontend-Backend Alignment Gaps

**Date:** 2026-01-23
**Analysis:** Comprehensive review of frontend GUI vs backend API implementation

---

## Summary

| Category | Missing Backend | Missing Frontend | Alignment Issues |
|----------|-----------------|------------------|------------------|
| Node Management | 3 | 0 | 1 |
| Bulk Operations | 5 | 0 | 0 |
| System/DHCP | 0 | 0 | 1 |
| Pages | 0 | 6 | 0 |
| Workflow | 0 | 2 | 0 |
| **Total** | **8** | **8** | **2** |

---

## CRITICAL: Missing Backend Endpoints

### Issue 1: Node Stats Endpoint Missing

**Priority:** HIGH
**Frontend Location:** [Dashboard.tsx:55](frontend/src/pages/Dashboard.tsx#L55)
**Hook:** `useNodeStats()` in [useNodes.ts:30-61](frontend/src/hooks/useNodes.ts#L30-L61)

**Current Behavior:**
Frontend computes stats by fetching ALL nodes (`limit: 1000`) and aggregating client-side. This is inefficient and will fail with large deployments.

**Expected Endpoint:**
```
GET /api/v1/nodes/stats
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "total": 150,
    "by_state": {
      "discovered": 5,
      "pending": 10,
      "installing": 3,
      "installed": 2,
      "active": 120,
      "reprovision": 2,
      "retired": 8
    },
    "discovered_last_hour": 2,
    "installing_count": 3
  }
}
```

**Action Required:** Implement `GET /api/v1/nodes/stats` in `src/api/routes/nodes.py`

---

### Issue 2: Bulk Assign Group Endpoint Missing

**Priority:** HIGH
**Frontend Location:** [BulkActionBar.tsx](frontend/src/components/nodes/BulkActionBar.tsx)
**API Call:** [nodes.ts:53-58](frontend/src/api/nodes.ts#L53-L58)

**Expected Endpoint:**
```
POST /api/v1/nodes/bulk/assign-group
```

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "group_id": "group-uuid" | null
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": { "updated": 5 },
  "message": "Assigned 5 nodes to group"
}
```

**Action Required:** Implement bulk endpoint in `src/api/routes/nodes.py`

---

### Issue 3: Bulk Assign Workflow Endpoint Missing

**Priority:** MEDIUM
**Frontend Location:** [nodes.ts:60-65](frontend/src/api/nodes.ts#L60-L65)

**Expected Endpoint:**
```
POST /api/v1/nodes/bulk/assign-workflow
```

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "workflow_id": "workflow-id" | null
}
```

**Action Required:** Implement bulk endpoint

---

### Issue 4: Bulk Add Tag Endpoint Missing

**Priority:** HIGH
**Frontend Location:** [BulkActionBar.tsx](frontend/src/components/nodes/BulkActionBar.tsx)
**API Call:** [nodes.ts:67-73](frontend/src/api/nodes.ts#L67-L73)

**Expected Endpoint:**
```
POST /api/v1/nodes/bulk/add-tag
```

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "tag": "production"
}
```

**Action Required:** Implement bulk endpoint

---

### Issue 5: Bulk Remove Tag Endpoint Missing

**Priority:** MEDIUM
**Frontend Location:** [nodes.ts:74-79](frontend/src/api/nodes.ts#L74-L79)

**Expected Endpoint:**
```
POST /api/v1/nodes/bulk/remove-tag
```

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "tag": "staging"
}
```

**Action Required:** Implement bulk endpoint

---

### Issue 6: Bulk Change State Endpoint Missing

**Priority:** HIGH
**Frontend Location:** [BulkActionBar.tsx](frontend/src/components/nodes/BulkActionBar.tsx)
**API Call:** [nodes.ts:81-86](frontend/src/api/nodes.ts#L81-L86)

**Expected Endpoint:**
```
POST /api/v1/nodes/bulk/change-state
```

**Request Body:**
```json
{
  "node_ids": ["uuid1", "uuid2"],
  "new_state": "pending"
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "updated": 4,
    "failed": 1,
    "errors": [
      { "node_id": "uuid5", "error": "Invalid state transition from active to pending" }
    ]
  }
}
```

**Action Required:** Implement bulk endpoint with individual validation

---

### Issue 7: File Delete Endpoint Path Mismatch

**Priority:** MEDIUM
**Frontend Expects:** `POST /api/v1/storage/backends/{id}/files/delete`
**Backend Provides:** `DELETE /api/v1/storage/backends/{id}/files`

**Frontend Location:** [storage.ts:57-62](frontend/src/api/storage.ts#L57-L62)
**Backend Location:** [files.py:144](src/api/routes/files.py#L144)

**Action Required:** Either:
- Add `POST /files/delete` endpoint (recommended for bulk operations)
- Or update frontend to use `DELETE /files` with body

---

### Issue 8: System Info/DHCP Status Frontend Mismatch

**Priority:** LOW
**Backend Provides:** `GET /api/v1/system/dhcp-status` and `GET /api/v1/system/info`
**Frontend:** `GET /api/v1/dhcp-status` (missing `/system` prefix)

**Frontend Location:** Dashboard DHCP banner component
**Backend Location:** [system.py:70](src/api/routes/system.py#L70)

**Action Required:** Update frontend API path to include `/system` prefix

---

## Missing Frontend Pages (Backend Ready)

### Issue 9: Workflows Page Not Implemented

**Priority:** HIGH
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:23](frontend/src/router.tsx#L23)

**Backend Ready:**
- `GET /api/v1/workflows` - Lists all workflows
- `GET /api/v1/workflows/{id}` - Get workflow details

**Action Required:**
1. Create `frontend/src/pages/Workflows.tsx`
2. Create `frontend/src/hooks/useWorkflows.ts`
3. Create `frontend/src/api/workflows.ts`
4. Add workflow selection to NodeDetail page

---

### Issue 10: Templates Page Not Implemented

**Priority:** MEDIUM
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:24](frontend/src/router.tsx#L24)

**Backend Status:** Templates API not implemented yet

**Action Required:**
1. Implement backend templates API
2. Create frontend pages

---

### Issue 11: Hypervisors Page Not Implemented

**Priority:** LOW
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:25](frontend/src/router.tsx#L25)

**Backend Status:** Hypervisors API not implemented yet

**Action Required:**
1. Implement backend hypervisors API
2. Create frontend pages

---

### Issue 12: Approvals Page Not Implemented

**Priority:** MEDIUM
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:27](frontend/src/router.tsx#L27)

**Backend Status:** Approvals API not implemented yet (per PRD, four-eye principle)

**Action Required:**
1. Design and implement approvals API
2. Create frontend pages
3. Integrate with bulk operations

---

### Issue 13: Activity Log Page Not Implemented

**Priority:** MEDIUM
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:28](frontend/src/router.tsx#L28)

**Backend Ready:**
- `GET /api/v1/nodes/{id}/events` - Node events exist
- `GET /api/v1/nodes/{id}/history` - State history exists

**Action Required:**
1. Add global activity/audit log endpoint
2. Create `frontend/src/pages/ActivityLog.tsx`

---

### Issue 14: Users & Roles Page Not Implemented

**Priority:** LOW
**Status:** Shows "Coming Soon" placeholder
**Router:** [router.tsx:30](frontend/src/router.tsx#L30)

**Backend Status:** Authentication/authorization not implemented

**Action Required:**
1. Design RBAC system
2. Implement users API
3. Create frontend pages

---

## Frontend Features Missing Backend Support

### Issue 15: NodeDetail Workflow Assignment Disabled

**Priority:** HIGH
**Location:** [NodeDetail.tsx:273](frontend/src/pages/NodeDetail.tsx#L273)

**Current Status:** Button shows "Assign Workflow (Coming Soon)" and is disabled

**Backend Ready:**
- Workflows list endpoint exists
- Node model has `workflow_id` field

**Missing:**
- `PATCH /api/v1/nodes/{id}` should support `workflow_id` update (may already work)

**Action Required:**
1. Verify node update accepts workflow_id
2. Enable workflow assignment in frontend
3. Add workflow dropdown component

---

### Issue 16: Register Node Button Disabled

**Priority:** MEDIUM
**Location:** [Nodes.tsx](frontend/src/pages/Nodes.tsx)

**Current Status:** "Register Node" button is disabled

**Backend Ready:**
- `POST /api/v1/nodes` endpoint exists

**Action Required:**
1. Create node registration form/dialog
2. Enable the button

---

## Implementation Priority Order

### Phase 1 - Critical Backend (Enables Core UI)
1. **Issue 1:** Node stats endpoint
2. **Issue 2:** Bulk assign group
3. **Issue 4:** Bulk add tag
4. **Issue 6:** Bulk change state

### Phase 2 - Complete Bulk Operations
5. **Issue 3:** Bulk assign workflow
6. **Issue 5:** Bulk remove tag

### Phase 3 - Fix Alignment Issues
7. **Issue 7:** File delete endpoint alignment
8. **Issue 8:** System API path fix

### Phase 4 - Workflows Feature
9. **Issue 9:** Workflows page
10. **Issue 15:** NodeDetail workflow assignment
11. **Issue 16:** Register node dialog

### Phase 5 - Remaining Pages
12. **Issue 13:** Activity log
13. **Issue 12:** Approvals
14. **Issue 10:** Templates
15. **Issue 11:** Hypervisors
16. **Issue 14:** Users & Roles

---

## Appendix: Endpoint Comparison

### Frontend API Calls vs Backend Routes

| Frontend Call | Backend Route | Status |
|--------------|---------------|--------|
| `GET /nodes` | `GET /nodes` | OK |
| `GET /nodes/{id}` | `GET /nodes/{id}` | OK |
| `POST /nodes` | `POST /nodes` | OK |
| `PATCH /nodes/{id}` | `PATCH /nodes/{id}` | OK |
| `PATCH /nodes/{id}/state` | `PATCH /nodes/{id}/state` | OK |
| `DELETE /nodes/{id}` | `DELETE /nodes/{id}` | OK |
| `POST /nodes/{id}/tags` | `POST /nodes/{id}/tags` | OK |
| `DELETE /nodes/{id}/tags/{tag}` | `DELETE /nodes/{id}/tags/{tag}` | OK |
| `GET /nodes/stats` | - | **MISSING** |
| `POST /nodes/bulk/assign-group` | - | **MISSING** |
| `POST /nodes/bulk/assign-workflow` | - | **MISSING** |
| `POST /nodes/bulk/add-tag` | - | **MISSING** |
| `POST /nodes/bulk/remove-tag` | - | **MISSING** |
| `POST /nodes/bulk/change-state` | - | **MISSING** |
| `GET /groups` | `GET /groups` | OK |
| `GET /groups/{id}` | `GET /groups/{id}` | OK |
| `POST /groups` | `POST /groups` | OK |
| `PATCH /groups/{id}` | `PATCH /groups/{id}` | OK |
| `DELETE /groups/{id}` | `DELETE /groups/{id}` | OK |
| `GET /groups/{id}/nodes` | `GET /groups/{id}/nodes` | OK |
| `GET /storage/backends` | `GET /storage/backends` | OK |
| `POST /storage/backends` | `POST /storage/backends` | OK |
| `PATCH /storage/backends/{id}` | `PATCH /storage/backends/{id}` | OK |
| `DELETE /storage/backends/{id}` | `DELETE /storage/backends/{id}` | OK |
| `POST /storage/backends/{id}/test` | `POST /storage/backends/{id}/test` | OK |
| `GET /storage/backends/{id}/files` | `GET /storage/backends/{id}/files` | OK |
| `POST /storage/backends/{id}/folders` | `POST /storage/backends/{id}/folders` | OK |
| `POST /storage/backends/{id}/files/delete` | `DELETE /storage/backends/{id}/files` | **MISMATCH** |
| `POST /storage/backends/{id}/files/move` | `POST /storage/backends/{id}/files/move` | OK |
| `GET /storage/luns` | `GET /storage/luns` | OK |
| `POST /storage/luns` | `POST /storage/luns` | OK |
| `PATCH /storage/luns/{id}` | `PATCH /storage/luns/{id}` | OK |
| `DELETE /storage/luns/{id}` | `DELETE /storage/luns/{id}` | OK |
| `POST /storage/luns/{id}/assign` | `POST /storage/luns/{id}/assign` | OK |
| `POST /storage/luns/{id}/unassign` | `POST /storage/luns/{id}/unassign` | OK |
| `GET /storage/sync-jobs` | `GET /storage/sync-jobs` | OK |
| `POST /storage/sync-jobs` | `POST /storage/sync-jobs` | OK |
| `PATCH /storage/sync-jobs/{id}` | `PATCH /storage/sync-jobs/{id}` | OK |
| `DELETE /storage/sync-jobs/{id}` | `DELETE /storage/sync-jobs/{id}` | OK |
| `POST /storage/sync-jobs/{id}/run` | `POST /storage/sync-jobs/{id}/run` | OK |
| `GET /storage/sync-jobs/{id}/history` | `GET /storage/sync-jobs/{id}/history` | OK |
| `GET /dhcp-status` | `GET /system/dhcp-status` | **PATH MISMATCH** |
| `GET /workflows` | `GET /workflows` | OK |
| `GET /workflows/{id}` | `GET /workflows/{id}` | OK |
