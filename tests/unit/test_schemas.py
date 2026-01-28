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
    SiteCreate,
    SiteUpdate,
    SiteResponse,
    SiteHealthResponse,
    SiteSyncRequest,
    SiteSyncResponse,
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


class TestSiteCreate:
    """Test SiteCreate schema."""

    def test_valid_site_create(self):
        """Create site with valid data."""
        from src.api.schemas import SiteCreate

        site = SiteCreate(name="datacenter-west")
        assert site.name == "datacenter-west"
        assert site.autonomy_level == "readonly"
        assert site.conflict_resolution == "central_wins"
        assert site.cache_policy == "minimal"
        assert site.discovery_method == "dhcp"
        assert site.migration_policy == "manual"
        assert site.cache_retention_days == 30

    def test_site_create_with_all_fields(self):
        """Create site with all fields specified."""
        from src.api.schemas import SiteCreate

        site = SiteCreate(
            name="branch-office-nyc",
            description="New York branch office",
            parent_id="parent-site-uuid",
            agent_url="https://site-agent.local:8443",
            autonomy_level="full",
            conflict_resolution="last_write",
            cache_policy="mirror",
            cache_max_size_gb=100,
            cache_retention_days=60,
            discovery_method="dns",
            migration_policy="bidirectional",
        )
        assert site.name == "branch-office-nyc"
        assert site.autonomy_level == "full"
        assert site.cache_max_size_gb == 100

    def test_invalid_autonomy_level_rejected(self):
        """Invalid autonomy level rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError) as exc_info:
            SiteCreate(name="test-site", autonomy_level="invalid")
        assert "Invalid autonomy_level" in str(exc_info.value)

    def test_invalid_conflict_resolution_rejected(self):
        """Invalid conflict resolution rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError) as exc_info:
            SiteCreate(name="test-site", conflict_resolution="invalid")
        assert "Invalid conflict_resolution" in str(exc_info.value)

    def test_invalid_cache_policy_rejected(self):
        """Invalid cache policy rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError) as exc_info:
            SiteCreate(name="test-site", cache_policy="invalid")
        assert "Invalid cache_policy" in str(exc_info.value)

    def test_invalid_discovery_method_rejected(self):
        """Invalid discovery method rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError) as exc_info:
            SiteCreate(name="test-site", discovery_method="invalid")
        assert "Invalid discovery_method" in str(exc_info.value)

    def test_invalid_migration_policy_rejected(self):
        """Invalid migration policy rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError) as exc_info:
            SiteCreate(name="test-site", migration_policy="invalid")
        assert "Invalid migration_policy" in str(exc_info.value)

    def test_empty_name_rejected(self):
        """Empty name rejected."""
        from src.api.schemas import SiteCreate

        with pytest.raises(ValidationError):
            SiteCreate(name="")

    def test_all_autonomy_levels_valid(self):
        """All valid autonomy levels accepted."""
        from src.api.schemas import SiteCreate

        for level in ["readonly", "limited", "full"]:
            site = SiteCreate(name="test-site", autonomy_level=level)
            assert site.autonomy_level == level

    def test_all_conflict_resolutions_valid(self):
        """All valid conflict resolutions accepted."""
        from src.api.schemas import SiteCreate

        for resolution in ["central_wins", "last_write", "site_wins", "manual"]:
            site = SiteCreate(name="test-site", conflict_resolution=resolution)
            assert site.conflict_resolution == resolution

    def test_all_cache_policies_valid(self):
        """All valid cache policies accepted."""
        from src.api.schemas import SiteCreate

        for policy in ["minimal", "assigned", "mirror", "pattern"]:
            site = SiteCreate(name="test-site", cache_policy=policy)
            assert site.cache_policy == policy

    def test_all_discovery_methods_valid(self):
        """All valid discovery methods accepted."""
        from src.api.schemas import SiteCreate

        for method in ["dhcp", "dns", "anycast", "fallback"]:
            site = SiteCreate(name="test-site", discovery_method=method)
            assert site.discovery_method == method

    def test_all_migration_policies_valid(self):
        """All valid migration policies accepted."""
        from src.api.schemas import SiteCreate

        for policy in ["manual", "auto_accept", "auto_release", "bidirectional"]:
            site = SiteCreate(name="test-site", migration_policy=policy)
            assert site.migration_policy == policy


class TestSiteUpdate:
    """Test SiteUpdate schema."""

    def test_all_fields_optional(self):
        """All fields are optional for update."""
        from src.api.schemas import SiteUpdate

        update = SiteUpdate()
        assert update.name is None
        assert update.autonomy_level is None

    def test_partial_update(self):
        """Can update just some fields."""
        from src.api.schemas import SiteUpdate

        update = SiteUpdate(autonomy_level="full", cache_max_size_gb=200)
        assert update.autonomy_level == "full"
        assert update.cache_max_size_gb == 200
        assert update.name is None

    def test_invalid_autonomy_level_rejected(self):
        """Invalid autonomy level rejected in update."""
        from src.api.schemas import SiteUpdate

        with pytest.raises(ValidationError) as exc_info:
            SiteUpdate(autonomy_level="invalid")
        assert "Invalid autonomy_level" in str(exc_info.value)

    def test_invalid_conflict_resolution_rejected(self):
        """Invalid conflict resolution rejected in update."""
        from src.api.schemas import SiteUpdate

        with pytest.raises(ValidationError) as exc_info:
            SiteUpdate(conflict_resolution="invalid")
        assert "Invalid conflict_resolution" in str(exc_info.value)

    def test_none_values_allowed(self):
        """None values are allowed (they mean 'no change')."""
        from src.api.schemas import SiteUpdate

        update = SiteUpdate(autonomy_level=None, cache_policy=None)
        assert update.autonomy_level is None
        assert update.cache_policy is None


class TestSiteResponse:
    """Test SiteResponse schema."""

    def test_site_response_includes_site_fields(self):
        """SiteResponse includes site-specific fields."""
        from datetime import datetime
        from src.api.schemas import SiteResponse

        class MockSite:
            id = "site-uuid"
            name = "datacenter-west"
            description = "Western datacenter"
            parent_id = None
            path = "/datacenter-west"
            depth = 0
            default_workflow_id = None
            auto_provision = None
            created_at = datetime(2026, 1, 26)
            updated_at = datetime(2026, 1, 26)
            # Site-specific fields
            is_site = True
            agent_url = "https://site-agent.local:8443"
            agent_status = "online"
            agent_last_seen = datetime(2026, 1, 26, 12, 0, 0)
            autonomy_level = "limited"
            conflict_resolution = "central_wins"
            cache_policy = "assigned"
            cache_patterns_json = None
            cache_max_size_gb = 100
            cache_retention_days = 30
            discovery_method = "dhcp"
            discovery_config_json = None
            migration_policy = "manual"

        resp = SiteResponse.from_site(MockSite(), node_count=10, children_count=2)

        assert resp.id == "site-uuid"
        assert resp.name == "datacenter-west"
        assert resp.is_site is True
        assert resp.agent_url == "https://site-agent.local:8443"
        assert resp.agent_status == "online"
        assert resp.autonomy_level == "limited"
        assert resp.cache_policy == "assigned"
        assert resp.cache_max_size_gb == 100
        assert resp.node_count == 10
        assert resp.children_count == 2

    def test_site_response_inherits_from_device_group_response(self):
        """SiteResponse inherits DeviceGroupResponse fields."""
        from src.api.schemas import SiteResponse, DeviceGroupResponse

        assert issubclass(SiteResponse, DeviceGroupResponse)

    def test_site_response_with_null_agent_status(self):
        """SiteResponse handles null agent status (site not yet connected)."""
        from datetime import datetime
        from src.api.schemas import SiteResponse

        class MockSite:
            id = "site-uuid"
            name = "new-site"
            description = None
            parent_id = None
            path = "/new-site"
            depth = 0
            default_workflow_id = None
            auto_provision = None
            created_at = datetime(2026, 1, 26)
            updated_at = datetime(2026, 1, 26)
            is_site = True
            agent_url = None
            agent_status = None
            agent_last_seen = None
            autonomy_level = "readonly"
            conflict_resolution = "central_wins"
            cache_policy = "minimal"
            cache_patterns_json = None
            cache_max_size_gb = None
            cache_retention_days = 30
            discovery_method = "dhcp"
            discovery_config_json = None
            migration_policy = "manual"

        resp = SiteResponse.from_site(MockSite())

        assert resp.agent_url is None
        assert resp.agent_status is None
        assert resp.agent_last_seen is None


class TestSiteHealthResponse:
    """Test SiteHealthResponse schema."""

    def test_site_health_response(self):
        """SiteHealthResponse accepts all fields."""
        from datetime import datetime
        from src.api.schemas import SiteHealthResponse

        health = SiteHealthResponse(
            site_id="site-uuid",
            agent_status="online",
            agent_last_seen=datetime(2026, 1, 26, 12, 0, 0),
            pending_sync_items=5,
            conflicts_pending=2,
            nodes_count=10,
            cache_used_gb=45.5,
            cache_max_gb=100,
        )
        assert health.site_id == "site-uuid"
        assert health.agent_status == "online"
        assert health.pending_sync_items == 5
        assert health.conflicts_pending == 2

    def test_site_health_response_defaults(self):
        """SiteHealthResponse has sensible defaults."""
        from src.api.schemas import SiteHealthResponse

        health = SiteHealthResponse(site_id="site-uuid", agent_status=None)
        assert health.pending_sync_items == 0
        assert health.conflicts_pending == 0
        assert health.nodes_count == 0
        assert health.cache_used_gb is None


class TestSiteSyncSchemas:
    """Test site sync request/response schemas."""

    def test_site_sync_request_defaults(self):
        """SiteSyncRequest has sensible defaults."""
        from src.api.schemas import SiteSyncRequest

        req = SiteSyncRequest()
        assert req.full_sync is False
        assert req.entity_types is None

    def test_site_sync_request_with_options(self):
        """SiteSyncRequest accepts sync options."""
        from src.api.schemas import SiteSyncRequest

        req = SiteSyncRequest(full_sync=True, entity_types=["node", "workflow"])
        assert req.full_sync is True
        assert req.entity_types == ["node", "workflow"]

    def test_site_sync_response(self):
        """SiteSyncResponse contains sync job info."""
        from src.api.schemas import SiteSyncResponse

        resp = SiteSyncResponse(
            sync_id="sync-uuid",
            status="queued",
            message="Sync queued successfully",
        )
        assert resp.sync_id == "sync-uuid"
        assert resp.status == "queued"
