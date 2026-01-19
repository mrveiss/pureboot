"""iPXE script generation."""
from dataclasses import dataclass

ASCII_LOGO = r"""
 ____                 ____              _
|  _ \ _   _ _ __ ___| __ )  ___   ___ | |_
| |_) | | | | '__/ _ \  _ \ / _ \ / _ \| __|
|  __/| |_| | | |  __/ |_) | (_) | (_) | |_
|_|    \__,_|_|  \___|____/ \___/ \___/ \__|
"""


@dataclass
class IPXEScriptGenerator:
    """Generate iPXE boot scripts."""

    server_address: str
    timeout: int = 5
    show_menu: bool = True
    logo_url: str | None = None

    def generate_boot_script(self) -> str:
        """Generate the main boot script served by the API."""
        lines = ["#!ipxe", ""]

        # Try PNG logo, fall back to ASCII
        if self.logo_url:
            lines.append(f"console --picture http://{self.server_address}{self.logo_url} 2>/dev/null ||")
            lines.append("")

        # ASCII logo
        for line in ASCII_LOGO.strip().split("\n"):
            lines.append(f"echo {line}")
        lines.append("echo")
        lines.append("echo Contacting PureBoot server...")
        lines.append("echo")

        # Fetch and chain to boot instructions
        timeout_ms = self.timeout * 1000
        lines.extend([
            ":retry",
            f"chain --timeout {timeout_ms} http://{self.server_address}/api/v1/boot?mac=${{mac:hexhyp}} && goto end ||",
            "echo Server unreachable. Retrying in 5 seconds...",
            "echo Press 'L' for local boot, 'S' for shell",
            "sleep 5 || goto localboot",
            "goto retry",
            "",
        ])

        if self.show_menu:
            lines.extend([
                ":menu",
                "menu PureBoot Options",
                "item --key c continue Continue with assigned action",
                "item --key l localboot Boot from local disk",
                "item --key r retry Retry server connection",
                "item --key s shell iPXE shell",
                f"choose --default continue --timeout {timeout_ms} selected || goto continue",
                "goto ${selected}",
                "",
                ":continue",
                f"chain http://{self.server_address}/api/v1/boot?mac=${{mac:hexhyp}}",
                "",
            ])

        lines.extend([
            ":localboot",
            "echo Booting from local disk...",
            "exit",
            "",
            ":shell",
            "shell",
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
dhcp
chain http://{self.server_address}/api/v1/ipxe/boot.ipxe || shell
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
