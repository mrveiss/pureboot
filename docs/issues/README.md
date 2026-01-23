# PureBoot Issue Tracker

This directory contains tracked issues for frontend-backend alignment and feature implementation.

## Issue Summary

| ID | Title | Priority | Type | Status |
|----|-------|----------|------|--------|
| [001](open/001-node-stats-endpoint.md) | Implement Node Stats Endpoint | HIGH | Backend | Open |
| [002](open/002-bulk-assign-group.md) | Implement Bulk Assign Group Endpoint | HIGH | Backend | Open |
| [003](open/003-bulk-assign-workflow.md) | Implement Bulk Assign Workflow Endpoint | MEDIUM | Backend | Open |
| [004](open/004-bulk-add-tag.md) | Implement Bulk Add Tag Endpoint | HIGH | Backend | Open |
| [005](open/005-bulk-remove-tag.md) | Implement Bulk Remove Tag Endpoint | MEDIUM | Backend | Open |
| [006](open/006-bulk-change-state.md) | Implement Bulk Change State Endpoint | HIGH | Backend | Open |
| [007](open/007-file-delete-endpoint-mismatch.md) | File Delete Endpoint Path Mismatch | MEDIUM | Bug | Open |
| [008](open/008-dhcp-status-path-mismatch.md) | DHCP Status API Path Mismatch | LOW | Bug | Open |
| [009](open/009-workflows-page.md) | Implement Workflows Page | HIGH | Frontend | Open |
| [010](open/010-templates-page.md) | Implement Templates Page and API | MEDIUM | Full Stack | Open |
| [011](open/011-hypervisors-page.md) | Implement Hypervisors Page and API | LOW | Full Stack | Open |
| [012](open/012-approvals-page.md) | Implement Approvals Page and API | MEDIUM | Full Stack | Open |
| [013](open/013-activity-log-page.md) | Implement Activity Log Page | MEDIUM | Frontend | Open |
| [014](open/014-users-roles-page.md) | Implement Users & Roles Page | LOW | Full Stack | Open |
| [015](open/015-nodedetail-workflow-assignment.md) | Enable Workflow Assignment in Node Detail | HIGH | Frontend | Open |
| [016](open/016-register-node-dialog.md) | Implement Register Node Dialog | MEDIUM | Frontend | Open |

## Priority Breakdown

### HIGH Priority (6 issues)
Critical for core UI functionality:
- 001: Node stats endpoint (Dashboard broken)
- 002: Bulk assign group (BulkActionBar broken)
- 004: Bulk add tag (BulkActionBar broken)
- 006: Bulk change state (BulkActionBar broken)
- 009: Workflows page (Backend ready)
- 015: Workflow assignment (Backend ready)

### MEDIUM Priority (6 issues)
Important features:
- 003: Bulk assign workflow
- 005: Bulk remove tag
- 007: File delete mismatch
- 010: Templates feature
- 012: Approvals (PRD requirement)
- 013: Activity log
- 016: Register node dialog

### LOW Priority (4 issues)
Nice to have:
- 008: DHCP path mismatch
- 011: Hypervisors integration
- 014: Users & authentication

## Implementation Phases

### Phase 1: Critical Backend (Unblocks Core UI)
```
001 → 002 → 004 → 006
```
Enables: Dashboard stats, bulk operations

### Phase 2: Complete Bulk Operations
```
003 → 005
```
Enables: Full bulk action bar functionality

### Phase 3: Fix Alignment Issues
```
007 → 008
```
Fixes: File deletion, DHCP status

### Phase 4: Workflows Feature
```
009 → 015 → 016
```
Enables: Complete workflow management

### Phase 5: Remaining Pages
```
013 → 012 → 010 → 011 → 014
```
Enables: Activity log, approvals, templates, hypervisors, auth

## Directory Structure

```
docs/issues/
├── README.md                 # This file
├── frontend-backend-gaps.md  # Original analysis document
└── open/                     # Open issues
    ├── 001-*.md
    ├── 002-*.md
    └── ...
```

## Contributing

When closing an issue:
1. Move the file from `open/` to `closed/`
2. Add resolution notes at the bottom
3. Update status in this README

## Related Documentation

- [PRD](../PureBoot_Product_Requirements_Document.md) - Product requirements
- [Architecture](../architecture/) - System design
- [API Reference](../api/) - API documentation
- [Implementation Plans](../plans/) - Detailed implementation plans
