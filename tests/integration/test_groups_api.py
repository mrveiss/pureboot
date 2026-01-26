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
