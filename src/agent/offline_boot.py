"""Offline boot script generator for site agent.

Generates boot scripts when operating offline, using cached node state
and content to provide continuity when central controller is unreachable.
"""
import logging
from datetime import datetime, timezone
from typing import Literal

from src.agent.cache.state_cache import NodeStateCache, CachedNode
from src.agent.cache.content_cache import ContentCache

logger = logging.getLogger(__name__)


class OfflineBootGenerator:
    """Generates boot scripts when operating offline."""

    def __init__(
        self,
        state_cache: NodeStateCache,
        content_cache: ContentCache,
        site_id: str,
        default_action: Literal["local", "discovery", "last_known"] = "local",
        offline_since: datetime | None = None,
    ):
        """Initialize offline boot generator.

        Args:
            state_cache: Node state cache instance
            content_cache: Content cache instance
            site_id: This agent's site ID
            default_action: Default action for unknown nodes:
                - local: Boot from local disk
                - discovery: Run discovery script
                - last_known: Use last known state if available
            offline_since: When agent went offline (for display)
        """
        self.state_cache = state_cache
        self.content_cache = content_cache
        self.site_id = site_id
        self.default_action = default_action
        self.offline_since = offline_since

    def set_offline_since(self, offline_since: datetime | None):
        """Update the offline timestamp."""
        self.offline_since = offline_since

    async def generate_script(
        self,
        mac: str,
        hardware_info: dict | None = None,
    ) -> str:
        """Generate boot script from cached state.

        Args:
            mac: MAC address of the booting node
            hardware_info: Optional hardware information

        Returns:
            iPXE boot script
        """
        # Normalize MAC address
        mac = mac.lower().replace("-", ":")

        # Check if we have cached state for this node
        cached_node = await self.state_cache.get_node(mac)

        if cached_node:
            # We have cached state - use it
            logger.info(f"Generating offline boot script for {mac} from cached state")
            return await self._generate_cached_script(cached_node)
        else:
            # Unknown node in offline mode
            logger.info(f"Generating offline boot script for unknown node {mac}")
            return await self._generate_unknown_script(mac, hardware_info)

    async def _generate_cached_script(self, node: CachedNode) -> str:
        """Generate script based on cached node state.

        Args:
            node: Cached node information

        Returns:
            iPXE boot script
        """
        state = node.state
        mac = node.mac_address
        cached_at = node.cached_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        offline_info = self._get_offline_info()

        # Map state to boot action
        if state in ("discovered", "pending"):
            # Node awaiting provisioning - boot local
            return self._script_header(mac) + f"""
# Cached State: {state}
# Cached At: {cached_at}
{offline_info}

echo   Node is in '{state}' state.
echo   Cannot provision while offline.
echo   Booting from local disk...
echo

sleep 5
sanboot --drive 0x80 || exit
"""

        elif state == "installing":
            # Node was installing - dangerous to continue
            return self._script_header(mac) + f"""
# Cached State: {state}
# Cached At: {cached_at}
{offline_info}

echo   *** WARNING ***
echo   Node was in '{state}' state when offline began.
echo   Cannot continue installation without central.
echo   Booting from local disk (installation may be incomplete).
echo

sleep 10
sanboot --drive 0x80 || exit
"""

        elif state in ("installed", "active"):
            # Node should boot normally
            return self._script_header(mac) + f"""
# Cached State: {state}
# Cached At: {cached_at}
{offline_info}

echo   Node is in '{state}' state.
echo   Booting from local disk...
echo

sleep 3
sanboot --drive 0x80 || exit
"""

        elif state == "reprovision":
            # Node marked for reprovision - can't do it offline
            return self._script_header(mac) + f"""
# Cached State: {state}
# Cached At: {cached_at}
{offline_info}

echo   Node is marked for reprovisioning.
echo   Cannot reprovision while offline.
echo   Booting from local disk...
echo

sleep 5
sanboot --drive 0x80 || exit
"""

        elif state == "retired":
            # Retired node
            return self._script_header(mac) + f"""
# Cached State: {state}
# Cached At: {cached_at}
{offline_info}

echo   Node is retired.
echo   No boot action configured.
echo

sleep 3
exit
"""

        else:
            # Unknown state - boot local
            return self._script_header(mac) + f"""
# Cached State: {state} (unknown)
# Cached At: {cached_at}
{offline_info}

echo   Unknown node state: {state}
echo   Booting from local disk...
echo

sleep 3
sanboot --drive 0x80 || exit
"""

    async def _generate_unknown_script(
        self,
        mac: str,
        hardware_info: dict | None = None,
    ) -> str:
        """Generate script for unknown node in offline mode.

        Args:
            mac: MAC address
            hardware_info: Optional hardware information

        Returns:
            iPXE boot script based on default_action
        """
        offline_info = self._get_offline_info()

        if self.default_action == "discovery":
            return await self._generate_discovery_script(mac, hardware_info)

        elif self.default_action == "last_known":
            # Try to get any stale cached state
            cached = await self.state_cache.get_node(mac)
            if cached:
                # Use cached even if expired
                return await self._generate_cached_script(cached)
            # Fall through to local boot

        # Default: local boot
        return self._script_header(mac) + f"""
# Node not in cache
{offline_info}

echo   This node is not registered.
echo   Cannot register while offline.
echo   Booting from local disk...
echo

sleep 5
sanboot --drive 0x80 || exit
"""

    async def _generate_discovery_script(
        self,
        mac: str,
        hardware_info: dict | None = None,
    ) -> str:
        """Generate discovery script for unknown nodes.

        In offline mode, discovery collects hardware info but can't
        report to central. Information is logged locally.

        Args:
            mac: MAC address
            hardware_info: Optional hardware information

        Returns:
            iPXE boot script for discovery
        """
        offline_info = self._get_offline_info()

        return self._script_header(mac) + f"""
# Discovery Mode (Offline)
{offline_info}

echo   Running offline discovery...
echo
echo   MAC Address: {mac}
echo   Vendor: ${{manufacturer:undef}}
echo   Model: ${{product:undef}}
echo   Serial: ${{serial:undef}}
echo   UUID: ${{uuid:undef}}
echo
echo   Discovery data will be synced when online.
echo   Booting from local disk...
echo

sleep 10
sanboot --drive 0x80 || exit
"""

    def _script_header(self, mac: str) -> str:
        """Generate script header with offline banner.

        Args:
            mac: MAC address

        Returns:
            iPXE script header
        """
        return f"""#!ipxe
# PureBoot Site Agent - OFFLINE MODE
# MAC: {mac}
# Site: {self.site_id}

echo
echo *** PureBoot Site Agent - OFFLINE ***
echo
echo   Central controller is unreachable.
echo   Operating from cached state.
echo
"""

    def _get_offline_info(self) -> str:
        """Get offline information comment.

        Returns:
            Comment string with offline details
        """
        if self.offline_since:
            since_str = self.offline_since.strftime("%Y-%m-%d %H:%M:%S UTC")
            duration = datetime.now(timezone.utc) - self.offline_since
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            return f"# Offline Since: {since_str} ({hours}h {minutes}m)"
        return "# Offline Duration: Unknown"


class OfflineBootScripts:
    """Collection of static boot script templates for offline mode."""

    @staticmethod
    def local_boot(mac: str, site_id: str, reason: str = "") -> str:
        """Generate simple local boot script.

        Args:
            mac: MAC address
            site_id: Site ID
            reason: Optional reason for local boot

        Returns:
            iPXE script for local boot
        """
        reason_line = f"echo   Reason: {reason}" if reason else ""
        return f"""#!ipxe
# PureBoot Site Agent - Local Boot
# MAC: {mac}
# Site: {site_id}

echo
echo *** PureBoot - Local Boot ***
echo
{reason_line}
echo   Booting from local disk...
echo

sleep 2
sanboot --drive 0x80 || exit
"""

    @staticmethod
    def maintenance_mode(mac: str, site_id: str, message: str = "") -> str:
        """Generate maintenance mode script.

        Args:
            mac: MAC address
            site_id: Site ID
            message: Optional maintenance message

        Returns:
            iPXE script for maintenance mode
        """
        msg_line = f"echo   {message}" if message else "echo   System under maintenance."
        return f"""#!ipxe
# PureBoot Site Agent - Maintenance Mode
# MAC: {mac}
# Site: {site_id}

echo
echo *** PureBoot - MAINTENANCE MODE ***
echo
{msg_line}
echo   Booting from local disk...
echo

sleep 5
sanboot --drive 0x80 || exit
"""

    @staticmethod
    def error_script(mac: str, site_id: str, error: str) -> str:
        """Generate error script.

        Args:
            mac: MAC address
            site_id: Site ID
            error: Error message

        Returns:
            iPXE script showing error
        """
        return f"""#!ipxe
# PureBoot Site Agent - Error
# MAC: {mac}
# Site: {site_id}

echo
echo *** PureBoot - ERROR ***
echo
echo   Error: {error}
echo   Booting from local disk...
echo

sleep 10
sanboot --drive 0x80 || exit
"""
