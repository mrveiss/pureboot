"""Integration tests for full application."""
import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestApplicationIntegration:
    """Test full application integration."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_health_check(self, client):
        """Health endpoint works."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_boot_endpoint_available(self, client):
        """Boot endpoint is available."""
        response = client.get("/api/v1/boot?mac=00:11:22:33:44:55")
        assert response.status_code == 200
        assert "#!ipxe" in response.text

    def test_ipxe_script_endpoint(self, client):
        """iPXE boot script endpoint works."""
        response = client.get("/api/v1/ipxe/boot.ipxe?server=192.168.1.10:8080")
        assert response.status_code == 200
        assert "#!ipxe" in response.text
        assert "192.168.1.10" in response.text

    def test_openapi_docs_available(self, client):
        """OpenAPI docs are generated."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "PureBoot" in response.json()["info"]["title"]
