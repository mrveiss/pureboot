"""Integration tests for node API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestNodesCRUD:
    """Test node CRUD operations."""

    def test_create_node(self, client: TestClient):
        """Create a new node."""
        response = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["mac_address"] == "00:11:22:33:44:55"
        assert data["data"]["state"] == "discovered"

    def test_create_node_with_hardware_info(self, client: TestClient):
        """Create node with hardware information."""
        response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "00:11:22:33:44:55",
                "vendor": "Dell Inc.",
                "model": "PowerEdge R740",
                "serial_number": "ABC123",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["vendor"] == "Dell Inc."
        assert data["model"] == "PowerEdge R740"
        assert data["serial_number"] == "ABC123"

    def test_create_duplicate_mac_fails(self, client: TestClient):
        """Cannot create node with duplicate MAC."""
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        response = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        assert response.status_code == 409

    def test_list_nodes(self, client: TestClient):
        """List all nodes."""
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:66"})

        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_get_node(self, client: TestClient):
        """Get node by ID."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == node_id

    def test_get_nonexistent_node(self, client: TestClient):
        """Get nonexistent node returns 404."""
        response = client.get("/api/v1/nodes/nonexistent-id")
        assert response.status_code == 404

    def test_update_node(self, client: TestClient):
        """Update node metadata."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"hostname": "webserver-01"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["hostname"] == "webserver-01"

    def test_retire_node(self, client: TestClient):
        """Retire a node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "retired"


class TestNodeStateTransitions:
    """Test node state transitions."""

    def test_valid_transition(self, client: TestClient):
        """Valid state transition succeeds."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "pending"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "pending"

    def test_invalid_transition_fails(self, client: TestClient):
        """Invalid state transition fails."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "active"},
        )
        assert response.status_code == 400
        assert "Invalid state transition" in response.json()["detail"]


class TestNodeTags:
    """Test node tagging."""

    def test_add_tag(self, client: TestClient):
        """Add tag to node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.post(
            f"/api/v1/nodes/{node_id}/tags",
            json={"tag": "production"},
        )
        assert response.status_code == 200
        assert "production" in response.json()["data"]["tags"]

    def test_remove_tag(self, client: TestClient):
        """Remove tag from node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]
        client.post(f"/api/v1/nodes/{node_id}/tags", json={"tag": "production"})

        response = client.delete(f"/api/v1/nodes/{node_id}/tags/production")
        assert response.status_code == 200
        assert "production" not in response.json()["data"]["tags"]

    def test_filter_by_tag(self, client: TestClient):
        """Filter nodes by tag."""
        resp1 = client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        resp2 = client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:66"})
        node1_id = resp1.json()["data"]["id"]

        client.post(f"/api/v1/nodes/{node1_id}/tags", json={"tag": "production"})

        response = client.get("/api/v1/nodes?tag=production")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["data"][0]["id"] == node1_id
