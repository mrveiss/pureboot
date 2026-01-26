# Hierarchical Device Groups Design

**Issue:** #10
**Status:** Design Complete
**Author:** Claude + mrveiss
**Date:** 2026-01-26
**Prerequisite For:** Issue #76 (Multi-Site Management)

---

## Overview

Extend the device group system to support parent-child hierarchies with inherited settings.

### Requirements (from Issue #10)

- Groups can have a parent group
- Settings inherit from parent to child (child can override)
- Support for arbitrary nesting depth
- Query nodes by group including descendants

### Example Structure

```
servers/
├── webservers/
│   ├── webservers-prod
│   └── webservers-staging
└── databases/
    ├── databases-prod
    └── databases-staging
```

---

## Data Model

### Schema Changes

```python
class DeviceGroup(Base):
    # Existing fields
    id: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    default_workflow_id: Mapped[str | None]
    auto_provision: Mapped[bool | None]  # Changed to nullable for inheritance

    # New: Hierarchy
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("device_groups.id", ondelete="RESTRICT")
    )
    parent: Mapped["DeviceGroup | None"] = relationship(
        back_populates="children",
        remote_side="DeviceGroup.id"
    )
    children: Mapped[list["DeviceGroup"]] = relationship(
        back_populates="parent"
    )

    # Materialized path for efficient descendant queries
    path: Mapped[str] = mapped_column(String(1000), index=True)
    depth: Mapped[int] = mapped_column(default=0)
```

### Materialized Path Pattern

Enables efficient descendant queries without recursive CTEs:

| Group | Path | Depth |
|-------|------|-------|
| servers | `/servers` | 0 |
| webservers | `/servers/webservers` | 1 |
| webservers-prod | `/servers/webservers/webservers-prod` | 2 |

Query all descendants of "servers": `WHERE path LIKE '/servers/%'`

### Delete Behavior

- `ondelete="RESTRICT"` prevents deleting a group with children
- Must delete or reassign children first
- Cannot delete group with nodes assigned

---

## Settings Inheritance

### Inheritance Model

**Simple override**: Child setting wins if set, otherwise inherit from nearest ancestor.

### Inheritable Fields

| Field | Inherit? | Notes |
|-------|----------|-------|
| `default_workflow_id` | Yes | Primary use case |
| `auto_provision` | Yes | Child can override |
| `description` | No | Each group has its own |
| `name` | No | Must be unique |

### Tri-State Boolean

To distinguish "not set" from "explicitly false":

```python
auto_provision: Mapped[bool | None] = mapped_column(default=None)
```

- `None` = inherit from parent
- `True` = enabled
- `False` = explicitly disabled

### Resolution Logic

```python
def get_effective_settings(group: DeviceGroup) -> dict:
    """
    Walk up the tree, collect first non-null value for each setting.
    """
    settings = {
        "default_workflow_id": None,
        "auto_provision": False,  # Ultimate default
    }

    current = group
    while current:
        if settings["default_workflow_id"] is None:
            if current.default_workflow_id is not None:
                settings["default_workflow_id"] = current.default_workflow_id

        if current.auto_provision is not None:
            settings["auto_provision"] = current.auto_provision
            break  # Found explicit value

        current = current.parent

    return settings
```

---

## API Changes

### Updated Endpoints

```
GET /api/v1/groups
  Query params:
    - ?format=flat (default) | tree
    - ?root_only=true (only top-level groups)
    - ?parent_id={id} (direct children of parent)

POST /api/v1/groups
  - Add optional parent_id to request body
  - Path auto-computed on creation

GET /api/v1/groups/{id}
  - Include parent_id, path, depth
  - Include effective_* computed settings
  - Include children_count

PATCH /api/v1/groups/{id}
  - Can update parent_id (move group)
  - Path auto-recomputed for group and all descendants

DELETE /api/v1/groups/{id}
  - Fails if group has children (RESTRICT)
  - Fails if group has nodes

GET /api/v1/groups/{id}/nodes
  Query params:
    - ?include_descendants=true (nodes from all descendant groups)

GET /api/v1/groups/{id}/ancestors
  - Returns parent chain up to root

GET /api/v1/groups/{id}/descendants
  - Returns all descendant groups (flat list)
```

### Request Schemas

```python
class DeviceGroupCreate(BaseModel):
    name: str
    description: str | None = None
    parent_id: str | None = None  # NEW
    default_workflow_id: str | None = None
    auto_provision: bool | None = None  # Changed to nullable

class DeviceGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: str | None = None  # NEW - allows moving groups
    default_workflow_id: str | None = None
    auto_provision: bool | None = None
```

### Response Schema

```python
class DeviceGroupResponse(BaseModel):
    id: str
    name: str
    description: str | None

    # Hierarchy
    parent_id: str | None
    path: str
    depth: int
    children_count: int

    # Own settings (may be null = inherit)
    default_workflow_id: str | None
    auto_provision: bool | None

    # Effective settings (computed after inheritance)
    effective_workflow_id: str | None
    effective_auto_provision: bool

    node_count: int
    created_at: datetime
    updated_at: datetime
```

### Tree Response Format

When `GET /api/v1/groups?format=tree`:

```json
{
  "data": [
    {
      "id": "uuid-1",
      "name": "servers",
      "path": "/servers",
      "depth": 0,
      "children": [
        {
          "id": "uuid-2",
          "name": "webservers",
          "path": "/servers/webservers",
          "depth": 1,
          "children": [
            {
              "id": "uuid-3",
              "name": "prod",
              "path": "/servers/webservers/prod",
              "depth": 2,
              "children": []
            }
          ]
        }
      ]
    }
  ]
}
```

---

## Path Management

### Path Computation

```python
def compute_path(group: DeviceGroup) -> str:
    """Compute path from root to this group."""
    if group.parent is None:
        return f"/{group.name}"
    return f"{group.parent.path}/{group.name}"

def compute_depth(group: DeviceGroup) -> int:
    """Compute depth (0 = root)."""
    if group.parent is None:
        return 0
    return group.parent.depth + 1
```

### On Create

```python
async def create_group(group_data: DeviceGroupCreate, db: AsyncSession):
    parent = None
    if group_data.parent_id:
        parent = await db.get(DeviceGroup, group_data.parent_id)
        if not parent:
            raise HTTPException(404, "Parent group not found")

    group = DeviceGroup(
        name=group_data.name,
        parent_id=group_data.parent_id,
        description=group_data.description,
        default_workflow_id=group_data.default_workflow_id,
        auto_provision=group_data.auto_provision,
    )

    # Compute path and depth
    if parent:
        group.path = f"{parent.path}/{group.name}"
        group.depth = parent.depth + 1
    else:
        group.path = f"/{group.name}"
        group.depth = 0

    db.add(group)
    await db.flush()
    return group
```

### On Move (Reparent)

When `parent_id` changes, update paths for the group and all descendants:

```python
async def update_group_parent(
    group: DeviceGroup,
    new_parent_id: str | None,
    db: AsyncSession
):
    old_path = group.path

    # Compute new path
    if new_parent_id:
        new_parent = await db.get(DeviceGroup, new_parent_id)
        if not new_parent:
            raise HTTPException(404, "Parent group not found")

        # Prevent circular reference
        if new_parent.path.startswith(group.path + "/") or new_parent.id == group.id:
            raise HTTPException(400, "Cannot move group under itself or its descendant")

        new_path = f"{new_parent.path}/{group.name}"
        new_depth = new_parent.depth + 1
    else:
        new_path = f"/{group.name}"
        new_depth = 0

    # Update all descendants' paths
    depth_diff = new_depth - group.depth
    await db.execute(
        update(DeviceGroup)
        .where(DeviceGroup.path.startswith(old_path + "/"))
        .values(
            path=func.replace(DeviceGroup.path, old_path, new_path),
            depth=DeviceGroup.depth + depth_diff
        )
    )

    group.path = new_path
    group.depth = new_depth
    group.parent_id = new_parent_id
```

### On Rename

Update descendant paths when group name changes:

```python
async def rename_group(group: DeviceGroup, new_name: str, db: AsyncSession):
    old_path = group.path

    if group.parent:
        new_path = f"{group.parent.path}/{new_name}"
    else:
        new_path = f"/{new_name}"

    # Update descendants
    await db.execute(
        update(DeviceGroup)
        .where(DeviceGroup.path.startswith(old_path + "/"))
        .values(path=func.replace(DeviceGroup.path, old_path, new_path))
    )

    group.name = new_name
    group.path = new_path
```

---

## Query Implementations

### Get Nodes Including Descendants

```python
@router.get("/groups/{group_id}/nodes")
async def list_group_nodes(
    group_id: str,
    include_descendants: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if include_descendants:
        # Get all groups with matching path prefix
        group_ids_query = select(DeviceGroup.id).where(
            (DeviceGroup.id == group_id) |
            (DeviceGroup.path.startswith(group.path + "/"))
        )
        nodes_query = (
            select(Node)
            .where(Node.group_id.in_(group_ids_query))
            .options(selectinload(Node.tags))
        )
    else:
        nodes_query = (
            select(Node)
            .where(Node.group_id == group_id)
            .options(selectinload(Node.tags))
        )

    result = await db.execute(nodes_query)
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes)
    )
```

### Get Descendant Groups

```python
@router.get("/groups/{group_id}/descendants")
async def list_descendants(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    query = (
        select(DeviceGroup)
        .where(DeviceGroup.path.startswith(group.path + "/"))
        .order_by(DeviceGroup.path)
    )

    result = await db.execute(query)
    descendants = result.scalars().all()

    return ApiListResponse(
        data=[DeviceGroupResponse.from_group(g) for g in descendants],
        total=len(descendants)
    )
```

### Get Ancestors

```python
@router.get("/groups/{group_id}/ancestors")
async def list_ancestors(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    # Parse path to get ancestor paths
    # Path: /servers/webservers/prod → ancestors: /servers, /servers/webservers
    path_parts = group.path.strip("/").split("/")[:-1]  # Exclude self

    ancestor_paths = []
    current_path = ""
    for part in path_parts:
        current_path = f"{current_path}/{part}"
        ancestor_paths.append(current_path)

    if not ancestor_paths:
        return ApiListResponse(data=[], total=0)

    result = await db.execute(
        select(DeviceGroup)
        .where(DeviceGroup.path.in_(ancestor_paths))
        .order_by(DeviceGroup.depth)
    )
    ancestors = result.scalars().all()

    return ApiListResponse(
        data=[DeviceGroupResponse.from_group(g) for g in ancestors],
        total=len(ancestors)
    )
```

### Build Tree Structure

```python
def build_tree(groups: list[DeviceGroup]) -> list[dict]:
    """Convert flat group list to nested tree structure."""
    groups_by_id = {g.id: g for g in groups}
    root_groups = []

    # Add children list to each group response
    responses = {}
    for g in groups:
        resp = DeviceGroupResponse.from_group(g).model_dump()
        resp["children"] = []
        responses[g.id] = resp

    # Build tree
    for g in groups:
        if g.parent_id and g.parent_id in responses:
            responses[g.parent_id]["children"].append(responses[g.id])
        else:
            root_groups.append(responses[g.id])

    return root_groups
```

---

## Database Migration

```python
"""Add hierarchy fields to device_groups.

Revision ID: xxx
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add new columns
    op.add_column('device_groups',
        sa.Column('parent_id', sa.String(36), nullable=True))
    op.add_column('device_groups',
        sa.Column('path', sa.String(1000), nullable=True))
    op.add_column('device_groups',
        sa.Column('depth', sa.Integer(), nullable=True, default=0))

    # Backfill existing groups as roots
    op.execute("""
        UPDATE device_groups
        SET path = '/' || name, depth = 0
        WHERE path IS NULL
    """)

    # Make columns non-nullable after backfill
    op.alter_column('device_groups', 'path', nullable=False)
    op.alter_column('device_groups', 'depth', nullable=False)

    # Add foreign key
    op.create_foreign_key(
        'fk_device_groups_parent',
        'device_groups', 'device_groups',
        ['parent_id'], ['id'],
        ondelete='RESTRICT'
    )

    # Add index for path queries
    op.create_index('ix_device_groups_path', 'device_groups', ['path'])

    # Change auto_provision to nullable for inheritance
    op.alter_column('device_groups', 'auto_provision', nullable=True)

def downgrade():
    op.drop_index('ix_device_groups_path')
    op.drop_constraint('fk_device_groups_parent', 'device_groups')
    op.drop_column('device_groups', 'depth')
    op.drop_column('device_groups', 'path')
    op.drop_column('device_groups', 'parent_id')
    op.alter_column('device_groups', 'auto_provision', nullable=False)
```

---

## Implementation Phases

### Phase 1: Schema Migration
- Add `parent_id`, `path`, `depth` columns
- Add foreign key with RESTRICT
- Backfill path/depth for existing groups (all become roots)
- Add index on `path`
- Make `auto_provision` nullable

### Phase 2: Core API Updates
- Update create endpoint to accept `parent_id`
- Implement path/depth computation on create
- Update response schema with hierarchy fields
- Implement effective settings computation

### Phase 3: Move & Rename
- Implement parent change with path cascade
- Implement rename with path cascade
- Add circular reference prevention
- Add validation (cannot move under self)

### Phase 4: Query Endpoints
- Add `GET /groups/{id}/descendants`
- Add `GET /groups/{id}/ancestors`
- Add `?include_descendants=true` to node listing
- Add `?format=tree` to group listing

### Phase 5: UI Updates
- Tree view in groups list
- Parent selector dropdown in create/edit forms
- Breadcrumb showing ancestor path
- "Effective settings" display with inheritance indicator

---

## Acceptance Criteria

From Issue #10:

- [x] Parent-child relationship in DeviceGroup model
- [x] Settings inheritance logic
- [x] API endpoints for managing hierarchy
- [x] Query nodes by group with `include_descendants` option

---

## References

- Issue #10: Implement Hierarchical Device Groups
- Issue #76: Multi-Site Management (depends on this)
- Issue #2: Controller API with Node Management (prerequisite)