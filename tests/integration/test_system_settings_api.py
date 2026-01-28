"""Integration tests for system settings API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestSystemSettings:
    """Test system settings API endpoints."""

    def test_get_settings_returns_defaults_when_empty(self, client: TestClient):
        """GET /api/v1/system/settings returns default values when no settings exist."""
        response = client.get("/api/v1/system/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["default_boot_backend_id"] is None
        assert data["data"]["file_serving_bandwidth_mbps"] == 1000  # DEFAULT_BANDWIDTH_MBPS

    def test_set_default_boot_backend_id(self, client: TestClient):
        """PATCH /api/v1/system/settings can set default_boot_backend_id to valid backend."""
        # First create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-nfs-backend",
                "type": "nfs",
                "config": {
                    "server": "nfs.example.com",
                    "export_path": "/exports/boot",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set the default boot backend
        response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["default_boot_backend_id"] == backend_id

        # Verify it persists
        get_response = client.get("/api/v1/system/settings")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["default_boot_backend_id"] == backend_id

    def test_set_nonexistent_backend_returns_404(self, client: TestClient):
        """PATCH /api/v1/system/settings with nonexistent backend ID returns 404."""
        response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": "nonexistent-backend-id"},
        )
        assert response.status_code == 404
        assert "Storage backend not found" in response.json()["detail"]

    def test_set_file_serving_bandwidth(self, client: TestClient):
        """PATCH /api/v1/system/settings can set file_serving_bandwidth_mbps."""
        response = client.patch(
            "/api/v1/system/settings",
            json={"file_serving_bandwidth_mbps": 500},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["file_serving_bandwidth_mbps"] == 500

        # Verify it persists
        get_response = client.get("/api/v1/system/settings")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["file_serving_bandwidth_mbps"] == 500

    def test_clear_default_boot_backend_id(self, client: TestClient):
        """PATCH /api/v1/system/settings can clear default_boot_backend_id by setting to null."""
        # First create and set a backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-nfs-backend",
                "type": "nfs",
                "config": {
                    "server": "nfs.example.com",
                    "export_path": "/exports/boot",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set the default boot backend
        set_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert set_response.status_code == 200
        assert set_response.json()["data"]["default_boot_backend_id"] == backend_id

        # Clear the default boot backend by setting to null
        clear_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": None},
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["data"]["default_boot_backend_id"] is None

        # Verify it's cleared
        get_response = client.get("/api/v1/system/settings")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["default_boot_backend_id"] is None

    def test_bandwidth_validation_minimum(self, client: TestClient):
        """PATCH /api/v1/system/settings rejects bandwidth below minimum (1)."""
        response = client.patch(
            "/api/v1/system/settings",
            json={"file_serving_bandwidth_mbps": 0},
        )
        assert response.status_code == 422  # Validation error

    def test_bandwidth_validation_maximum(self, client: TestClient):
        """PATCH /api/v1/system/settings rejects bandwidth above maximum (100000)."""
        response = client.patch(
            "/api/v1/system/settings",
            json={"file_serving_bandwidth_mbps": 100001},
        )
        assert response.status_code == 422  # Validation error

    def test_update_multiple_settings(self, client: TestClient):
        """PATCH /api/v1/system/settings can update multiple settings at once."""
        # First create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-nfs-backend",
                "type": "nfs",
                "config": {
                    "server": "nfs.example.com",
                    "export_path": "/exports/boot",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Update both settings at once
        response = client.patch(
            "/api/v1/system/settings",
            json={
                "default_boot_backend_id": backend_id,
                "file_serving_bandwidth_mbps": 2000,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["default_boot_backend_id"] == backend_id
        assert data["data"]["file_serving_bandwidth_mbps"] == 2000
