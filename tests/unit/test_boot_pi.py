"""Tests for Raspberry Pi boot API endpoints."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.main import app


class TestPiBootEndpoint:
    """Test GET /api/v1/boot/pi endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_boot_pi_requires_serial_parameter(self, client):
        """Serial parameter is required."""
        response = client.get("/api/v1/boot/pi")

        assert response.status_code == 422  # Validation error

    def test_boot_pi_validates_serial_format(self, client):
        """Serial number format is validated (8 hex chars)."""
        response = client.get("/api/v1/boot/pi?serial=invalid")

        assert response.status_code == 400
        assert "Invalid Pi serial number" in response.json().get("detail", "")

    def test_boot_pi_validates_serial_too_short(self, client):
        """Serial number that is too short is rejected."""
        response = client.get("/api/v1/boot/pi?serial=abc123")

        assert response.status_code == 400

    def test_boot_pi_validates_serial_too_long(self, client):
        """Serial number that is too long is rejected."""
        response = client.get("/api/v1/boot/pi?serial=abc123def456")

        assert response.status_code == 400

    def test_boot_pi_accepts_valid_serial(self, client):
        """Valid 8-character hex serial is accepted."""
        response = client.get("/api/v1/boot/pi?serial=d83add36")

        # Should return 200 with JSON response (either local_boot or registration)
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        # Without auto_register enabled or existing node, should return discovered
        # (or local_boot if auto_register disabled)

    def test_boot_pi_accepts_uppercase_serial(self, client):
        """Uppercase serial is normalized and accepted."""
        response = client.get("/api/v1/boot/pi?serial=D83ADD36")

        assert response.status_code == 200

    def test_boot_pi_accepts_optional_mac(self, client):
        """Optional MAC parameter is accepted."""
        response = client.get("/api/v1/boot/pi?serial=d83add36&mac=dc:a6:32:12:34:56")

        assert response.status_code == 200

    def test_boot_pi_validates_mac_format(self, client):
        """Invalid MAC format is rejected."""
        response = client.get("/api/v1/boot/pi?serial=d83add36&mac=invalid")

        assert response.status_code == 400

    def test_boot_pi_returns_json_response(self, client):
        """Response is JSON PiBootResponse format."""
        response = client.get("/api/v1/boot/pi?serial=d83add36")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        # PiBootResponse fields
        assert "state" in data


class TestPiRegisterEndpoint:
    """Test POST /api/v1/nodes/register-pi endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_register_pi_requires_body(self, client):
        """Request body is required."""
        response = client.post("/api/v1/nodes/register-pi")

        assert response.status_code == 422  # Validation error

    def test_register_pi_requires_serial(self, client):
        """Serial field is required."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={"mac": "dc:a6:32:12:34:56"}
        )

        assert response.status_code == 422

    def test_register_pi_requires_mac(self, client):
        """MAC field is required."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={"serial": "d83add36"}
        )

        assert response.status_code == 422

    def test_register_pi_validates_serial_format(self, client):
        """Serial format is validated."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "invalid",
                "mac": "dc:a6:32:12:34:56"
            }
        )

        assert response.status_code == 422
        # Pydantic validation error for serial

    def test_register_pi_validates_mac_format(self, client):
        """MAC format is validated."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add36",
                "mac": "invalid"
            }
        )

        assert response.status_code == 422

    def test_register_pi_validates_model(self, client):
        """Pi model is validated."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add36",
                "mac": "dc:a6:32:12:34:56",
                "model": "invalid_model"
            }
        )

        assert response.status_code == 422

    def test_register_pi_accepts_valid_request(self, client):
        """Valid registration request is accepted."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add36",
                "mac": "dc:a6:32:12:34:56",
                "model": "pi4"
            }
        )

        # Should return 200/201 with ApiResponse[NodeResponse]
        assert response.status_code in (200, 201)
        data = response.json()
        assert data.get("success") is True

    def test_register_pi_accepts_pi3_model(self, client):
        """Pi3 model is accepted."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add37",
                "mac": "dc:a6:32:12:34:57",
                "model": "pi3"
            }
        )

        assert response.status_code in (200, 201)

    def test_register_pi_accepts_pi5_model(self, client):
        """Pi5 model is accepted."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add38",
                "mac": "dc:a6:32:12:34:58",
                "model": "pi5"
            }
        )

        assert response.status_code in (200, 201)

    def test_register_pi_accepts_optional_ip(self, client):
        """Optional IP address is accepted."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add39",
                "mac": "dc:a6:32:12:34:59",
                "model": "pi4",
                "ip_address": "192.168.1.100"
            }
        )

        assert response.status_code in (200, 201)

    def test_register_pi_returns_node_response(self, client):
        """Response contains NodeResponse in data field."""
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "d83add3a",
                "mac": "dc:a6:32:12:34:5a",
                "model": "pi4"
            }
        )

        assert response.status_code in (200, 201)
        data = response.json()
        assert "data" in data
        # NodeResponse should have expected fields
        node_data = data["data"]
        assert "id" in node_data
        assert "mac_address" in node_data
        assert "serial_number" in node_data
        assert node_data["arch"] == "aarch64"
        assert node_data["boot_mode"] == "pi"


class TestPiBootEndpointStates:
    """Test GET /api/v1/boot/pi returns correct responses for different node states."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_boot_pi_unknown_node_auto_register_enabled(self, client):
        """Unknown node returns discovered state when auto_register enabled."""
        # First request should auto-register
        response = client.get("/api/v1/boot/pi?serial=e83add36")

        assert response.status_code == 200
        data = response.json()
        # Should be discovered or local_boot depending on auto_register setting
        assert data["state"] in ("discovered", "active", "installed")

    def test_boot_pi_existing_discovered_node(self, client):
        """Discovered node returns awaiting workflow message."""
        # First register the node
        client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "f83add36",
                "mac": "dc:a6:32:aa:bb:cc",
                "model": "pi4"
            }
        )

        # Then boot
        response = client.get("/api/v1/boot/pi?serial=f83add36")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "discovered"
        assert "message" in data
