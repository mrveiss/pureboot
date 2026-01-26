"""Variable resolution service for templates."""
import re
from typing import Any


KNOWN_NAMESPACES: dict[str, set[str]] = {
    "node": {
        "id",
        "mac",
        "ip",
        "hostname",
        "uuid",
        "serial",
        "vendor",
        "model",
        "architecture",
        "boot_mode",
        "state",
    },
    "group": {"id", "name", "description"},
    "workflow": {"id", "name", "description"},
    "server": {"url", "tftp_url", "http_url"},
    "template": {"id", "name", "version"},
    "execution": {"id", "step_id", "step_name"},
    "meta": set(),  # Dynamic - any key allowed
    "secret": set(),  # Dynamic - any key allowed
}


class VariableResolver:
    """Resolve template variables from structured namespaces.

    Supports variables in the format ${namespace.key} with optional defaults:
    - ${node.mac} - resolves to node's MAC address
    - ${node.ip|dhcp} - resolves to IP or "dhcp" if not set
    - ${meta.custom_key} - resolves custom metadata keys

    Namespaces:
        node: Node properties (id, mac, ip, hostname, etc.)
        group: Group properties (id, name, description)
        workflow: Workflow properties (id, name, description)
        server: Server URLs (url, tftp_url, http_url)
        template: Template properties (id, name, version)
        execution: Execution context (id, step_id, step_name)
        meta: Dynamic user-defined metadata
        secret: Dynamic secrets (any key allowed)
    """

    VARIABLE_PATTERN = re.compile(r"\$\{([a-z]+)\.([a-z_]+)(?:\|([^}]*))?\}")

    def __init__(self, context: dict[str, dict[str, Any]]):
        """Initialize with variable context.

        Args:
            context: Dictionary mapping namespaces to their variable dictionaries.
                     Example: {"node": {"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.1"}}
        """
        self.context = context

    def resolve(self, content: str) -> str:
        """Resolve all ${namespace.key} variables in content.

        Args:
            content: Template content with variable placeholders

        Returns:
            Content with variables substituted. Unknown variables without
            defaults are left as-is.
        """

        def replace(match: re.Match) -> str:
            namespace, key, default = match.groups()
            ns_context = self.context.get(namespace, {})
            value = ns_context.get(key)
            if value is None:
                return default if default is not None else match.group(0)
            return str(value)

        return self.VARIABLE_PATTERN.sub(replace, content)

    def list_variables(self, content: str) -> list[str]:
        """Extract all variable references from content.

        Args:
            content: Template content with variable placeholders

        Returns:
            List of variable references in "namespace.key" format
        """
        return [f"{m[0]}.{m[1]}" for m in self.VARIABLE_PATTERN.findall(content)]

    def validate(self, content: str) -> list[str]:
        """Validate variable references against known namespaces.

        Args:
            content: Template content with variable placeholders

        Returns:
            List of validation error messages. Empty list if all valid.
        """
        errors = []
        for namespace, key, _ in self.VARIABLE_PATTERN.findall(content):
            if namespace not in KNOWN_NAMESPACES:
                errors.append(f"Unknown namespace: {namespace}")
            elif namespace not in ("meta", "secret") and key not in KNOWN_NAMESPACES[namespace]:
                errors.append(f"Unknown variable: {namespace}.{key}")
        return errors
