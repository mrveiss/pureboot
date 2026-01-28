# Hierarchical Device Groups Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add parent-child hierarchy to DeviceGroups with settings inheritance and descendant queries.

**Architecture:** Materialized path pattern (`/parent/child/grandchild`) for efficient descendant queries without recursive CTEs. Simple override inheritance where child settings win if set.

**Tech Stack:** SQLAlchemy, FastAPI, Pydantic, SQLite (test) / PostgreSQL (prod), pytest

**Design Doc:** `docs/plans/2026-01-26-hierarchical-device-groups-design.md`

---

## Task 1: Add Hierarchy Fields to DeviceGroup Model

**Files:**
- Modify: `src/db/models.py:15-41` (DeviceGroup class)
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestDeviceGroupHierarchy:
    """Test DeviceGroup hierarchy features."""

    def test_group_with_parent(self, session):
        """Group can have a parent."""
        parent = DeviceGroup(name="servers")
        session.add(parent)
        session.flush()

        child = DeviceGroup(name="webservers", parent_id=parent.id)
        session.add(child)
        session.commit()

        assert child.parent_id == parent.id
        assert child.parent.name == "servers"
        assert child in parent.children

    def test_group_path_and_depth(self, session):
        """Group has path and depth fields."""
        group = DeviceGroup(name="servers", path="/servers", depth=0)
        session.add(group)
        session.commit()

        assert group.path == "/servers"
        assert group.depth == 0

    def test_auto_provision_nullable(self, session):
        """auto_provision can be None for inheritance."""
        group = DeviceGroup(name="servers", auto_provision=None)
        session.add(group)
        session.commit()

        assert group.auto_provision is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::TestDeviceGroupHierarchy -v`
Expected: FAIL - "parent_id" not found

**Step 3: Update DeviceGroup model**

In `src/db/models.py`, replace the DeviceGroup class (lines 15-41):

```python
class DeviceGroup(Base):
    """Device group for organizing nodes with shared settings."""

    __tablename__ = "device_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    # Hierarchy
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("device_groups.id", ondelete="RESTRICT"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(1000), index=True, default="/")
    depth: Mapped[int] = mapped_column(default=0)

    # Default settings for nodes in this group (nullable for inheritance)
    default_workflow_id: Mapped[str | None] = mapped_column(String(36))
    auto_provision: Mapped[bool | None] = mapped_column(default=None)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    parent: Mapped["DeviceGroup | None"] = relationship(
        "DeviceGroup",
        back_populates="children",
        remote_side="DeviceGroup.id",
    )
    children: Mapped[list["DeviceGroup"]] = relationship(
        "DeviceGroup",
        back_populates="parent",
    )
    nodes: Mapped[list["Node"]] = relationship(back_populates="group")
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_device_groups", back_populates="device_groups"
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py::TestDeviceGroupHierarchy -v`
Expected: PASS

**Step 5: Run all model tests to check for regressions**

Run: `pytest tests/unit/test_models.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat(models): add hierarchy fields to DeviceGroup

Add parent_id, path, depth fields for hierarchical groups.
Make auto_provision nullable for inheritance support.
Add parent/children relationships."
```

---

## Task 2: Update DeviceGroup Schemas

**Files:**
- Modify: `src/api/schemas.py:256-309` (DeviceGroup schemas)
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_schemas.py`:

```python
from src.api.schemas import DeviceGroupCreate, DeviceGroupUpdate, DeviceGroupResponse


class TestDeviceGroupSchemas:
    """Test DeviceGroup schema changes for hierarchy."""

    def test_create_with_parent_id(self):
        """DeviceGroupCreate accepts parent_id."""
        data = DeviceGroupCreate(name="webservers", parent_id="parent-uuid")
        assert data.parent_id == "parent-uuid"

    def test_create_auto_provision_nullable(self):
        """DeviceGroupCreate auto_provision can be None."""
        data = DeviceGroupCreate(name="webservers", auto_provision=None)
        assert data.auto_provision is None

    def test_update_with_parent_id(self):
        """DeviceGroupUpdate accepts parent_id."""
        data = DeviceGroupUpdate(parent_id="new-parent-uuid")
        assert data.parent_id == "new-parent-uuid"

    def test_response_has_hierarchy_fields(self):
        """DeviceGroupResponse includes hierarchy fields."""
        # Create mock group-like object
        class MockGroup:
            id = "uuid"
            name = "webservers"
            description = None
            parent_id = "parent-uuid"
            path = "/servers/webservers"
            depth = 1
            default_workflow_id = None
            auto_provision = None
            created_at = "2026-01-26T00:00:00"
            updated_at = "2026-01-26T00:00:00"

        resp = DeviceGroupResponse.from_group(MockGroup(), node_count=5, children_count=2)
        assert resp.parent_id == "parent-uuid"
        assert resp.path == "/servers/webservers"
        assert resp.depth == 1
        assert resp.children_count == 2
        assert resp.effective_auto_provision is False  # Default when None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_schemas.py::TestDeviceGroupSchemas -v`
Expected: FAIL - parent_id not in schema

**Step 3: Update schemas**

In `src/api/schemas.py`, replace DeviceGroup schemas (around lines 256-309):

```python
class DeviceGroupCreate(BaseModel):
    """Schema for creating a device group."""

    name: str
    description: str | None = None
    parent_id: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate group name."""
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v


class DeviceGroupUpdate(BaseModel):
    """Schema for updating a device group."""

    name: str | None = None
    description: str | None = None
    parent_id: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None


class DeviceGroupResponse(BaseModel):
    """Schema for device group response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None

    # Hierarchy
    parent_id: str | None
    path: str
    depth: int
    children_count: int = 0

    # Own settings (may be None = inherit)
    default_workflow_id: str | None
    auto_provision: bool | None

    # Effective settings (computed)
    effective_workflow_id: str | None = None
    effective_auto_provision: bool = False

    # Metadata
    node_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_group(
        cls,
        group,
        node_count: int = 0,
        children_count: int = 0,
        effective_workflow_id: str | None = None,
        effective_auto_provision: bool = False,
    ) -> "DeviceGroupResponse":
        """Create response from DeviceGroup model."""
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            parent_id=group.parent_id,
            path=group.path,
            depth=group.depth,
            children_count=children_count,
            default_workflow_id=group.default_workflow_id,
            auto_provision=group.auto_provision,
            effective_workflow_id=effective_workflow_id
            if effective_workflow_id
            else group.default_workflow_id,
            effective_auto_provision=effective_auto_provision
            if group.auto_provision is None
            else group.auto_provision,
            node_count=node_count,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_schemas.py::TestDeviceGroupSchemas -v`
Expected: PASS

**Step 5: Run all schema tests**

Run: `pytest tests/unit/test_schemas.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/api/schemas.py tests/unit/test_schemas.py
git commit -m "feat(schemas): add hierarchy fields to DeviceGroup schemas

- Add parent_id to Create/Update schemas
- Add path, depth, children_count to Response
- Add effective_workflow_id, effective_auto_provision for inheritance
- Make auto_provision nullable"
```

---

## Task 3: Update Create Group Endpoint

**Files:**
- Modify: `src/api/routes/groups.py:47-74` (create_group function)
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py`:

```python
class TestGroupHierarchy:
    """Test device group hierarchy operations."""

    def test_create_group_with_parent(self, client: TestClient):
        """Create child group with parent."""
        # Create parent
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        # Create child
        response = client.post(
            "/api/v1/groups",
            json={"name": "webservers", "parent_id": parent_id},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["parent_id"] == parent_id
        assert data["path"] == "/servers/webservers"
        assert data["depth"] == 1

    def test_create_root_group_has_correct_path(self, client: TestClient):
        """Root group has path /{name} and depth 0."""
        response = client.post("/api/v1/groups", json={"name": "servers"})
        data = response.json()["data"]
        assert data["parent_id"] is None
        assert data["path"] == "/servers"
        assert data["depth"] == 0

    def test_create_group_invalid_parent_fails(self, client: TestClient):
        """Creating group with non-existent parent fails."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "webservers", "parent_id": "nonexistent-uuid"},
        )
        assert response.status_code == 404
        assert "Parent group not found" in response.json()["detail"]

    def test_create_nested_hierarchy(self, client: TestClient):
        """Create deeply nested hierarchy."""
        # Level 0
        r1 = client.post("/api/v1/groups", json={"name": "servers"})
        id1 = r1.json()["data"]["id"]

        # Level 1
        r2 = client.post("/api/v1/groups", json={"name": "web", "parent_id": id1})
        id2 = r2.json()["data"]["id"]

        # Level 2
        r3 = client.post("/api/v1/groups", json={"name": "prod", "parent_id": id2})
        data = r3.json()["data"]

        assert data["path"] == "/servers/web/prod"
        assert data["depth"] == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy -v`
Expected: FAIL

**Step 3: Update create_group endpoint**

In `src/api/routes/groups.py`, replace create_group function:

```python
@router.post("/groups", response_model=ApiResponse[DeviceGroupResponse], status_code=201)
async def create_group(
    group_data: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new device group."""
    # Check for duplicate name
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == group_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Group '{group_data.name}' already exists",
        )

    # Validate parent if provided
    parent = None
    if group_data.parent_id:
        result = await db.execute(
            select(DeviceGroup).where(DeviceGroup.id == group_data.parent_id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent group not found")

    # Compute path and depth
    if parent:
        path = f"{parent.path}/{group_data.name}"
        depth = parent.depth + 1
    else:
        path = f"/{group_data.name}"
        depth = 0

    group = DeviceGroup(
        name=group_data.name,
        description=group_data.description,
        parent_id=group_data.parent_id,
        path=path,
        depth=depth,
        default_workflow_id=group_data.default_workflow_id,
        auto_provision=group_data.auto_provision,
    )
    db.add(group)
    await db.flush()

    return ApiResponse(
        data=DeviceGroupResponse.from_group(group),
        message="Group created successfully",
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy -v`
Expected: PASS

**Step 5: Run all group API tests**

Run: `pytest tests/integration/test_groups_api.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): support parent_id in group creation

- Validate parent exists
- Compute path and depth from parent
- Root groups get path=/{name}, depth=0"
```

---

## Task 4: Update Get/List Group Endpoints for Hierarchy

**Files:**
- Modify: `src/api/routes/groups.py` (list_groups, get_group)
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_get_group_shows_children_count(self, client: TestClient):
        """Get group shows children count."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        client.post("/api/v1/groups", json={"name": "web", "parent_id": parent_id})
        client.post("/api/v1/groups", json={"name": "db", "parent_id": parent_id})

        response = client.get(f"/api/v1/groups/{parent_id}")
        assert response.json()["data"]["children_count"] == 2

    def test_list_groups_filter_root_only(self, client: TestClient):
        """List only root groups."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]
        client.post("/api/v1/groups", json={"name": "web", "parent_id": parent_id})
        client.post("/api/v1/groups", json={"name": "other"})

        response = client.get("/api/v1/groups?root_only=true")
        data = response.json()
        assert data["total"] == 2
        names = [g["name"] for g in data["data"]]
        assert "servers" in names
        assert "other" in names
        assert "web" not in names

    def test_list_groups_filter_by_parent(self, client: TestClient):
        """List children of a specific parent."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]
        client.post("/api/v1/groups", json={"name": "web", "parent_id": parent_id})
        client.post("/api/v1/groups", json={"name": "db", "parent_id": parent_id})
        client.post("/api/v1/groups", json={"name": "other"})

        response = client.get(f"/api/v1/groups?parent_id={parent_id}")
        data = response.json()
        assert data["total"] == 2
        names = [g["name"] for g in data["data"]]
        assert "web" in names
        assert "db" in names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_get_group_shows_children_count -v`
Expected: FAIL

**Step 3: Update list_groups and get_group endpoints**

In `src/api/routes/groups.py`:

```python
@router.get("/groups", response_model=ApiListResponse[DeviceGroupResponse])
async def list_groups(
    root_only: bool = Query(False, description="Only return root groups"),
    parent_id: str | None = Query(None, description="Filter by parent ID"),
    db: AsyncSession = Depends(get_db),
):
    """List all device groups."""
    query = select(DeviceGroup)

    if root_only:
        query = query.where(DeviceGroup.parent_id.is_(None))
    elif parent_id:
        query = query.where(DeviceGroup.parent_id == parent_id)

    result = await db.execute(query)
    groups = result.scalars().all()

    # Get node counts
    count_query = (
        select(Node.group_id, func.count(Node.id))
        .where(Node.group_id.isnot(None))
        .group_by(Node.group_id)
    )
    count_result = await db.execute(count_query)
    node_counts = dict(count_result.all())

    # Get children counts
    children_query = (
        select(DeviceGroup.parent_id, func.count(DeviceGroup.id))
        .where(DeviceGroup.parent_id.isnot(None))
        .group_by(DeviceGroup.parent_id)
    )
    children_result = await db.execute(children_query)
    children_counts = dict(children_result.all())

    return ApiListResponse(
        data=[
            DeviceGroupResponse.from_group(
                g,
                node_count=node_counts.get(g.id, 0),
                children_count=children_counts.get(g.id, 0),
            )
            for g in groups
        ],
        total=len(groups),
    )


@router.get("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get device group details."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Node count
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    # Children count
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(
            group, node_count=node_count, children_count=children_count
        )
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): add hierarchy filters to group listing

- Add root_only query param
- Add parent_id query param
- Include children_count in responses"
```

---

## Task 5: Implement Move Group (Reparent)

**Files:**
- Modify: `src/api/routes/groups.py` (update_group)
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_move_group_to_new_parent(self, client: TestClient):
        """Move group to a new parent."""
        # Create structure: servers, databases, web (under servers)
        servers_resp = client.post("/api/v1/groups", json={"name": "servers"})
        servers_id = servers_resp.json()["data"]["id"]

        db_resp = client.post("/api/v1/groups", json={"name": "databases"})
        db_id = db_resp.json()["data"]["id"]

        web_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": servers_id}
        )
        web_id = web_resp.json()["data"]["id"]

        # Move web under databases
        response = client.patch(
            f"/api/v1/groups/{web_id}",
            json={"parent_id": db_id},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["parent_id"] == db_id
        assert data["path"] == "/databases/web"
        assert data["depth"] == 1

    def test_move_group_to_root(self, client: TestClient):
        """Move group to root level."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        child_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": parent_id}
        )
        child_id = child_resp.json()["data"]["id"]

        # Move to root (parent_id = null via empty string or explicit null)
        response = client.patch(
            f"/api/v1/groups/{child_id}",
            json={"parent_id": None},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["parent_id"] is None
        assert data["path"] == "/web"
        assert data["depth"] == 0

    def test_move_group_updates_descendants(self, client: TestClient):
        """Moving group updates all descendant paths."""
        # Create: servers -> web -> prod
        servers_resp = client.post("/api/v1/groups", json={"name": "servers"})
        servers_id = servers_resp.json()["data"]["id"]

        web_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": servers_id}
        )
        web_id = web_resp.json()["data"]["id"]

        prod_resp = client.post(
            "/api/v1/groups", json={"name": "prod", "parent_id": web_id}
        )
        prod_id = prod_resp.json()["data"]["id"]

        # Create new parent
        other_resp = client.post("/api/v1/groups", json={"name": "other"})
        other_id = other_resp.json()["data"]["id"]

        # Move web under other
        client.patch(f"/api/v1/groups/{web_id}", json={"parent_id": other_id})

        # Check prod was updated
        response = client.get(f"/api/v1/groups/{prod_id}")
        data = response.json()["data"]
        assert data["path"] == "/other/web/prod"
        assert data["depth"] == 2

    def test_move_group_circular_reference_fails(self, client: TestClient):
        """Cannot move group under its own descendant."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        child_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": parent_id}
        )
        child_id = child_resp.json()["data"]["id"]

        # Try to move parent under child
        response = client.patch(
            f"/api/v1/groups/{parent_id}",
            json={"parent_id": child_id},
        )
        assert response.status_code == 400
        assert "Cannot move" in response.json()["detail"]

    def test_move_group_to_self_fails(self, client: TestClient):
        """Cannot set group as its own parent."""
        resp = client.post("/api/v1/groups", json={"name": "servers"})
        group_id = resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/groups/{group_id}",
            json={"parent_id": group_id},
        )
        assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_move_group_to_new_parent -v`
Expected: FAIL

**Step 3: Update update_group endpoint**

In `src/api/routes/groups.py`, replace update_group function:

```python
@router.patch("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def update_group(
    group_id: str,
    group_data: DeviceGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check for name conflict
    if group_data.name and group_data.name != group.name:
        existing = await db.execute(
            select(DeviceGroup).where(DeviceGroup.name == group_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Group '{group_data.name}' already exists",
            )

    # Handle parent change (reparent)
    update_data = group_data.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        new_parent_id = update_data["parent_id"]
        old_path = group.path

        # Cannot be own parent
        if new_parent_id == group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot set group as its own parent",
            )

        if new_parent_id:
            # Validate new parent exists
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == new_parent_id)
            )
            new_parent = parent_result.scalar_one_or_none()
            if not new_parent:
                raise HTTPException(status_code=404, detail="Parent group not found")

            # Prevent circular reference
            if new_parent.path.startswith(group.path + "/") or new_parent.id == group_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot move group under itself or its descendant",
                )

            # Compute new path
            new_name = update_data.get("name", group.name)
            new_path = f"{new_parent.path}/{new_name}"
            new_depth = new_parent.depth + 1
        else:
            # Moving to root
            new_name = update_data.get("name", group.name)
            new_path = f"/{new_name}"
            new_depth = 0

        # Update descendants' paths
        depth_diff = new_depth - group.depth
        descendants_result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.path.startswith(old_path + "/")
            )
        )
        descendants = descendants_result.scalars().all()
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)
            desc.depth = desc.depth + depth_diff

        group.path = new_path
        group.depth = new_depth
        group.parent_id = new_parent_id

        # Remove parent_id from update_data since we handled it
        del update_data["parent_id"]

    # Handle name change (update path if not already handled by reparent)
    if "name" in update_data and "parent_id" not in group_data.model_dump(exclude_unset=True):
        old_path = group.path
        if group.parent_id:
            # Get parent path
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == group.parent_id)
            )
            parent = parent_result.scalar_one()
            new_path = f"{parent.path}/{update_data['name']}"
        else:
            new_path = f"/{update_data['name']}"

        # Update descendants' paths
        descendants_result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.path.startswith(old_path + "/")
            )
        )
        descendants = descendants_result.scalars().all()
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)

        group.path = new_path

    # Apply remaining updates
    for field, value in update_data.items():
        setattr(group, field, value)

    await db.flush()

    # Get counts
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(
            group, node_count=node_count, children_count=children_count
        ),
        message="Group updated successfully",
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): implement group reparenting (move)

- Support changing parent_id via PATCH
- Update descendant paths on move
- Prevent circular references
- Handle rename with path updates"
```

---

## Task 6: Implement Delete with Children Check

**Files:**
- Modify: `src/api/routes/groups.py` (delete_group)
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_delete_group_with_children_fails(self, client: TestClient):
        """Cannot delete group that has children."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        client.post("/api/v1/groups", json={"name": "web", "parent_id": parent_id})

        response = client.delete(f"/api/v1/groups/{parent_id}")
        assert response.status_code == 400
        assert "children" in response.json()["detail"].lower()

    def test_delete_leaf_group_succeeds(self, client: TestClient):
        """Can delete group with no children."""
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        child_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": parent_id}
        )
        child_id = child_resp.json()["data"]["id"]

        # Delete child (leaf) should succeed
        response = client.delete(f"/api/v1/groups/{child_id}")
        assert response.status_code == 200

        # Parent now has no children, should be deletable
        response = client.delete(f"/api/v1/groups/{parent_id}")
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_delete_group_with_children_fails -v`
Expected: FAIL (currently doesn't check for children)

**Step 3: Update delete_group endpoint**

In `src/api/routes/groups.py`, replace delete_group function:

```python
@router.delete("/groups/{group_id}", response_model=ApiResponse[dict])
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check for children
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    if children_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete group with {children_count} child group(s). Delete or move children first.",
        )

    # Check for nodes
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    if node_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete group with {node_count} node(s). Remove nodes first.",
        )

    await db.delete(group)
    await db.flush()

    return ApiResponse(
        data={"id": group_id},
        message="Group deleted successfully",
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): prevent deleting groups with children

Delete now fails if group has child groups.
Must delete or move children first (RESTRICT behavior)."
```

---

## Task 7: Add Ancestors Endpoint

**Files:**
- Modify: `src/api/routes/groups.py`
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_get_ancestors(self, client: TestClient):
        """Get ancestor chain for a group."""
        # Create: servers -> web -> prod
        r1 = client.post("/api/v1/groups", json={"name": "servers"})
        id1 = r1.json()["data"]["id"]

        r2 = client.post("/api/v1/groups", json={"name": "web", "parent_id": id1})
        id2 = r2.json()["data"]["id"]

        r3 = client.post("/api/v1/groups", json={"name": "prod", "parent_id": id2})
        id3 = r3.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{id3}/ancestors")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = [g["name"] for g in data["data"]]
        assert names == ["servers", "web"]  # Ordered by depth

    def test_get_ancestors_root_group(self, client: TestClient):
        """Root group has no ancestors."""
        r = client.post("/api/v1/groups", json={"name": "servers"})
        group_id = r.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{group_id}/ancestors")
        assert response.status_code == 200
        assert response.json()["total"] == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_get_ancestors -v`
Expected: FAIL (404 - endpoint doesn't exist)

**Step 3: Add ancestors endpoint**

Add to `src/api/routes/groups.py`:

```python
@router.get("/groups/{group_id}/ancestors", response_model=ApiListResponse[DeviceGroupResponse])
async def list_ancestors(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List ancestor groups from root to parent."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Parse path to get ancestor paths
    path_parts = group.path.strip("/").split("/")[:-1]  # Exclude self

    if not path_parts:
        return ApiListResponse(data=[], total=0)

    # Build ancestor paths
    ancestor_paths = []
    current_path = ""
    for part in path_parts:
        current_path = f"{current_path}/{part}"
        ancestor_paths.append(current_path)

    # Query ancestors
    ancestors_result = await db.execute(
        select(DeviceGroup)
        .where(DeviceGroup.path.in_(ancestor_paths))
        .order_by(DeviceGroup.depth)
    )
    ancestors = ancestors_result.scalars().all()

    return ApiListResponse(
        data=[DeviceGroupResponse.from_group(a) for a in ancestors],
        total=len(ancestors),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_get_ancestors -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): add GET /groups/{id}/ancestors endpoint

Returns ancestor chain from root to parent, ordered by depth."
```

---

## Task 8: Add Descendants Endpoint

**Files:**
- Modify: `src/api/routes/groups.py`
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_get_descendants(self, client: TestClient):
        """Get all descendant groups."""
        # Create: servers -> web -> prod, staging
        r1 = client.post("/api/v1/groups", json={"name": "servers"})
        id1 = r1.json()["data"]["id"]

        r2 = client.post("/api/v1/groups", json={"name": "web", "parent_id": id1})
        id2 = r2.json()["data"]["id"]

        client.post("/api/v1/groups", json={"name": "prod", "parent_id": id2})
        client.post("/api/v1/groups", json={"name": "staging", "parent_id": id2})

        response = client.get(f"/api/v1/groups/{id1}/descendants")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        names = [g["name"] for g in data["data"]]
        assert "web" in names
        assert "prod" in names
        assert "staging" in names

    def test_get_descendants_leaf_group(self, client: TestClient):
        """Leaf group has no descendants."""
        r1 = client.post("/api/v1/groups", json={"name": "servers"})
        id1 = r1.json()["data"]["id"]

        r2 = client.post("/api/v1/groups", json={"name": "web", "parent_id": id1})
        id2 = r2.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{id2}/descendants")
        assert response.status_code == 200
        assert response.json()["total"] == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_get_descendants -v`
Expected: FAIL (404)

**Step 3: Add descendants endpoint**

Add to `src/api/routes/groups.py`:

```python
@router.get("/groups/{group_id}/descendants", response_model=ApiListResponse[DeviceGroupResponse])
async def list_descendants(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all descendant groups."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Query descendants by path prefix
    descendants_result = await db.execute(
        select(DeviceGroup)
        .where(DeviceGroup.path.startswith(group.path + "/"))
        .order_by(DeviceGroup.path)
    )
    descendants = descendants_result.scalars().all()

    return ApiListResponse(
        data=[DeviceGroupResponse.from_group(d) for d in descendants],
        total=len(descendants),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_get_descendants -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): add GET /groups/{id}/descendants endpoint

Returns all descendant groups using path prefix matching."
```

---

## Task 9: Add include_descendants to Node Listing

**Files:**
- Modify: `src/api/routes/groups.py` (list_group_nodes)
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_groups_api.py` in `TestGroupHierarchy`:

```python
    def test_list_nodes_include_descendants(self, client: TestClient):
        """List nodes including all descendants."""
        # Create hierarchy
        r1 = client.post("/api/v1/groups", json={"name": "servers"})
        id1 = r1.json()["data"]["id"]

        r2 = client.post("/api/v1/groups", json={"name": "web", "parent_id": id1})
        id2 = r2.json()["data"]["id"]

        # Add nodes at different levels
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:01", "group_id": id1})
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:02", "group_id": id2})
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:03", "group_id": id2})

        # Without include_descendants: only direct nodes
        response = client.get(f"/api/v1/groups/{id1}/nodes")
        assert response.json()["total"] == 1

        # With include_descendants: all nodes
        response = client.get(f"/api/v1/groups/{id1}/nodes?include_descendants=true")
        assert response.json()["total"] == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_list_nodes_include_descendants -v`
Expected: FAIL

**Step 3: Update list_group_nodes endpoint**

In `src/api/routes/groups.py`, replace list_group_nodes function:

```python
@router.get("/groups/{group_id}/nodes", response_model=ApiListResponse[NodeResponse])
async def list_group_nodes(
    group_id: str,
    include_descendants: bool = Query(False, description="Include nodes from descendant groups"),
    db: AsyncSession = Depends(get_db),
):
    """List nodes in a device group."""
    group_result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = group_result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if include_descendants:
        # Get all group IDs (this group + descendants)
        group_ids_query = select(DeviceGroup.id).where(
            (DeviceGroup.id == group_id) |
            (DeviceGroup.path.startswith(group.path + "/"))
        )
        query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.group_id.in_(group_ids_query))
        )
    else:
        query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.group_id == group_id)
        )

    result = await db.execute(query)
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchy::test_list_nodes_include_descendants -v`
Expected: PASS

**Step 5: Run all tests**

Run: `pytest tests/integration/test_groups_api.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/api/routes/groups.py tests/integration/test_groups_api.py
git commit -m "feat(api): add include_descendants param to group nodes endpoint

When true, returns nodes from the group and all its descendants."
```

---

## Task 10: Implement Settings Inheritance

**Files:**
- Create: `src/core/group_service.py`
- Modify: `src/api/routes/groups.py`
- Test: `tests/unit/test_group_service.py`

**Step 1: Write the failing test**

Create `tests/unit/test_group_service.py`:

```python
"""Tests for group service functions."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.models import Base, DeviceGroup
from src.core.group_service import get_effective_settings


@pytest.fixture
def engine():
    """Create in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create database session."""
    with Session(engine) as session:
        yield session


class TestEffectiveSettings:
    """Test settings inheritance."""

    def test_root_group_own_settings(self, session):
        """Root group uses its own settings."""
        group = DeviceGroup(
            name="servers",
            path="/servers",
            depth=0,
            default_workflow_id="workflow-1",
            auto_provision=True,
        )
        session.add(group)
        session.commit()

        settings = get_effective_settings(group, session)
        assert settings["effective_workflow_id"] == "workflow-1"
        assert settings["effective_auto_provision"] is True

    def test_child_inherits_from_parent(self, session):
        """Child inherits settings from parent."""
        parent = DeviceGroup(
            name="servers",
            path="/servers",
            depth=0,
            default_workflow_id="workflow-1",
            auto_provision=True,
        )
        session.add(parent)
        session.flush()

        child = DeviceGroup(
            name="web",
            path="/servers/web",
            depth=1,
            parent_id=parent.id,
            default_workflow_id=None,
            auto_provision=None,
        )
        session.add(child)
        session.commit()

        settings = get_effective_settings(child, session)
        assert settings["effective_workflow_id"] == "workflow-1"
        assert settings["effective_auto_provision"] is True

    def test_child_overrides_parent(self, session):
        """Child can override parent settings."""
        parent = DeviceGroup(
            name="servers",
            path="/servers",
            depth=0,
            default_workflow_id="workflow-1",
            auto_provision=True,
        )
        session.add(parent)
        session.flush()

        child = DeviceGroup(
            name="web",
            path="/servers/web",
            depth=1,
            parent_id=parent.id,
            default_workflow_id="workflow-2",
            auto_provision=False,
        )
        session.add(child)
        session.commit()

        settings = get_effective_settings(child, session)
        assert settings["effective_workflow_id"] == "workflow-2"
        assert settings["effective_auto_provision"] is False

    def test_grandchild_inherits_through_chain(self, session):
        """Grandchild inherits through parent chain."""
        grandparent = DeviceGroup(
            name="servers",
            path="/servers",
            depth=0,
            default_workflow_id="workflow-1",
            auto_provision=True,
        )
        session.add(grandparent)
        session.flush()

        parent = DeviceGroup(
            name="web",
            path="/servers/web",
            depth=1,
            parent_id=grandparent.id,
            default_workflow_id=None,  # Inherit
            auto_provision=False,  # Override
        )
        session.add(parent)
        session.flush()

        child = DeviceGroup(
            name="prod",
            path="/servers/web/prod",
            depth=2,
            parent_id=parent.id,
            default_workflow_id=None,
            auto_provision=None,
        )
        session.add(child)
        session.commit()

        settings = get_effective_settings(child, session)
        assert settings["effective_workflow_id"] == "workflow-1"  # From grandparent
        assert settings["effective_auto_provision"] is False  # From parent

    def test_no_settings_returns_defaults(self, session):
        """No settings in chain returns defaults."""
        group = DeviceGroup(
            name="servers",
            path="/servers",
            depth=0,
            default_workflow_id=None,
            auto_provision=None,
        )
        session.add(group)
        session.commit()

        settings = get_effective_settings(group, session)
        assert settings["effective_workflow_id"] is None
        assert settings["effective_auto_provision"] is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_group_service.py -v`
Expected: FAIL (module not found)

**Step 3: Create group_service.py**

Create `src/core/group_service.py`:

```python
"""Device group service functions."""
from sqlalchemy.orm import Session

from src.db.models import DeviceGroup


def get_effective_settings(group: DeviceGroup, db: Session) -> dict:
    """
    Compute effective settings by walking up the parent chain.

    Child settings override parent settings (simple override model).
    """
    settings = {
        "effective_workflow_id": None,
        "effective_auto_provision": False,
    }

    current = group
    while current:
        # Workflow: take first non-None value
        if settings["effective_workflow_id"] is None:
            if current.default_workflow_id is not None:
                settings["effective_workflow_id"] = current.default_workflow_id

        # auto_provision: take first explicit value (not None)
        if current.auto_provision is not None:
            settings["effective_auto_provision"] = current.auto_provision
            # Once we find an explicit value, stop looking for this setting
            # But continue for workflow if still None
            if settings["effective_workflow_id"] is not None:
                break

        # Move to parent
        if current.parent_id:
            current = db.get(DeviceGroup, current.parent_id)
        else:
            current = None

    return settings
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_group_service.py -v`
Expected: All PASS

**Step 5: Update get_group endpoint to use effective settings**

In `src/api/routes/groups.py`, update the get_group function to include effective settings:

Add import at top:
```python
from src.core.group_service import get_effective_settings
```

Update the response in get_group:
```python
@router.get("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get device group details."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Node count
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    # Children count
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    # Effective settings
    # Note: get_effective_settings expects sync session, but we have async
    # For now, compute inline. In production, refactor to async.
    effective = {"effective_workflow_id": None, "effective_auto_provision": False}
    current = group
    while current:
        if effective["effective_workflow_id"] is None and current.default_workflow_id:
            effective["effective_workflow_id"] = current.default_workflow_id
        if current.auto_provision is not None:
            effective["effective_auto_provision"] = current.auto_provision
            if effective["effective_workflow_id"] is not None:
                break
        if current.parent_id:
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == current.parent_id)
            )
            current = parent_result.scalar_one_or_none()
        else:
            current = None

    return ApiResponse(
        data=DeviceGroupResponse.from_group(
            group,
            node_count=node_count,
            children_count=children_count,
            effective_workflow_id=effective["effective_workflow_id"],
            effective_auto_provision=effective["effective_auto_provision"],
        )
    )
```

**Step 6: Commit**

```bash
git add src/core/group_service.py tests/unit/test_group_service.py src/api/routes/groups.py
git commit -m "feat(core): implement settings inheritance for device groups

- Add get_effective_settings function
- Walk up parent chain, first non-null wins
- Include effective settings in GET /groups/{id} response"
```

---

## Task 11: Final Integration Test

**Files:**
- Test: `tests/integration/test_groups_api.py`

**Step 1: Write comprehensive integration test**

Add to `tests/integration/test_groups_api.py`:

```python
class TestGroupHierarchyIntegration:
    """Full integration test of hierarchy features."""

    def test_full_hierarchy_workflow(self, client: TestClient):
        """Test complete hierarchy workflow."""
        # 1. Create hierarchy: datacenter -> servers -> web -> prod
        dc = client.post("/api/v1/groups", json={
            "name": "datacenter",
            "default_workflow_id": "default-workflow",
            "auto_provision": False,
        })
        dc_id = dc.json()["data"]["id"]

        servers = client.post("/api/v1/groups", json={
            "name": "servers",
            "parent_id": dc_id,
            "auto_provision": True,  # Override
        })
        servers_id = servers.json()["data"]["id"]

        web = client.post("/api/v1/groups", json={
            "name": "web",
            "parent_id": servers_id,
        })
        web_id = web.json()["data"]["id"]

        prod = client.post("/api/v1/groups", json={
            "name": "prod",
            "parent_id": web_id,
            "default_workflow_id": "prod-workflow",  # Override
        })
        prod_id = prod.json()["data"]["id"]

        # 2. Verify paths and depths
        resp = client.get(f"/api/v1/groups/{prod_id}")
        data = resp.json()["data"]
        assert data["path"] == "/datacenter/servers/web/prod"
        assert data["depth"] == 3

        # 3. Verify inheritance
        assert data["effective_workflow_id"] == "prod-workflow"  # Own
        assert data["effective_auto_provision"] is True  # From servers

        # 4. Add nodes at different levels
        client.post("/api/v1/nodes", json={
            "mac_address": "00:00:00:00:00:01",
            "group_id": servers_id,
        })
        client.post("/api/v1/nodes", json={
            "mac_address": "00:00:00:00:00:02",
            "group_id": prod_id,
        })

        # 5. Query with include_descendants
        resp = client.get(f"/api/v1/groups/{dc_id}/nodes?include_descendants=true")
        assert resp.json()["total"] == 2

        # 6. Get ancestors
        resp = client.get(f"/api/v1/groups/{prod_id}/ancestors")
        names = [g["name"] for g in resp.json()["data"]]
        assert names == ["datacenter", "servers", "web"]

        # 7. Get descendants
        resp = client.get(f"/api/v1/groups/{dc_id}/descendants")
        assert resp.json()["total"] == 3

        # 8. Move group
        other = client.post("/api/v1/groups", json={"name": "other"})
        other_id = other.json()["data"]["id"]

        client.patch(f"/api/v1/groups/{web_id}", json={"parent_id": other_id})

        # Verify prod path updated
        resp = client.get(f"/api/v1/groups/{prod_id}")
        assert resp.json()["data"]["path"] == "/other/web/prod"

        # 9. Delete leaf, then parent
        client.delete(f"/api/v1/groups/{prod_id}")
        client.delete(f"/api/v1/groups/{web_id}")

        resp = client.get(f"/api/v1/groups/{other_id}/descendants")
        assert resp.json()["total"] == 0
```

**Step 2: Run the integration test**

Run: `pytest tests/integration/test_groups_api.py::TestGroupHierarchyIntegration -v`
Expected: PASS

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/integration/test_groups_api.py
git commit -m "test: add comprehensive hierarchy integration test

Tests full workflow: create, inherit, query, move, delete."
```

---

## Summary

**Commits in order:**
1. `feat(models): add hierarchy fields to DeviceGroup`
2. `feat(schemas): add hierarchy fields to DeviceGroup schemas`
3. `feat(api): support parent_id in group creation`
4. `feat(api): add hierarchy filters to group listing`
5. `feat(api): implement group reparenting (move)`
6. `feat(api): prevent deleting groups with children`
7. `feat(api): add GET /groups/{id}/ancestors endpoint`
8. `feat(api): add GET /groups/{id}/descendants endpoint`
9. `feat(api): add include_descendants param to group nodes endpoint`
10. `feat(core): implement settings inheritance for device groups`
11. `test: add comprehensive hierarchy integration test`

**Files modified:**
- `src/db/models.py`
- `src/api/schemas.py`
- `src/api/routes/groups.py`
- `src/core/group_service.py` (new)
- `tests/unit/test_models.py`
- `tests/unit/test_schemas.py`
- `tests/unit/test_group_service.py` (new)
- `tests/integration/test_groups_api.py`