"""Integration tests for boot files API endpoint."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


class TestBootFilesEndpoint:
    """Test boot files serving endpoint."""

    def test_no_default_backend_returns_503(self, client: TestClient):
        """GET /api/v1/files/{path} returns 503 when no default backend configured."""
        response = client.get("/api/v1/files/boot/vmlinuz")
        assert response.status_code == 503
        assert "No default boot backend configured" in response.json()["detail"]

    def test_nonexistent_backend_returns_503(self, client: TestClient):
        """GET /api/v1/files/{path} returns 503 when default backend ID doesn't exist."""
        # Set a non-existent backend ID as default
        # First we need to create and then delete a backend, or just set an invalid ID
        # We'll patch the system settings to return a fake ID

        with patch(
            "src.api.routes.boot_files.get_default_boot_backend_id",
            new=AsyncMock(return_value="nonexistent-backend-id"),
        ):
            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 503
            assert "not found" in response.json()["detail"]

    def test_file_not_found_returns_404(self, client: TestClient):
        """GET /api/v1/files/{path} returns 404 when file doesn't exist."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Mock the download_file to raise FileNotFoundError
        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                side_effect=FileNotFoundError("File not found: /boot/vmlinuz")
            )
            mock_get_service.return_value = mock_service

            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_successful_file_serving(self, client: TestClient):
        """GET /api/v1/files/{path} returns file with correct headers."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend-2",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Create a mock content iterator
        async def mock_content_iter():
            yield b"test file content"

        # Mock the download_file to return test content
        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 17)
            )
            mock_get_service.return_value = mock_service

            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/octet-stream"
            assert response.headers["content-length"] == "17"
            assert response.headers["content-disposition"] == 'inline; filename="vmlinuz"'
            assert response.content == b"test file content"

    def test_file_serving_with_checksum(self, client: TestClient):
        """GET /api/v1/files/{path} includes checksum headers when available."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend-3",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Create a mock content iterator
        async def mock_content_iter():
            yield b"test file content"

        test_checksum = "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd"

        # Mock download_file and get_file_checksum
        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service, patch(
            "src.api.routes.boot_files.get_file_checksum",
            new=AsyncMock(return_value=test_checksum),
        ):
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 17)
            )
            mock_get_service.return_value = mock_service

            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 200
            assert response.headers["etag"] == f'"sha256:{test_checksum}"'
            assert response.headers["x-checksum-sha256"] == test_checksum

    def test_file_serving_no_checksum(self, client: TestClient):
        """GET /api/v1/files/{path} works without checksum when not available."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend-4",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Create a mock content iterator
        async def mock_content_iter():
            yield b"test file content"

        # Mock download_file with no checksum available
        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service, patch(
            "src.api.routes.boot_files.get_file_checksum",
            new=AsyncMock(return_value=None),
        ):
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 17)
            )
            mock_get_service.return_value = mock_service

            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 200
            # No checksum headers when checksum is not available
            assert "etag" not in response.headers
            assert "x-checksum-sha256" not in response.headers

    def test_path_normalization(self, client: TestClient):
        """GET /api/v1/files/{path} normalizes paths correctly."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend-5",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Create a mock content iterator
        async def mock_content_iter():
            yield b"content"

        # Mock download_file and capture the path passed to it
        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 7)
            )
            mock_get_service.return_value = mock_service

            # Test with leading slash
            response = client.get("/api/v1/files/boot/vmlinuz")
            assert response.status_code == 200
            mock_service.download_file.assert_called_with("/boot/vmlinuz")

            # Reset mock
            mock_service.download_file.reset_mock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 7)
            )

            # Test without leading slash (should be normalized)
            response = client.get("/api/v1/files/vmlinuz")
            assert response.status_code == 200
            mock_service.download_file.assert_called_with("/vmlinuz")

    def test_nested_path(self, client: TestClient):
        """GET /api/v1/files/{path} handles nested paths correctly."""
        # Create a storage backend
        backend_response = client.post(
            "/api/v1/storage/backends",
            json={
                "name": "test-http-backend-6",
                "type": "http",
                "config": {
                    "base_url": "http://example.com/files",
                },
            },
        )
        assert backend_response.status_code == 201
        backend_id = backend_response.json()["data"]["id"]

        # Set as default backend
        settings_response = client.patch(
            "/api/v1/system/settings",
            json={"default_boot_backend_id": backend_id},
        )
        assert settings_response.status_code == 200

        # Create a mock content iterator
        async def mock_content_iter():
            yield b"content"

        with patch(
            "src.api.routes.boot_files.get_backend_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.download_file = AsyncMock(
                return_value=(mock_content_iter(), "application/octet-stream", 7)
            )
            mock_get_service.return_value = mock_service

            # Test deeply nested path
            response = client.get("/api/v1/files/boot/linux/ubuntu/24.04/vmlinuz")
            assert response.status_code == 200
            mock_service.download_file.assert_called_with(
                "/boot/linux/ubuntu/24.04/vmlinuz"
            )
            # Filename extraction for Content-Disposition
            assert response.headers["content-disposition"] == 'inline; filename="vmlinuz"'
