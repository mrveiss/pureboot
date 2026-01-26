"""Tests for API schemas."""
import pytest
from pydantic import ValidationError

from src.api.schemas import (
    NodeCreate,
    NodeUpdate,
    StateTransition,
    TagCreate,
    DeviceGroupCreate,
    DeviceGroupUpdate,
    DeviceGroupResponse,
    NodeReport,
)


class TestNodeCreate:
    """Test NodeCreate schema."""

    def test_valid_node_create(self):
        """Create node with valid data."""
        node = NodeCreate(mac_address="00:11:22:33:44:55")
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.arch == "x86_64"
        assert node.boot_mode == "bios"

    def test_mac_address_normalized(self):
        """MAC address is normalized."""
        node = NodeCreate(mac_address="00-11-22-AA-BB-CC")
        assert node.mac_address == "00:11:22:aa:bb:cc"

    def test_invalid_mac_rejected(self):
        """Invalid MAC address rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="invalid")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_invalid_arch_rejected(self):
        """Invalid architecture rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="00:11:22:33:44:55", arch="invalid")
        assert "Invalid architecture" in str(exc_info.value)

    def test_invalid_boot_mode_rejected(self):
        """Invalid boot mode rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="00:11:22:33:44:55", boot_mode="invalid")
        assert "Invalid boot mode" in str(exc_info.value)

    def test_with_hardware_info(self):
        """Create node with hardware info."""
        node = NodeCreate(
            mac_address="00:11:22:33:44:55",
            vendor="Dell Inc.",
            model="PowerEdge R740",
            serial_number="ABC123",
        )
        assert node.vendor == "Dell Inc."
        assert node.model == "PowerEdge R740"

    def test_pi_boot_mode_accepted(self):
        """Pi boot mode is accepted."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            arch="aarch64",
            boot_mode="pi",
        )
        assert node.boot_mode == "pi"

    def test_pi_node_with_serial(self):
        """Pi node with serial number for identification."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            arch="aarch64",
            boot_mode="pi",
            serial_number="d83add36",
        )
        assert node.serial_number == "d83add36"


class TestStateTransition:
    """Test StateTransition schema."""

    def test_valid_state(self):
        """Valid state accepted."""
        transition = StateTransition(state="pending")
        assert transition.state == "pending"

    def test_invalid_state_rejected(self):
        """Invalid state rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StateTransition(state="invalid_state")
        assert "Invalid state" in str(exc_info.value)


class TestTagCreate:
    """Test TagCreate schema."""

    def test_valid_tag(self):
        """Valid tag accepted."""
        tag = TagCreate(tag="production")
        assert tag.tag == "production"

    def test_tag_normalized_lowercase(self):
        """Tag is normalized to lowercase."""
        tag = TagCreate(tag="PRODUCTION")
        assert tag.tag == "production"

    def test_tag_with_special_chars_rejected(self):
        """Tag with invalid characters rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TagCreate(tag="prod@server")
        assert "can only contain" in str(exc_info.value)

    def test_empty_tag_rejected(self):
        """Empty tag rejected."""
        with pytest.raises(ValidationError):
            TagCreate(tag="")


class TestDeviceGroupCreate:
    """Test DeviceGroupCreate schema."""

    def test_valid_group(self):
        """Valid group accepted."""
        group = DeviceGroupCreate(name="webservers")
        assert group.name == "webservers"
        assert group.auto_provision is None

    def test_empty_name_rejected(self):
        """Empty name rejected."""
        with pytest.raises(ValidationError):
            DeviceGroupCreate(name="")


class TestDeviceGroupSchemas:
    """Test DeviceGroup schema changes for hierarchy."""

    def test_create_with_parent_id(self):
        """DeviceGroupCreate accepts parent_id."""
        data = DeviceGroupCreate(name="webservers", parent_id="parent-uuid")
        assert data.parent_id == "parent-uuid"

    def test_create_auto_provision_nullable(self):
        """DeviceGroupCreate auto_provision can be None."""
        data = DeviceGroupCreate(name="webservers", auto_provision=None)
        assert data.auto_provision is None

    def test_update_with_parent_id(self):
        """DeviceGroupUpdate accepts parent_id."""
        data = DeviceGroupUpdate(parent_id="new-parent-uuid")
        assert data.parent_id == "new-parent-uuid"

    def test_response_has_hierarchy_fields(self):
        """DeviceGroupResponse includes hierarchy fields."""
        # Create mock group-like object
        class MockGroup:
            id = "uuid"
            name = "webservers"
            description = None
            parent_id = "parent-uuid"
            path = "/servers/webservers"
            depth = 1
            default_workflow_id = None
            auto_provision = None
            created_at = "2026-01-26T00:00:00"
            updated_at = "2026-01-26T00:00:00"

        resp = DeviceGroupResponse.from_group(MockGroup(), node_count=5, children_count=2)
        assert resp.parent_id == "parent-uuid"
        assert resp.path == "/servers/webservers"
        assert resp.depth == 1
        assert resp.children_count == 2
        assert resp.effective_auto_provision is False  # Default when None


class TestNodeReport:
    """Test NodeReport schema."""

    def test_valid_report(self):
        """Valid report accepted."""
        report = NodeReport(
            mac_address="00:11:22:33:44:55",
            ip_address="192.168.1.100",
            hostname="webserver-01",
        )
        assert report.mac_address == "00:11:22:33:44:55"
        assert report.ip_address == "192.168.1.100"

    def test_mac_normalized(self):
        """MAC address normalized."""
        report = NodeReport(mac_address="00-11-22-AA-BB-CC")
        assert report.mac_address == "00:11:22:aa:bb:cc"


class TestPiNodeSchemas:
    """Test Pi-specific node schema fields."""

    def test_node_create_with_pi_model(self):
        """NodeCreate accepts pi_model field."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            arch="aarch64",
            boot_mode="pi",
            serial_number="d83add36",
            pi_model="pi4",
        )
        assert node.pi_model == "pi4"

    def test_pi_model_validation(self):
        """pi_model must be valid Pi model identifier."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            pi_model="pi4",
        )
        assert node.pi_model == "pi4"

    def test_pi_model_optional(self):
        """pi_model is optional."""
        node = NodeCreate(mac_address="dc:a6:32:12:34:56")
        assert node.pi_model is None
