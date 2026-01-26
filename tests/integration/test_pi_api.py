"""Integration tests for Raspberry Pi boot API endpoints.

Tests the Pi-specific API endpoints end-to-end with the database:
- GET /api/v1/boot/pi - Get boot instructions for a Pi by serial
- POST /api/v1/nodes/register-pi - Register or update a Pi node
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import Node


@pytest.fixture
def pi_node(test_db: Session) -> Node:
    """Create a test Pi node in discovered state.

    Creates a Raspberry Pi 4 node with typical Pi MAC address
    and serial number format.

    Args:
        test_db: Test database session from conftest.

    Returns:
        Node instance representing a discovered Pi.
    """
    node = Node(
        mac_address="dc:a6:32:12:34:56",
        serial_number="d83add36",
        arch="aarch64",
        boot_mode="pi",
        pi_model="pi4",
        state="discovered",
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    return node


@pytest.fixture
def pi_node_pending(test_db: Session) -> Node:
    """Create a test Pi node in pending state.

    Args:
        test_db: Test database session from conftest.

    Returns:
        Node instance in pending state without workflow.
    """
    node = Node(
        mac_address="dc:a6:32:aa:bb:cc",
        serial_number="abcd1234",
        arch="aarch64",
        boot_mode="pi",
        pi_model="pi4",
        state="pending",
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    return node


@pytest.fixture
def pi_node_active(test_db: Session) -> Node:
    """Create a test Pi node in active state.

    Args:
        test_db: Test database session from conftest.

    Returns:
        Node instance in active state.
    """
    node = Node(
        mac_address="dc:a6:32:11:22:33",
        serial_number="1234abcd",
        arch="aarch64",
        boot_mode="pi",
        pi_model="pi4",
        state="active",
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    return node


class TestGetBootPi:
    """Tests for GET /api/v1/boot/pi endpoint."""

    def test_get_boot_pi_unknown_serial(self, client: TestClient):
        """GET /boot/pi with unknown serial returns discovered state.

        When a Pi boots with a serial number not in the database,
        it should be auto-registered and return discovered state.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": "00000001"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "discovered"
        assert "registered" in data["message"].lower() or "awaiting" in data["message"].lower()

    def test_get_boot_pi_existing_node_discovered(
        self, client: TestClient, pi_node: Node
    ):
        """GET /boot/pi with existing discovered node returns correct state.

        When a known Pi in discovered state boots, it should receive
        instructions to await workflow assignment.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": pi_node.serial_number},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "discovered"
        assert "workflow" in data["message"].lower()

    def test_get_boot_pi_existing_node_pending_no_workflow(
        self, client: TestClient, pi_node_pending: Node
    ):
        """GET /boot/pi with pending node without workflow returns local_boot.

        A pending node with no workflow assigned should boot locally.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": pi_node_pending.serial_number},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "pending"
        assert data["action"] == "local_boot"

    def test_get_boot_pi_existing_node_active(
        self, client: TestClient, pi_node_active: Node
    ):
        """GET /boot/pi with active node returns local_boot.

        Active nodes should always boot from local storage.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": pi_node_active.serial_number},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "active"
        assert data["action"] == "local_boot"

    def test_get_boot_pi_invalid_serial_too_short(self, client: TestClient):
        """GET /boot/pi rejects serial that is too short (400).

        Serial numbers must be exactly 8 hexadecimal characters.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": "abc123"},  # Only 6 chars
        )
        assert response.status_code == 422  # Validation error

    def test_get_boot_pi_invalid_serial_too_long(self, client: TestClient):
        """GET /boot/pi rejects serial that is too long (400).

        Serial numbers must be exactly 8 hexadecimal characters.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": "0123456789"},  # 10 chars
        )
        assert response.status_code == 422  # Validation error

    def test_get_boot_pi_invalid_serial_non_hex(self, client: TestClient):
        """GET /boot/pi rejects non-hexadecimal serial (400).

        Serial numbers must contain only hexadecimal characters.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": "ghijklmn"},  # Non-hex chars
        )
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_get_boot_pi_with_mac_address(self, client: TestClient):
        """GET /boot/pi with MAC address parameter registers node with MAC.

        When MAC is provided, it should be stored with the node.
        """
        response = client.get(
            "/api/v1/boot/pi",
            params={
                "serial": "fedcba98",
                "mac": "dc:a6:32:fe:dc:ba",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "discovered"

    def test_get_boot_pi_serial_case_insensitive(self, client: TestClient, pi_node: Node):
        """GET /boot/pi handles serial number case insensitively.

        Serial numbers should be normalized to lowercase.
        """
        # Test with uppercase
        response = client.get(
            "/api/v1/boot/pi",
            params={"serial": pi_node.serial_number.upper()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "discovered"


class TestRegisterPi:
    """Tests for POST /api/v1/nodes/register-pi endpoint."""

    def test_register_pi_new_node(self, client: TestClient):
        """POST /nodes/register-pi creates new node.

        Registering a new Pi serial should create a node entry
        with all provided attributes.
        """
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "11223344",
                "mac": "dc:a6:32:11:22:33",
                "model": "pi4",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["serial_number"] == "11223344"
        assert data["data"]["mac_address"] == "dc:a6:32:11:22:33"
        assert data["data"]["pi_model"] == "pi4"
        assert data["data"]["arch"] == "aarch64"
        assert data["data"]["boot_mode"] == "pi"
        assert data["data"]["state"] == "discovered"
        assert "registered" in data["message"].lower()

    def test_register_pi_update_existing(self, client: TestClient, pi_node: Node):
        """POST /nodes/register-pi updates existing node.

        Re-registering a known serial should update the node's
        information rather than creating a duplicate.
        """
        # Change model from pi4 to pi5
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": pi_node.serial_number,
                "mac": "dc:a6:32:99:88:77",  # Different MAC
                "model": "pi5",  # Different model
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == pi_node.id
        assert data["data"]["pi_model"] == "pi5"
        assert data["data"]["mac_address"] == "dc:a6:32:99:88:77"
        assert "updated" in data["message"].lower()

    def test_register_pi_invalid_model(self, client: TestClient):
        """POST /nodes/register-pi rejects invalid model (422).

        Only valid Pi models (pi3, pi4, pi5) should be accepted.
        """
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "55667788",
                "mac": "dc:a6:32:55:66:77",
                "model": "pi2",  # Invalid model
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        # Check that validation error mentions invalid model
        assert any("model" in str(err).lower() for err in detail)

    def test_register_pi_invalid_serial(self, client: TestClient):
        """POST /nodes/register-pi rejects invalid serial (422).

        Serial must be exactly 8 hex characters.
        """
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "invalid!",  # Invalid characters
                "mac": "dc:a6:32:55:66:77",
                "model": "pi4",
            },
        )
        assert response.status_code == 422

    def test_register_pi_invalid_mac(self, client: TestClient):
        """POST /nodes/register-pi rejects invalid MAC (422).

        MAC address must be in valid format.
        """
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "aabbccdd",
                "mac": "not-a-mac",  # Invalid MAC
                "model": "pi4",
            },
        )
        assert response.status_code == 422

    def test_register_pi_with_ip_address(self, client: TestClient):
        """POST /nodes/register-pi stores provided IP address.

        When IP address is provided, it should be stored with the node.
        """
        response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "99aabbcc",
                "mac": "dc:a6:32:99:aa:bb",
                "model": "pi4",
                "ip_address": "192.168.1.100",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["ip_address"] == "192.168.1.100"

    def test_register_pi_all_models(self, client: TestClient):
        """POST /nodes/register-pi accepts all valid Pi models.

        Test that pi3, pi4, and pi5 are all accepted.
        """
        valid_models = [
            ("aabbcc01", "dc:a6:32:aa:bb:01", "pi3"),
            ("aabbcc02", "dc:a6:32:aa:bb:02", "pi4"),
            ("aabbcc03", "dc:a6:32:aa:bb:03", "pi5"),
        ]
        for serial, mac, model in valid_models:
            response = client.post(
                "/api/v1/nodes/register-pi",
                json={
                    "serial": serial,
                    "mac": mac,
                    "model": model,
                },
            )
            assert response.status_code == 200, f"Failed for model {model}"
            assert response.json()["data"]["pi_model"] == model


class TestGetNodeBySerial:
    """Tests for retrieving Pi nodes by ID and verifying pi_model field."""

    def test_get_node_by_id_returns_pi_model(
        self, client: TestClient, pi_node: Node
    ):
        """GET /nodes/{id} returns pi_model field for Pi nodes.

        When retrieving a Pi node by ID, the response should
        include the pi_model field.
        """
        response = client.get(f"/api/v1/nodes/{pi_node.id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["pi_model"] == "pi4"
        assert data["arch"] == "aarch64"
        assert data["boot_mode"] == "pi"
        assert data["serial_number"] == "d83add36"

    def test_get_node_shows_pi_specific_fields(self, client: TestClient):
        """GET /nodes/{id} shows all Pi-specific fields after registration.

        Register a Pi and then retrieve it to verify all fields are present.
        """
        # Register a new Pi
        register_response = client.post(
            "/api/v1/nodes/register-pi",
            json={
                "serial": "deadbeef",
                "mac": "dc:a6:32:de:ad:be",
                "model": "pi5",
                "ip_address": "10.0.0.50",
            },
        )
        assert register_response.status_code == 200
        node_id = register_response.json()["data"]["id"]

        # Retrieve the node
        response = client.get(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        data = response.json()["data"]

        # Verify all Pi-specific fields
        assert data["serial_number"] == "deadbeef"
        assert data["mac_address"] == "dc:a6:32:de:ad:be"
        assert data["pi_model"] == "pi5"
        assert data["arch"] == "aarch64"
        assert data["boot_mode"] == "pi"
        assert data["ip_address"] == "10.0.0.50"

    def test_list_nodes_includes_pi_nodes(self, client: TestClient, pi_node: Node):
        """GET /nodes lists Pi nodes with pi_model field.

        When listing nodes, Pi nodes should include the pi_model field.
        """
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

        # Find our Pi node in the list
        pi_nodes = [n for n in data["data"] if n["id"] == pi_node.id]
        assert len(pi_nodes) == 1
        assert pi_nodes[0]["pi_model"] == "pi4"


class TestPiNodeLifecycle:
    """Integration tests for Pi node lifecycle operations."""

    def test_pi_node_state_transition(self, client: TestClient, pi_node: Node):
        """Pi node can transition through states like any other node.

        Verify that state machine works correctly for Pi nodes.
        """
        # Transition discovered -> pending
        response = client.patch(
            f"/api/v1/nodes/{pi_node.id}/state",
            json={"state": "pending"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "pending"

        # Transition pending -> installing
        response = client.patch(
            f"/api/v1/nodes/{pi_node.id}/state",
            json={"state": "installing"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "installing"

    def test_pi_node_can_be_updated(self, client: TestClient, pi_node: Node):
        """Pi node metadata can be updated via PATCH.

        The pi_model field should be updatable.
        """
        response = client.patch(
            f"/api/v1/nodes/{pi_node.id}",
            json={"pi_model": "pi5", "hostname": "pi-server-01"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["pi_model"] == "pi5"
        assert data["hostname"] == "pi-server-01"

    def test_pi_node_can_be_tagged(self, client: TestClient, pi_node: Node):
        """Pi node can have tags added."""
        response = client.post(
            f"/api/v1/nodes/{pi_node.id}/tags",
            json={"tag": "raspberry-pi"},
        )
        assert response.status_code == 200
        assert "raspberry-pi" in response.json()["data"]["tags"]

    def test_pi_node_can_be_retired(self, client: TestClient, pi_node: Node):
        """Pi node can be retired via DELETE."""
        response = client.delete(f"/api/v1/nodes/{pi_node.id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "retired"
