"""Tests for boot API endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestBootAPI:
    """Test boot endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_boot_unknown_mac_returns_local_boot(self, client):
        """Unknown MAC address returns local boot script."""
        response = client.get("/api/v1/boot?mac=00:11:22:33:44:55")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "#!ipxe" in response.text
        assert "exit" in response.text  # Local boot exits iPXE

    def test_boot_requires_mac_parameter(self, client):
        """MAC parameter is required."""
        response = client.get("/api/v1/boot")

        assert response.status_code == 422  # Validation error

    def test_boot_validates_mac_format(self, client):
        """MAC address format is validated."""
        response = client.get("/api/v1/boot?mac=invalid")

        assert response.status_code == 400

    def test_boot_accepts_hyphenated_mac(self, client):
        """Accept hyphenated MAC format (from iPXE)."""
        response = client.get("/api/v1/boot?mac=00-11-22-33-44-55")

        assert response.status_code == 200
        assert "#!ipxe" in response.text
