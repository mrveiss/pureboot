"""iPXE script generation."""
from dataclasses import dataclass

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
