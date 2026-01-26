"""Integration tests for device group API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestGroupsCRUD:
    """Test device group CRUD operations."""

    def test_create_group(self, client: TestClient):
        """Create a new device group."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "webservers", "description": "Web servers"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "webservers"

    def test_create_duplicate_name_fails(self, client: TestClient):
        """Cannot create group with duplicate name."""
        client.post("/api/v1/groups", json={"name": "webservers"})
        response = client.post("/api/v1/groups", json={"name": "webservers"})
        assert response.status_code == 409

    def test_list_groups(self, client: TestClient):
        """List all groups."""
        client.post("/api/v1/groups", json={"name": "webservers"})
        client.post("/api/v1/groups", json={"name": "databases"})

        response = client.get("/api/v1/groups")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_get_group(self, client: TestClient):
        """Get group by ID."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == group_id

    def test_update_group(self, client: TestClient):
        """Update group."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/groups/{group_id}",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["description"] == "Updated description"

    def test_delete_empty_group(self, client: TestClient):
        """Delete empty group succeeds."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 200

    def test_delete_group_with_nodes_fails(self, client: TestClient):
        """Cannot delete group with nodes."""
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )

        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 400
        assert "Cannot delete group" in response.json()["detail"]


class TestGroupNodes:
    """Test group-node relationships."""

    def test_list_group_nodes(self, client: TestClient):
        """List nodes in a group."""
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:66", "group_id": group_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:77"},
        )

        response = client.get(f"/api/v1/groups/{group_id}/nodes")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_group_node_count(self, client: TestClient):
        """Group shows correct node count."""
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )

        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.json()["data"]["node_count"] == 1

    def test_assign_node_to_group(self, client: TestClient):
        """Assign existing node to group."""
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]
        node_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = node_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"group_id": group_id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["group_id"] == group_id


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

    def test_delete_group_with_children_fails(self, client: TestClient):
        """Cannot delete group that has child groups."""
        # Create parent
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        # Create child
        client.post("/api/v1/groups", json={"name": "web", "parent_id": parent_id})

        # Try to delete parent
        response = client.delete(f"/api/v1/groups/{parent_id}")
        assert response.status_code == 400
        assert "Cannot delete group" in response.json()["detail"]
        assert "child" in response.json()["detail"].lower()

    def test_delete_leaf_group_succeeds(self, client: TestClient):
        """Delete a leaf group (no children) succeeds."""
        # Create parent
        parent_resp = client.post("/api/v1/groups", json={"name": "servers"})
        parent_id = parent_resp.json()["data"]["id"]

        # Create child
        child_resp = client.post(
            "/api/v1/groups", json={"name": "web", "parent_id": parent_id}
        )
        child_id = child_resp.json()["data"]["id"]

        # Delete child (leaf) should succeed
        response = client.delete(f"/api/v1/groups/{child_id}")
        assert response.status_code == 200

        # Verify it's gone
        get_resp = client.get(f"/api/v1/groups/{child_id}")
        assert get_resp.status_code == 404

    def test_get_ancestors(self, client: TestClient):
        """Get ancestors returns chain from parent to root."""
        # Create: root -> mid -> leaf
        root_resp = client.post("/api/v1/groups", json={"name": "root"})
        root_id = root_resp.json()["data"]["id"]

        mid_resp = client.post(
            "/api/v1/groups", json={"name": "mid", "parent_id": root_id}
        )
        mid_id = mid_resp.json()["data"]["id"]

        leaf_resp = client.post(
            "/api/v1/groups", json={"name": "leaf", "parent_id": mid_id}
        )
        leaf_id = leaf_resp.json()["data"]["id"]

        # Get ancestors of leaf
        response = client.get(f"/api/v1/groups/{leaf_id}/ancestors")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Order: immediate parent first, then grandparent
        names = [g["name"] for g in data["data"]]
        assert names == ["mid", "root"]

    def test_get_ancestors_root_group(self, client: TestClient):
        """Root group has no ancestors."""
        resp = client.post("/api/v1/groups", json={"name": "root"})
        group_id = resp.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{group_id}/ancestors")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_get_descendants(self, client: TestClient):
        """Get descendants returns all groups under a parent."""
        # Create: root -> mid -> leaf1, leaf2
        root_resp = client.post("/api/v1/groups", json={"name": "root"})
        root_id = root_resp.json()["data"]["id"]

        mid_resp = client.post(
            "/api/v1/groups", json={"name": "mid", "parent_id": root_id}
        )
        mid_id = mid_resp.json()["data"]["id"]

        client.post("/api/v1/groups", json={"name": "leaf1", "parent_id": mid_id})
        client.post("/api/v1/groups", json={"name": "leaf2", "parent_id": mid_id})

        # Create sibling not under root
        client.post("/api/v1/groups", json={"name": "other"})

        # Get descendants of root
        response = client.get(f"/api/v1/groups/{root_id}/descendants")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3  # mid, leaf1, leaf2

        names = {g["name"] for g in data["data"]}
        assert names == {"mid", "leaf1", "leaf2"}

    def test_get_descendants_leaf_group(self, client: TestClient):
        """Leaf group has no descendants."""
        root_resp = client.post("/api/v1/groups", json={"name": "root"})
        root_id = root_resp.json()["data"]["id"]

        leaf_resp = client.post(
            "/api/v1/groups", json={"name": "leaf", "parent_id": root_id}
        )
        leaf_id = leaf_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{leaf_id}/descendants")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_list_group_nodes_include_descendants(self, client: TestClient):
        """List nodes including descendants."""
        # Create hierarchy: servers -> web -> prod
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

        # Add nodes at each level
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:01", "group_id": servers_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:02", "group_id": web_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:03", "group_id": prod_id},
        )

        # Without include_descendants - only direct nodes
        response = client.get(f"/api/v1/groups/{servers_id}/nodes")
        assert response.json()["total"] == 1

        # With include_descendants - all nodes under hierarchy
        response = client.get(
            f"/api/v1/groups/{servers_id}/nodes?include_descendants=true"
        )
        assert response.json()["total"] == 3

        # Check specific level
        response = client.get(
            f"/api/v1/groups/{web_id}/nodes?include_descendants=true"
        )
        assert response.json()["total"] == 2  # web + prod nodes


class TestGroupSettingsInheritance:
    """Test device group settings inheritance."""

    def test_effective_auto_provision_inherits_from_parent(self, client: TestClient):
        """Child group inherits auto_provision from parent."""
        # Create parent with auto_provision=True
        parent_resp = client.post(
            "/api/v1/groups",
            json={"name": "servers", "auto_provision": True},
        )
        parent_id = parent_resp.json()["data"]["id"]

        # Create child without auto_provision (None = inherit)
        child_resp = client.post(
            "/api/v1/groups",
            json={"name": "web", "parent_id": parent_id},
        )
        child_id = child_resp.json()["data"]["id"]

        # Get child - should inherit parent's auto_provision
        response = client.get(f"/api/v1/groups/{child_id}")
        data = response.json()["data"]
        assert data["auto_provision"] is None  # Own value is None
        assert data["effective_auto_provision"] is True  # Inherited from parent

    def test_effective_auto_provision_child_overrides(self, client: TestClient):
        """Child's own value overrides parent's."""
        # Parent has auto_provision=True
        parent_resp = client.post(
            "/api/v1/groups",
            json={"name": "servers", "auto_provision": True},
        )
        parent_id = parent_resp.json()["data"]["id"]

        # Child explicitly sets auto_provision=False
        child_resp = client.post(
            "/api/v1/groups",
            json={"name": "web", "parent_id": parent_id, "auto_provision": False},
        )
        child_id = child_resp.json()["data"]["id"]

        # Get child - should use own value
        response = client.get(f"/api/v1/groups/{child_id}")
        data = response.json()["data"]
        assert data["auto_provision"] is False
        assert data["effective_auto_provision"] is False

    def test_effective_workflow_inherits_from_parent(self, client: TestClient):
        """Child group inherits workflow_id from parent."""
        # Create parent with default_workflow_id
        parent_resp = client.post(
            "/api/v1/groups",
            json={"name": "servers", "default_workflow_id": "workflow-123"},
        )
        parent_id = parent_resp.json()["data"]["id"]

        # Create child without workflow
        child_resp = client.post(
            "/api/v1/groups",
            json={"name": "web", "parent_id": parent_id},
        )
        child_id = child_resp.json()["data"]["id"]

        # Get child - should inherit parent's workflow
        response = client.get(f"/api/v1/groups/{child_id}")
        data = response.json()["data"]
        assert data["default_workflow_id"] is None  # Own value is None
        assert data["effective_workflow_id"] == "workflow-123"  # Inherited

    def test_effective_settings_deep_inheritance(self, client: TestClient):
        """Settings inherit through multiple levels."""
        # Create: root (auto=True, workflow=123) -> mid (none) -> leaf (none)
        root_resp = client.post(
            "/api/v1/groups",
            json={
                "name": "root",
                "auto_provision": True,
                "default_workflow_id": "workflow-123",
            },
        )
        root_id = root_resp.json()["data"]["id"]

        mid_resp = client.post(
            "/api/v1/groups",
            json={"name": "mid", "parent_id": root_id},
        )
        mid_id = mid_resp.json()["data"]["id"]

        leaf_resp = client.post(
            "/api/v1/groups",
            json={"name": "leaf", "parent_id": mid_id},
        )
        leaf_id = leaf_resp.json()["data"]["id"]

        # Leaf should inherit from root through mid
        response = client.get(f"/api/v1/groups/{leaf_id}")
        data = response.json()["data"]
        assert data["effective_auto_provision"] is True
        assert data["effective_workflow_id"] == "workflow-123"

    def test_effective_settings_mid_level_override(self, client: TestClient):
        """Mid-level group can override root settings."""
        # Create: root (workflow=root-wf) -> mid (workflow=mid-wf) -> leaf (none)
        root_resp = client.post(
            "/api/v1/groups",
            json={"name": "root", "default_workflow_id": "root-wf"},
        )
        root_id = root_resp.json()["data"]["id"]

        mid_resp = client.post(
            "/api/v1/groups",
            json={
                "name": "mid",
                "parent_id": root_id,
                "default_workflow_id": "mid-wf",
            },
        )
        mid_id = mid_resp.json()["data"]["id"]

        leaf_resp = client.post(
            "/api/v1/groups",
            json={"name": "leaf", "parent_id": mid_id},
        )
        leaf_id = leaf_resp.json()["data"]["id"]

        # Leaf should inherit from mid (closest ancestor with value)
        response = client.get(f"/api/v1/groups/{leaf_id}")
        data = response.json()["data"]
        assert data["effective_workflow_id"] == "mid-wf"


class TestGroupHierarchyComplete:
    """Complete integration test for hierarchical device groups."""

    def test_complete_hierarchy_workflow(self, client: TestClient):
        """Full workflow test: create hierarchy, add nodes, query, move, delete."""
        # === Step 1: Create hierarchy ===
        # datacenter (auto_provision=True, workflow=dc-wf)
        #   ├── rack1
        #   │   ├── servers (workflow=servers-wf)
        #   │   └── network
        #   └── rack2

        dc_resp = client.post(
            "/api/v1/groups",
            json={
                "name": "datacenter",
                "auto_provision": True,
                "default_workflow_id": "dc-wf",
            },
        )
        assert dc_resp.status_code == 201
        dc_id = dc_resp.json()["data"]["id"]
        assert dc_resp.json()["data"]["path"] == "/datacenter"
        assert dc_resp.json()["data"]["depth"] == 0

        rack1_resp = client.post(
            "/api/v1/groups",
            json={"name": "rack1", "parent_id": dc_id},
        )
        rack1_id = rack1_resp.json()["data"]["id"]
        assert rack1_resp.json()["data"]["path"] == "/datacenter/rack1"
        assert rack1_resp.json()["data"]["depth"] == 1

        servers_resp = client.post(
            "/api/v1/groups",
            json={
                "name": "servers",
                "parent_id": rack1_id,
                "default_workflow_id": "servers-wf",
            },
        )
        servers_id = servers_resp.json()["data"]["id"]
        assert servers_resp.json()["data"]["path"] == "/datacenter/rack1/servers"

        network_resp = client.post(
            "/api/v1/groups",
            json={"name": "network", "parent_id": rack1_id},
        )
        network_id = network_resp.json()["data"]["id"]

        rack2_resp = client.post(
            "/api/v1/groups",
            json={"name": "rack2", "parent_id": dc_id},
        )
        rack2_id = rack2_resp.json()["data"]["id"]

        # === Step 2: Verify hierarchy queries ===
        # List root groups
        root_resp = client.get("/api/v1/groups?root_only=true")
        assert root_resp.json()["total"] == 1
        assert root_resp.json()["data"][0]["name"] == "datacenter"

        # List children of datacenter
        children_resp = client.get(f"/api/v1/groups?parent_id={dc_id}")
        assert children_resp.json()["total"] == 2

        # Get descendants of datacenter
        desc_resp = client.get(f"/api/v1/groups/{dc_id}/descendants")
        assert desc_resp.json()["total"] == 4  # rack1, rack2, servers, network

        # Get ancestors of servers
        anc_resp = client.get(f"/api/v1/groups/{servers_id}/ancestors")
        assert anc_resp.json()["total"] == 2  # rack1, datacenter
        names = [g["name"] for g in anc_resp.json()["data"]]
        assert names == ["rack1", "datacenter"]

        # === Step 3: Add nodes and query ===
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:01", "group_id": dc_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:02", "group_id": servers_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:03", "group_id": servers_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:04", "group_id": network_id},
        )

        # Direct nodes in datacenter
        nodes_resp = client.get(f"/api/v1/groups/{dc_id}/nodes")
        assert nodes_resp.json()["total"] == 1

        # All nodes under datacenter hierarchy
        all_nodes_resp = client.get(
            f"/api/v1/groups/{dc_id}/nodes?include_descendants=true"
        )
        assert all_nodes_resp.json()["total"] == 4

        # Nodes under rack1 hierarchy
        rack1_nodes_resp = client.get(
            f"/api/v1/groups/{rack1_id}/nodes?include_descendants=true"
        )
        assert rack1_nodes_resp.json()["total"] == 3

        # === Step 4: Verify settings inheritance ===
        # Servers should inherit auto_provision from datacenter
        # but use own workflow
        servers_detail = client.get(f"/api/v1/groups/{servers_id}")
        data = servers_detail.json()["data"]
        assert data["effective_auto_provision"] is True  # Inherited from datacenter
        assert data["effective_workflow_id"] == "servers-wf"  # Own value

        # Network should inherit both
        network_detail = client.get(f"/api/v1/groups/{network_id}")
        data = network_detail.json()["data"]
        assert data["effective_auto_provision"] is True  # Inherited
        assert data["effective_workflow_id"] == "dc-wf"  # Inherited

        # === Step 5: Move group and verify updates ===
        # Move servers from rack1 to rack2
        move_resp = client.patch(
            f"/api/v1/groups/{servers_id}",
            json={"parent_id": rack2_id},
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["data"]["path"] == "/datacenter/rack2/servers"

        # Verify descendants updated too (though servers has none)
        new_desc = client.get(f"/api/v1/groups/{rack1_id}/descendants")
        # Only network now under rack1
        assert new_desc.json()["total"] == 1
        assert new_desc.json()["data"][0]["name"] == "network"

        # === Step 6: Delete hierarchy from bottom up ===
        # Can't delete rack1 because it has children
        del_rack1 = client.delete(f"/api/v1/groups/{rack1_id}")
        assert del_rack1.status_code == 400
        assert "child" in del_rack1.json()["detail"].lower()

        # Delete network (no children, but has nodes)
        del_network = client.delete(f"/api/v1/groups/{network_id}")
        assert del_network.status_code == 400
        assert "node" in del_network.json()["detail"].lower()

        # Move nodes out of network first
        nodes_in_network = client.get(f"/api/v1/groups/{network_id}/nodes")
        for node in nodes_in_network.json()["data"]:
            client.patch(f"/api/v1/nodes/{node['id']}", json={"group_id": None})

        # Now delete network
        del_network2 = client.delete(f"/api/v1/groups/{network_id}")
        assert del_network2.status_code == 200

        # Now can delete rack1
        del_rack1_2 = client.delete(f"/api/v1/groups/{rack1_id}")
        assert del_rack1_2.status_code == 200
