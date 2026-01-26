"""Tests for variable resolver service."""
import pytest

from src.core.variable_resolver import VariableResolver, KNOWN_NAMESPACES, build_context
from src.db.models import Node, Workflow, DeviceGroup


class TestVariableResolver:
    """Test VariableResolver."""

    def test_resolve_node_variables(self):
        """resolve substitutes node namespace variables."""
        context = {
            "node": {"mac": "aa:bb:cc:dd:ee:ff", "hostname": "server-01"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve("MAC: ${node.mac}, Host: ${node.hostname}")

        assert result == "MAC: aa:bb:cc:dd:ee:ff, Host: server-01"

    def test_resolve_with_default(self):
        """resolve uses default value when variable is None."""
        context = {"node": {"ip": None}}
        resolver = VariableResolver(context)

        result = resolver.resolve("IP: ${node.ip|dhcp}")

        assert result == "IP: dhcp"

    def test_resolve_missing_keeps_placeholder(self):
        """resolve keeps placeholder for unknown variables."""
        context = {"node": {}}
        resolver = VariableResolver(context)

        result = resolver.resolve("Value: ${node.unknown}")

        assert result == "Value: ${node.unknown}"

    def test_resolve_meta_namespace(self):
        """resolve handles dynamic meta namespace."""
        context = {
            "node": {},
            "meta": {"location": "rack-5", "env": "prod"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve("Location: ${meta.location}, Env: ${meta.env}")

        assert result == "Location: rack-5, Env: prod"

    def test_resolve_server_namespace(self):
        """resolve handles server namespace variables."""
        context = {
            "server": {"url": "http://pureboot.local:8080", "tftp_url": "tftp://10.0.0.1"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve("Server: ${server.url}, TFTP: ${server.tftp_url}")

        assert result == "Server: http://pureboot.local:8080, TFTP: tftp://10.0.0.1"

    def test_resolve_multiple_namespaces(self):
        """resolve handles variables from multiple namespaces."""
        context = {
            "node": {"mac": "aa:bb:cc:dd:ee:ff"},
            "server": {"url": "http://server"},
            "workflow": {"name": "ubuntu-install"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve(
            "Node ${node.mac} running ${workflow.name} from ${server.url}"
        )

        assert result == "Node aa:bb:cc:dd:ee:ff running ubuntu-install from http://server"

    def test_resolve_empty_default(self):
        """resolve uses empty string default when specified."""
        context = {"node": {"ip": None}}
        resolver = VariableResolver(context)

        result = resolver.resolve("IP: ${node.ip|}")

        assert result == "IP: "

    def test_resolve_missing_namespace(self):
        """resolve keeps placeholder when namespace missing from context."""
        context = {}
        resolver = VariableResolver(context)

        result = resolver.resolve("MAC: ${node.mac}")

        assert result == "MAC: ${node.mac}"

    def test_resolve_integer_value(self):
        """resolve converts integer values to strings."""
        context = {"node": {"port": 8080}}
        resolver = VariableResolver(context)

        result = resolver.resolve("Port: ${node.port}")

        assert result == "Port: 8080"

    def test_list_variables(self):
        """list_variables extracts all variable references."""
        resolver = VariableResolver({})

        vars = resolver.list_variables(
            "MAC=${node.mac} IP=${node.ip|dhcp} URL=${server.url}"
        )

        assert set(vars) == {"node.mac", "node.ip", "server.url"}

    def test_list_variables_empty(self):
        """list_variables returns empty list for no variables."""
        resolver = VariableResolver({})

        vars = resolver.list_variables("No variables here")

        assert vars == []

    def test_list_variables_duplicates(self):
        """list_variables includes duplicates if present."""
        resolver = VariableResolver({})

        vars = resolver.list_variables("${node.mac} and ${node.mac}")

        assert vars == ["node.mac", "node.mac"]

    def test_validate_unknown_namespace(self):
        """validate returns errors for unknown namespaces."""
        resolver = VariableResolver({})

        errors = resolver.validate("Value: ${unknown.var}")

        assert len(errors) == 1
        assert "Unknown namespace" in errors[0]
        assert "unknown" in errors[0]

    def test_validate_unknown_variable(self):
        """validate returns errors for unknown variables in known namespaces."""
        resolver = VariableResolver({})

        errors = resolver.validate("Value: ${node.nonexistent}")

        assert len(errors) == 1
        assert "Unknown variable" in errors[0]
        assert "node.nonexistent" in errors[0]

    def test_validate_meta_allows_any_key(self):
        """validate allows any key in meta namespace."""
        resolver = VariableResolver({})

        errors = resolver.validate("${meta.custom_key} ${meta.any_value}")

        assert errors == []

    def test_validate_secret_allows_any_key(self):
        """validate allows any key in secret namespace."""
        resolver = VariableResolver({})

        errors = resolver.validate("${secret.api_key} ${secret.password}")

        assert errors == []

    def test_validate_valid_variables(self):
        """validate returns empty list for valid variables."""
        resolver = VariableResolver({})

        errors = resolver.validate(
            "${node.mac} ${node.hostname} ${server.url} ${workflow.name}"
        )

        assert errors == []

    def test_validate_multiple_errors(self):
        """validate returns all errors found."""
        resolver = VariableResolver({})

        errors = resolver.validate("${bad.ns} ${node.invalid} ${also.bad}")

        assert len(errors) == 3


class TestKnownNamespaces:
    """Test KNOWN_NAMESPACES configuration."""

    def test_node_namespace_has_expected_keys(self):
        """node namespace contains expected variable keys."""
        expected = {
            "id", "mac", "ip", "hostname", "uuid", "serial",
            "vendor", "model", "architecture", "boot_mode", "state"
        }
        assert KNOWN_NAMESPACES["node"] == expected

    def test_group_namespace_has_expected_keys(self):
        """group namespace contains expected variable keys."""
        assert KNOWN_NAMESPACES["group"] == {"id", "name", "description"}

    def test_workflow_namespace_has_expected_keys(self):
        """workflow namespace contains expected variable keys."""
        assert KNOWN_NAMESPACES["workflow"] == {"id", "name", "description"}

    def test_server_namespace_has_expected_keys(self):
        """server namespace contains expected variable keys."""
        assert KNOWN_NAMESPACES["server"] == {"url", "tftp_url", "http_url"}

    def test_template_namespace_has_expected_keys(self):
        """template namespace contains expected variable keys."""
        assert KNOWN_NAMESPACES["template"] == {"id", "name", "version"}

    def test_execution_namespace_has_expected_keys(self):
        """execution namespace contains expected variable keys."""
        assert KNOWN_NAMESPACES["execution"] == {"id", "step_id", "step_name"}

    def test_meta_namespace_is_empty_set(self):
        """meta namespace is empty set allowing any keys."""
        assert KNOWN_NAMESPACES["meta"] == set()

    def test_secret_namespace_is_empty_set(self):
        """secret namespace is empty set allowing any keys."""
        assert KNOWN_NAMESPACES["secret"] == set()

    def test_all_expected_namespaces_present(self):
        """All expected namespaces are defined."""
        expected = {"node", "group", "workflow", "server", "template", "execution", "meta", "secret"}
        assert set(KNOWN_NAMESPACES.keys()) == expected


class TestBuildContext:
    """Test context building from models."""

    def test_build_context_from_node(self, test_db):
        """build_context creates context from Node model."""
        node = Node(
            mac_address="aa:bb:cc:dd:ee:ff",
            hostname="server-01",
            ip_address="192.168.1.100",
        )
        test_db.add(node)
        test_db.flush()

        context = build_context(node=node)

        assert context["node"]["mac"] == "aa:bb:cc:dd:ee:ff"
        assert context["node"]["hostname"] == "server-01"
        assert context["node"]["ip"] == "192.168.1.100"

    def test_build_context_with_group(self, test_db):
        """build_context includes group data."""
        group = DeviceGroup(name="production", description="Production servers")
        test_db.add(group)
        test_db.flush()

        node = Node(mac_address="aa:bb:cc:dd:ee:ff", group_id=group.id)
        test_db.add(node)
        test_db.flush()
        test_db.refresh(node)

        context = build_context(node=node)

        assert context["group"]["name"] == "production"
        assert context["group"]["description"] == "Production servers"

    def test_build_context_with_workflow(self, test_db):
        """build_context includes workflow data."""
        workflow = Workflow(name="ubuntu-2404", description="Ubuntu Server", os_family="linux")
        test_db.add(workflow)
        test_db.flush()

        context = build_context(workflow=workflow)

        assert context["workflow"]["name"] == "ubuntu-2404"
        assert context["workflow"]["description"] == "Ubuntu Server"
