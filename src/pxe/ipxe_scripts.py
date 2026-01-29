"""iPXE script generation."""
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ASCII art logo - styled version
ASCII_LOGO = r"""
    ____                  ____              __
   / __ \__  __________  / __ )____  ____  / /_
  / /_/ / / / / ___/ _ \/ __  / __ \/ __ \/ __/
 / ____/ /_/ / /  /  __/ /_/ / /_/ / /_/ / /_
/_/    \__,_/_/   \___/_____/\____/\____/\__/
"""

# iPXE color codes (ANSI sequences)
COLOR_CYAN = "${cls}color --rgb 0x00d4ff 0x000000"
COLOR_WHITE = "color --rgb 0xffffff 0x000000"
COLOR_RESET = "colour --basic 7"


@dataclass
class IPXEScriptGenerator:
    """Generate iPXE boot scripts."""

    server_address: str
    timeout: int = 5
    logo_url: str | None = None

    def generate_boot_script(self) -> str:
        """Generate the main boot script served by the API."""
        lines = ["#!ipxe", ""]

        # Clear screen
        lines.append("console --x 1024 --y 768 2>/dev/null || console --x 800 --y 600 2>/dev/null ||")
        lines.append("cpair --foreground 7 --background 0 0")
        lines.append("")

        # Try PNG logo first
        if self.logo_url:
            lines.append(f"console --picture http://{self.server_address}{self.logo_url} --keep 2>/dev/null ||")
            lines.append("")

        # ASCII logo with cyan color
        lines.append("cpair --foreground 6 --background 0 1")
        lines.append("colour 1")
        for line in ASCII_LOGO.strip().split("\n"):
            # Escape special characters for iPXE echo
            escaped = line.replace("\\", "\\\\")
            lines.append(f"echo {escaped}")

        # Reset to white and show info
        lines.append("cpair --foreground 7 --background 0 0")
        lines.append("colour 0")
        lines.append("echo")
        lines.append("echo Network Boot Infrastructure")
        lines.append("echo ============================")
        lines.append("echo")
        lines.append("echo MAC Address: ${mac}")
        lines.append("echo IP Address:  ${ip}")
        lines.append("echo")
        lines.append("echo Contacting PureBoot server...")
        lines.append("echo")

        # Fetch and chain to boot instructions
        timeout_ms = self.timeout * 1000
        lines.extend([
            ":retry",
            f"chain --timeout {timeout_ms} http://{self.server_address}/api/v1/boot?mac=${{mac:hexhyp}} && goto end ||",
            "echo Server unreachable. Retrying in 5 seconds...",
            "sleep 5",
            "goto retry",
            "",
            ":end",
        ])

        return "\n".join(lines)

    def generate_local_boot(self) -> str:
        """Generate script for local boot."""
        return """#!ipxe
# PureBoot - Boot from local disk
echo Booting from local disk...
exit
"""

    def generate_embedded_script(self) -> str:
        """Generate script to embed in iPXE binary."""
        return f"""#!ipxe
:start
dhcp
chain http://{self.server_address}/api/v1/ipxe/boot.ipxe || goto retry
goto end
:retry
echo Server unreachable, retrying in 5s...
sleep 5
goto start
:end
"""

    def generate_autoexec_script(self) -> str:
        """Generate the autoexec.ipxe script served via TFTP.

        This script is loaded by iPXE binaries and chains to the HTTP API.
        It's placed in the TFTP root so iPXE can fetch it after DHCP.
        """
        return f"""#!ipxe
# PureBoot autoexec.ipxe - Auto-generated, do not edit manually
# Server: {self.server_address}

echo PureBoot iPXE starting...
echo Network interface: ${{net0/mac}}
echo IP address: ${{net0/ip}}
echo Gateway: ${{net0/gateway}}
echo

ifopen net0
echo
echo Fetching boot script from PureBoot server...
chain http://{self.server_address}/api/v1/boot?mac=${{net0/mac}} || goto retry

:retry
echo
echo Chain failed, retrying in 5 seconds...
sleep 5
chain http://{self.server_address}/api/v1/boot?mac=${{net0/mac}} || shell
"""

    def generate_install_script(
        self,
        kernel_url: str,
        initrd_url: str,
        cmdline: str
    ) -> str:
        """Generate script for OS installation."""
        return f"""#!ipxe
# PureBoot - OS Installation
echo Starting installation...
echo
kernel {kernel_url} {cmdline}
initrd {initrd_url}
boot
"""


def update_tftp_boot_scripts(tftp_root: Path, server_address: str) -> None:
    """Update TFTP boot scripts with current server address.

    This should be called at startup to ensure boot scripts
    have the correct server address after IP changes.

    Args:
        tftp_root: Path to TFTP root directory
        server_address: Server address in host:port format
    """
    generator = IPXEScriptGenerator(server_address=server_address)

    # Main autoexec.ipxe in TFTP root
    autoexec_path = tftp_root / "autoexec.ipxe"
    autoexec_content = generator.generate_autoexec_script()

    # Check if update is needed
    needs_update = True
    if autoexec_path.exists():
        existing = autoexec_path.read_text()
        if existing == autoexec_content:
            logger.debug("TFTP boot scripts already up to date")
            needs_update = False
        elif f"Server: {server_address}" not in existing:
            logger.info(f"Server address changed, updating TFTP boot scripts")

    if needs_update:
        # Write autoexec.ipxe
        autoexec_path.write_text(autoexec_content)
        logger.info(f"Updated {autoexec_path} with server address {server_address}")

        # Also update uefi/boot.ipxe for UEFI-specific chaining
        uefi_boot_path = tftp_root / "uefi" / "boot.ipxe"
        if uefi_boot_path.parent.exists():
            uefi_content = f"""#!ipxe
# PureBoot UEFI boot script - Auto-generated
dhcp
chain http://{server_address}/api/v1/ipxe/boot.ipxe || shell
"""
            uefi_boot_path.write_text(uefi_content)
            logger.info(f"Updated {uefi_boot_path}")

        # Update bios/boot.ipxe for BIOS-specific chaining
        bios_boot_path = tftp_root / "bios" / "boot.ipxe"
        if bios_boot_path.parent.exists():
            bios_content = f"""#!ipxe
# PureBoot BIOS boot script - Auto-generated
dhcp
chain http://{server_address}/api/v1/ipxe/boot.ipxe || shell
"""
            bios_boot_path.write_text(bios_content)
            logger.info(f"Updated {bios_boot_path}")
