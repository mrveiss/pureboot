# Issue 010: Implement Templates Page and API

**Priority:** MEDIUM
**Type:** Full Stack Feature
**Component:** Frontend + Backend
**Status:** Open

---

## Summary

The Templates page shows "Coming Soon" placeholder. Templates are OS images and configuration files used by workflows for node provisioning.

## Current Behavior

**Router:** `frontend/src/router.tsx:24`
```typescript
{ path: 'templates', element: <div>Templates (Coming Soon)</div> },
```

## Backend Status

Templates API is NOT implemented. Need to design and build.

## Expected Functionality

### Templates Overview

Templates are reusable OS images and configurations:
- ISO images (Ubuntu, Windows, etc.)
- Kickstart/Preseed/Autounattend files
- Post-install scripts
- Driver packages

### Backend API Design

```
GET    /api/v1/templates              - List all templates
GET    /api/v1/templates/{id}         - Get template details
POST   /api/v1/templates              - Create template
PATCH  /api/v1/templates/{id}         - Update template
DELETE /api/v1/templates/{id}         - Delete template
POST   /api/v1/templates/{id}/upload  - Upload template file
```

### Template Model

```python
class Template(Base):
    __tablename__ = "templates"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # iso, kickstart, preseed, autounattend, script
    os_family = Column(String)  # linux, windows
    os_name = Column(String)  # ubuntu, debian, rhel, windows
    os_version = Column(String)  # 24.04, 11, 2022
    architecture = Column(String)  # x86_64, arm64
    file_path = Column(String)  # Path to file on storage backend
    storage_backend_id = Column(String, ForeignKey("storage_backends.id"))
    size_bytes = Column(BigInteger)
    checksum = Column(String)  # SHA256
    description = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### Frontend Page Features

1. List templates with filtering by type/OS
2. Upload new templates
3. Edit template metadata
4. Delete templates
5. Link templates to workflows

## Implementation Steps

### Phase 1: Backend
1. Create `src/db/models.py` - Template model
2. Create `src/api/schemas.py` - Template schemas
3. Create `src/api/routes/templates.py` - CRUD endpoints
4. Add database migration

### Phase 2: Frontend
1. Create `frontend/src/types/template.ts`
2. Create `frontend/src/api/templates.ts`
3. Create `frontend/src/hooks/useTemplates.ts`
4. Create `frontend/src/pages/Templates.tsx`
5. Update router

## Acceptance Criteria

- [ ] Backend CRUD API for templates
- [ ] Templates stored on storage backends
- [ ] Frontend lists templates with metadata
- [ ] Upload functionality works
- [ ] Templates can be associated with workflows

## Related Files

- `frontend/src/router.tsx`
- `src/db/models.py`
- `src/api/routes/templates.py` (new)

## Dependencies

- Storage backends must be implemented (done)
- File upload/download working (done)
