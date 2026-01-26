"""Integration tests for Raspberry Pi node management."""
from fastapi.testclient import TestClient


class TestPiNodeAPI:
    """Test Pi node API endpoints."""

    def test_create_pi_node(self, client: TestClient):
        """Create a Raspberry Pi node via API."""
        response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
                "serial_number": "d83add36",
                "pi_model": "pi4",
                "vendor": "Raspberry Pi Foundation",
                "model": "Raspberry Pi 4 Model B",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["arch"] == "aarch64"
        assert data["boot_mode"] == "pi"
        assert data["pi_model"] == "pi4"
        assert data["serial_number"] == "d83add36"
        assert data["vendor"] == "Raspberry Pi Foundation"
        assert data["model"] == "Raspberry Pi 4 Model B"

    def test_create_pi_node_minimal(self, client: TestClient):
        """Create Pi node with minimal required fields."""
        response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:aa:bb:cc",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["arch"] == "aarch64"
        assert data["boot_mode"] == "pi"
        assert data["pi_model"] is None

    def test_update_pi_node(self, client: TestClient):
        """Update Pi node's pi_model field."""
        # Create node
        create_response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )
        assert create_response.status_code == 201
        node_id = create_response.json()["data"]["id"]

        # Update pi_model
        update_response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"pi_model": "pi4"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["pi_model"] == "pi4"

    def test_update_pi_node_serial_number(self, client: TestClient):
        """Update Pi node's serial number."""
        # Create node
        create_response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )
        node_id = create_response.json()["data"]["id"]

        # Update serial_number
        update_response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"serial_number": "d83add36"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["serial_number"] == "d83add36"

    def test_list_pi_nodes_by_arch(self, client: TestClient):
        """Filter nodes by aarch64 architecture."""
        # Create x86 node
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "arch": "x86_64"},
        )
        # Create Pi node
        client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )

        # List all nodes
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert response.json()["total"] == 2

        # Filter by arch (if implemented)
        # This tests the groundwork - actual filtering may be added later

    def test_pi_node_state_lifecycle(self, client: TestClient):
        """Test complete state lifecycle for a Pi node."""
        # Create Pi node in discovered state
        create_response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
                "pi_model": "pi4",
            },
        )
        assert create_response.status_code == 201
        node_id = create_response.json()["data"]["id"]
        assert create_response.json()["data"]["state"] == "discovered"

        # Transition to pending
        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "pending"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "pending"

        # Transition to installing
        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "installing"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "installing"

        # Transition to installed
        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "installed"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "installed"

        # Transition to active
        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "active"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "active"

    def test_pi_node_with_tags(self, client: TestClient):
        """Test tagging a Pi node."""
        # Create Pi node
        create_response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
                "pi_model": "pi4",
            },
        )
        node_id = create_response.json()["data"]["id"]

        # Add raspberry-pi tag
        response = client.post(
            f"/api/v1/nodes/{node_id}/tags",
            json={"tag": "raspberry-pi"},
        )
        assert response.status_code == 200
        assert "raspberry-pi" in response.json()["data"]["tags"]

        # Add arm64 tag
        response = client.post(
            f"/api/v1/nodes/{node_id}/tags",
            json={"tag": "arm64"},
        )
        assert response.status_code == 200
        tags = response.json()["data"]["tags"]
        assert "raspberry-pi" in tags
        assert "arm64" in tags

    def test_pi_node_different_models(self, client: TestClient):
        """Test creating nodes with different Pi models."""
        pi_models = [
            ("dc:a6:32:11:11:11", "pi3"),
            ("dc:a6:32:22:22:22", "pi4"),
            ("dc:a6:32:33:33:33", "pi5"),
            ("e4:5f:01:44:44:44", "pi400"),
            ("dc:a6:32:55:55:55", "cm4"),
        ]

        for mac, model in pi_models:
            response = client.post(
                "/api/v1/nodes",
                json={
                    "mac_address": mac,
                    "arch": "aarch64",
                    "boot_mode": "pi",
                    "pi_model": model,
                },
            )
            assert response.status_code == 201
            assert response.json()["data"]["pi_model"] == model

        # Verify all nodes were created
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert response.json()["total"] == 5

    def test_retire_pi_node(self, client: TestClient):
        """Test retiring a Pi node."""
        # Create Pi node
        create_response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
                "pi_model": "pi4",
            },
        )
        node_id = create_response.json()["data"]["id"]

        # Retire the node
        response = client.delete(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "retired"