# Multi-Site Management Phase 1: Site Model Foundation

**Issue:** #76 (Phase 1 of 7)
**Status:** Implementation Plan
**Prerequisites:** Issue #10 (Hierarchical Device Groups) - COMPLETED
**Date:** 2026-01-26

---

## Overview

Phase 1 extends the DeviceGroup model with site-specific fields and creates Site CRUD API endpoints. This phase establishes the data foundation without implementing the agent component.

### Goals

1. Extend DeviceGroup with `is_site` flag and site-specific fields
2. Create Site-specific API endpoints
3. Add `home_site_id` to Node model
4. Establish sync state tracking models

### Non-Goals (Later Phases)

- Site agent implementation (Phase 2)
- API proxy and caching (Phase 3)
- Offline operation (Phase 4)

---

## Implementation Tasks (TDD)

### Task 1: Add Site Fields to DeviceGroup Model

**Files:**
- Modify: `src/db/models.py` (DeviceGroup)
- Test: `tests/unit/test_models.py`

**Changes:**
```python
class DeviceGroup(Base):
    # Existing fields...

    # Site-specific fields (null for regular groups)
    is_site: Mapped[bool] = mapped_column(default=False)

    # Site agent connection (only when is_site=True)
    agent_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # online, offline, degraded
    agent_last_seen: Mapped[datetime | None] = mapped_column(nullable=True)

    # Site autonomy settings
    autonomy_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # readonly, limited, full
    conflict_resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)  # central_wins, last_write, site_wins, manual

    # Content caching policy
    cache_policy: Mapped[str | None] = mapped_column(String(20), nullable=True)  # minimal, assigned, mirror, pattern
    cache_patterns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_max_size_gb: Mapped[int | None] = mapped_column(nullable=True)
    cache_retention_days: Mapped[int | None] = mapped_column(nullable=True)

    # Network discovery config
    discovery_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # dhcp, dns, anycast, fallback
    discovery_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Migration policy
    migration_policy: Mapped[str | None] = mapped_column(String(20), nullable=True)  # manual, auto_accept, auto_release, bidirectional
```

**Tests:**
- test_create_site_group
- test_site_fields_nullable_for_regular_groups
- test_site_default_values

---

### Task 2: Add home_site_id to Node Model

**Files:**
- Modify: `src/db/models.py` (Node)
- Test: `tests/unit/test_models.py`

**Changes:**
```python
class Node(Base):
    # Existing...
    home_site_id: Mapped[str | None] = mapped_column(
        ForeignKey("device_groups.id"), nullable=True
    )
    home_site: Mapped["DeviceGroup | None"] = relationship(
        foreign_keys=[home_site_id]
    )
```

**Tests:**
- test_node_has_home_site
- test_node_home_site_relationship
- test_home_site_can_differ_from_group

---

### Task 3: Create SyncState Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Changes:**
```python
class SyncState(Base):
    """Tracks sync state per entity."""
    __tablename__ = "sync_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # node, workflow, template
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("device_groups.id"), nullable=False)
    version: Mapped[int] = mapped_column(default=1)
    last_modified: Mapped[datetime] = mapped_column(default=func.now())
    last_modified_by: Mapped[str] = mapped_column(String(50), nullable=False)  # site_id or "central"
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "site_id", name="uq_sync_state_entity_site"),
    )
```

**Tests:**
- test_sync_state_creation
- test_sync_state_unique_constraint
- test_sync_state_version_increment

---

### Task 4: Create SyncConflict Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Changes:**
```python
class SyncConflict(Base):
    """Conflicts pending manual resolution."""
    __tablename__ = "sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("device_groups.id"), nullable=False)
    central_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    site_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)  # accepted_central, accepted_site, merged
```

**Tests:**
- test_sync_conflict_creation
- test_sync_conflict_resolution

---

### Task 5: Create MigrationClaim Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Changes:**
```python
class MigrationClaim(Base):
    """Tracks node migration between sites."""
    __tablename__ = "migration_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    source_site_id: Mapped[str] = mapped_column(ForeignKey("device_groups.id"), nullable=False)
    target_site_id: Mapped[str] = mapped_column(ForeignKey("device_groups.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected, expired
    auto_approve_eligible: Mapped[bool] = mapped_column(default=False)
    policy_matched: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships
    node: Mapped["Node"] = relationship()
    source_site: Mapped["DeviceGroup"] = relationship(foreign_keys=[source_site_id])
    target_site: Mapped["DeviceGroup"] = relationship(foreign_keys=[target_site_id])
```

**Tests:**
- test_migration_claim_creation
- test_migration_claim_status_transitions
- test_migration_claim_relationships

---

### Task 6: Add Site Schemas

**Files:**
- Modify: `src/api/schemas.py`
- Test: `tests/unit/test_schemas.py`

**Schemas:**
```python
class SiteCreate(BaseModel):
    """Create a site (is_site=True DeviceGroup)."""
    name: str
    description: str | None = None
    parent_id: str | None = None

    # Site-specific
    agent_url: str | None = None
    autonomy_level: str = "readonly"  # readonly, limited, full
    conflict_resolution: str = "central_wins"
    cache_policy: str = "minimal"
    cache_max_size_gb: int | None = None
    cache_retention_days: int = 30
    discovery_method: str = "dhcp"
    migration_policy: str = "manual"

class SiteUpdate(BaseModel):
    """Update site fields."""
    name: str | None = None
    description: str | None = None
    parent_id: str | None = None
    agent_url: str | None = None
    autonomy_level: str | None = None
    conflict_resolution: str | None = None
    cache_policy: str | None = None
    cache_patterns_json: str | None = None
    cache_max_size_gb: int | None = None
    cache_retention_days: int | None = None
    discovery_method: str | None = None
    discovery_config_json: str | None = None
    migration_policy: str | None = None

class SiteResponse(DeviceGroupResponse):
    """Extended response for sites."""
    is_site: bool = True
    agent_url: str | None
    agent_status: str | None
    agent_last_seen: datetime | None
    autonomy_level: str | None
    conflict_resolution: str | None
    cache_policy: str | None
    cache_max_size_gb: int | None
    cache_retention_days: int | None
    discovery_method: str | None
    migration_policy: str | None
```

**Tests:**
- test_site_create_schema_validation
- test_site_autonomy_level_validation
- test_site_response_includes_site_fields

---

### Task 7: Create Sites Router

**Files:**
- Create: `src/api/routes/sites.py`
- Modify: `src/api/routes/__init__.py`
- Test: `tests/integration/test_sites_api.py`

**Endpoints:**
```python
@router.get("/sites")
async def list_sites(...)  # List only is_site=True groups

@router.post("/sites")
async def create_site(...)  # Create DeviceGroup with is_site=True

@router.get("/sites/{site_id}")
async def get_site(...)  # Get site details + agent status

@router.patch("/sites/{site_id}")
async def update_site(...)  # Update site-specific fields

@router.delete("/sites/{site_id}")
async def delete_site(...)  # Delete site (with validation)

@router.get("/sites/{site_id}/nodes")
async def list_site_nodes(...)  # Nodes with home_site_id = this site
```

**Tests:**
- test_create_site
- test_list_sites_excludes_regular_groups
- test_get_site_returns_agent_status
- test_update_site_autonomy_level
- test_delete_site_with_nodes_fails
- test_site_inherits_from_parent_site

---

### Task 8: Add Site Health Endpoint

**Files:**
- Modify: `src/api/routes/sites.py`
- Test: `tests/integration/test_sites_api.py`

**Endpoint:**
```python
@router.get("/sites/{site_id}/health")
async def get_site_health(site_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed site health metrics."""
    # Returns agent_status, last_seen, pending_sync_items, conflicts_pending
```

**Tests:**
- test_site_health_online
- test_site_health_offline
- test_site_health_degraded

---

### Task 9: Add Manual Sync Trigger Endpoint

**Files:**
- Modify: `src/api/routes/sites.py`
- Test: `tests/integration/test_sites_api.py`

**Endpoint:**
```python
@router.post("/sites/{site_id}/sync")
async def trigger_site_sync(site_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger manual sync for a site (queues sync request)."""
```

**Tests:**
- test_trigger_sync_creates_request
- test_trigger_sync_offline_site_queues

---

### Task 10: Integration Tests for Site Hierarchy

**Files:**
- Test: `tests/integration/test_sites_api.py`

**Test Class: TestSiteHierarchy**
- test_site_under_parent_site
- test_site_inherits_parent_settings
- test_nested_sites_hierarchy
- test_move_site_under_different_parent
- test_cannot_make_regular_group_parent_of_site

---

### Task 11: Database Migration

**Files:**
- Create: `migrations/versions/xxx_add_site_fields.py`

Generate Alembic migration for:
- DeviceGroup site fields
- Node.home_site_id
- SyncState table
- SyncConflict table
- MigrationClaim table

---

## Dependencies

| Task | Depends On |
|------|------------|
| 2 | 1 |
| 3-5 | 1 |
| 6 | 1-5 |
| 7 | 6 |
| 8-9 | 7 |
| 10 | 7 |
| 11 | 1-5 |

## Estimated Complexity

- **Task 1-5**: Model changes (Low-Medium each)
- **Task 6**: Schemas (Low)
- **Task 7**: Router implementation (Medium)
- **Task 8-9**: Additional endpoints (Low each)
- **Task 10**: Integration tests (Medium)
- **Task 11**: Migration (Low)

---

## Success Criteria

1. Sites can be created as special DeviceGroups with `is_site=True`
2. Site-specific fields are persisted and queryable
3. Nodes can have a `home_site_id` distinct from `group_id`
4. Sync state models exist for later phases
5. All API endpoints functional with comprehensive tests
6. Sites participate in hierarchical settings inheritance
