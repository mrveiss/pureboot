"""Tests for database models."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.models import Base, Node, DeviceGroup, NodeTag, Template, TemplateVersion, Workflow


@pytest.fixture
def engine():
    """Create in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create database session."""
    with Session(engine) as session:
        yield session


class TestNodeModel:
    """Test Node model."""

    def test_create_node_with_defaults(self, session):
        """Create node with default values."""
        node = Node(mac_address="00:11:22:33:44:55")
        session.add(node)
        session.commit()

        assert node.id is not None
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.state == "discovered"
        assert node.arch == "x86_64"
        assert node.boot_mode == "bios"

    def test_create_node_with_hardware_info(self, session):
        """Create node with hardware identification."""
        node = Node(
            mac_address="00:11:22:33:44:55",
            vendor="Dell Inc.",
            model="PowerEdge R740",
            serial_number="ABC123",
            system_uuid="550e8400-e29b-41d4-a716-446655440000",
        )
        session.add(node)
        session.commit()

        assert node.vendor == "Dell Inc."
        assert node.model == "PowerEdge R740"
        assert node.serial_number == "ABC123"

    def test_mac_address_unique(self, session):
        """MAC address must be unique."""
        node1 = Node(mac_address="00:11:22:33:44:55")
        node2 = Node(mac_address="00:11:22:33:44:55")
        session.add(node1)
        session.commit()

        session.add(node2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_create_pi_node(self, session):
        """Create Raspberry Pi node with pi_model field."""
        node = Node(
            mac_address="dc:a6:32:12:34:56",
            arch="aarch64",
            boot_mode="pi",
            serial_number="d83add36",
            pi_model="pi4",
        )
        session.add(node)
        session.commit()

        assert node.arch == "aarch64"
        assert node.boot_mode == "pi"
        assert node.pi_model == "pi4"
        assert node.serial_number == "d83add36"

    def test_pi_model_optional(self, session):
        """pi_model field is optional (nullable)."""
        node = Node(mac_address="00:11:22:33:44:55")
        session.add(node)
        session.commit()

        assert node.pi_model is None


class TestDeviceGroupModel:
    """Test DeviceGroup model."""

    def test_create_group(self, session):
        """Create device group."""
        group = DeviceGroup(name="webservers", description="Web server nodes")
        session.add(group)
        session.commit()

        assert group.id is not None
        assert group.name == "webservers"
        assert group.auto_provision is None  # Default is None for inheritance

    def test_group_name_unique(self, session):
        """Group name must be unique."""
        group1 = DeviceGroup(name="webservers")
        group2 = DeviceGroup(name="webservers")
        session.add(group1)
        session.commit()

        session.add(group2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_node_group_relationship(self, session):
        """Node can belong to a group."""
        group = DeviceGroup(name="webservers")
        node = Node(mac_address="00:11:22:33:44:55", group=group)
        session.add(node)
        session.commit()

        assert node.group_id == group.id
        assert node in group.nodes


class TestNodeTagModel:
    """Test NodeTag model."""

    def test_add_tag_to_node(self, session):
        """Add tag to node."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag = NodeTag(node=node, tag="production")
        session.add(tag)
        session.commit()

        assert tag.id is not None
        assert tag.tag == "production"
        assert tag in node.tags

    def test_node_can_have_multiple_tags(self, session):
        """Node can have multiple tags."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag1 = NodeTag(node=node, tag="production")
        tag2 = NodeTag(node=node, tag="webserver")
        session.add_all([tag1, tag2])
        session.commit()

        assert len(node.tags) == 2

    def test_same_tag_same_node_not_allowed(self, session):
        """Same tag on same node not allowed."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag1 = NodeTag(node=node, tag="production")
        tag2 = NodeTag(node=node, tag="production")
        session.add_all([tag1, tag2])

        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_tags_deleted_with_node(self, session):
        """Tags are deleted when node is deleted."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag = NodeTag(node=node, tag="production")
        session.add(tag)
        session.commit()

        tag_id = tag.id
        session.delete(node)
        session.commit()

        assert session.get(NodeTag, tag_id) is None


class TestDeviceGroupHierarchy:
    """Test DeviceGroup hierarchy features."""

    def test_group_with_parent(self, session):
        """Group can have a parent."""
        parent = DeviceGroup(name="servers")
        session.add(parent)
        session.flush()

        child = DeviceGroup(name="webservers", parent_id=parent.id)
        session.add(child)
        session.commit()

        assert child.parent_id == parent.id
        assert child.parent.name == "servers"
        assert child in parent.children

    def test_group_path_and_depth(self, session):
        """Group has path and depth fields."""
        group = DeviceGroup(name="servers", path="/servers", depth=0)
        session.add(group)
        session.commit()

        assert group.path == "/servers"
        assert group.depth == 0

    def test_auto_provision_nullable(self, session):
        """auto_provision can be None for inheritance."""
        group = DeviceGroup(name="servers", auto_provision=None)
        session.add(group)
        session.commit()

        assert group.auto_provision is None


class TestTemplateVersion:
    """Test TemplateVersion model."""

    def test_template_version_creation(self, session):
        """TemplateVersion can be created with required fields."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id,
            major=1,
            minor=0,
            content="# kickstart content",
            content_hash="abc123",
        )
        session.add(version)
        session.flush()

        assert version.id is not None
        assert version.major == 1
        assert version.minor == 0
        assert version.version_string == "v1.0"

    def test_template_version_unique_constraint(self, session):
        """TemplateVersion enforces unique major.minor per template."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1", content_hash="hash1"
        )
        session.add(v1)
        session.flush()

        v1_dup = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1 dup", content_hash="hash2"
        )
        session.add(v1_dup)

        with pytest.raises(Exception):  # IntegrityError
            session.flush()

    def test_template_version_relationship(self, session):
        """Template has versions relationship."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1.0 content", content_hash="hash1"
        )
        v2 = TemplateVersion(
            template_id=template.id, major=1, minor=1,
            content="v1.1 content", content_hash="hash2"
        )
        session.add_all([v1, v2])
        session.flush()

        assert len(template.versions) == 2
        assert v1 in template.versions
        assert v2 in template.versions

    def test_template_version_cascade_delete(self, session):
        """Versions are deleted when template is deleted."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="content", content_hash="hash"
        )
        session.add(version)
        session.flush()

        version_id = version.id
        session.delete(template)
        session.flush()

        assert session.get(TemplateVersion, version_id) is None

    def test_template_version_optional_fields(self, session):
        """TemplateVersion optional fields work correctly."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id,
            major=1,
            minor=0,
            content="# kickstart content",
            content_hash="abc123def456",
            size_bytes=1024,
            commit_message="Initial version",
            file_path="/templates/kickstart/test.ks",
        )
        session.add(version)
        session.flush()

        assert version.size_bytes == 1024
        assert version.commit_message == "Initial version"
        assert version.file_path == "/templates/kickstart/test.ks"

    def test_template_current_version_id(self, session):
        """Template can track current version."""
        template = Template(name="test-template", type="kickstart")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="content", content_hash="hash"
        )
        session.add(version)
        session.flush()

        template.current_version_id = version.id
        session.flush()

        assert template.current_version_id == version.id


class TestWorkflow:
    """Test Workflow model."""

    def test_workflow_creation(self, session):
        """Workflow can be created with required fields."""
        workflow = Workflow(
            name="ubuntu-2404",
            description="Ubuntu 24.04 Server",
            os_family="linux",
        )
        session.add(workflow)
        session.flush()

        assert workflow.id is not None
        assert workflow.name == "ubuntu-2404"
        assert workflow.os_family == "linux"
        assert workflow.architecture == "x86_64"
        assert workflow.boot_mode == "bios"
        assert workflow.is_active is True

    def test_workflow_unique_name(self, session):
        """Workflow name must be unique."""
        w1 = Workflow(name="ubuntu", os_family="linux")
        session.add(w1)
        session.flush()

        w2 = Workflow(name="ubuntu", os_family="linux")
        session.add(w2)

        with pytest.raises(Exception):
            session.flush()

    def test_workflow_default_description(self, session):
        """Workflow description defaults to empty string."""
        workflow = Workflow(name="rhel-9", os_family="linux")
        session.add(workflow)
        session.flush()

        assert workflow.description == ""

    def test_workflow_custom_architecture_and_boot_mode(self, session):
        """Workflow can have custom architecture and boot_mode."""
        workflow = Workflow(
            name="ubuntu-arm",
            os_family="linux",
            architecture="aarch64",
            boot_mode="uefi",
        )
        session.add(workflow)
        session.flush()

        assert workflow.architecture == "aarch64"
        assert workflow.boot_mode == "uefi"

    def test_workflow_is_active_flag(self, session):
        """Workflow is_active can be set to False for soft delete."""
        workflow = Workflow(name="deprecated", os_family="windows", is_active=False)
        session.add(workflow)
        session.flush()

        assert workflow.is_active is False
