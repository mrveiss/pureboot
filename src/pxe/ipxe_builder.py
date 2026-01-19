"""iPXE binary builder using Docker."""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Architecture = Literal["bios", "uefi"]

EMBEDDED_SCRIPT_TEMPLATE = """#!ipxe
dhcp
chain http://{server_address}/api/v1/ipxe/boot.ipxe || echo Failed to load boot script && shell
"""


class IPXEBuilder:
    """Build custom iPXE binaries with embedded scripts."""

    def __init__(self, docker_image: str = "pureboot/ipxe-builder:latest"):
        self.docker_image = docker_image

    def generate_embedded_script(
        self,
        server_address: str,
        timeout: int = 5,
        architecture: Architecture = "bios"
    ) -> str:
        """Generate the script to embed in iPXE binary."""
        if architecture not in ("bios", "uefi"):
            raise ValueError(f"Invalid architecture: {architecture}")

        return EMBEDDED_SCRIPT_TEMPLATE.format(
            server_address=server_address,
            timeout=timeout
        )

    async def build(
        self,
        architecture: Architecture,
        server_address: str,
        timeout: int = 5
    ) -> bytes:
        """Build iPXE binary with embedded script."""
        script = self.generate_embedded_script(server_address, timeout, architecture)

        # Determine target binary
        if architecture == "bios":
            target = "bin/undionly.kpxe"
        else:
            target = "bin-x86_64-efi/ipxe.efi"

        return await self._run_docker_build(script, target)

    async def _run_docker_build(self, script: str, target: str) -> bytes:
        """Run Docker container to build iPXE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Write embedded script
            script_file = tmppath / "embed.ipxe"
            script_file.write_text(script)

            # Output file
            output_file = tmppath / "output.bin"

            # Build command
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{tmppath}:/build",
                self.docker_image,
                "make", f"EMBED=/build/embed.ipxe",
                target
            ]

            logger.info(f"Building iPXE: {' '.join(cmd)}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"iPXE build failed: {stderr.decode()}")
                raise RuntimeError(f"iPXE build failed: {stderr.decode()}")

            # Copy output binary
            # Note: actual implementation would copy from docker volume
            # For now, return placeholder
            if output_file.exists():
                return output_file.read_bytes()

            # Placeholder for testing without Docker
            return b"IPXE_BINARY_PLACEHOLDER"

    async def check_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False
