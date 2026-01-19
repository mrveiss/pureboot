# tests/integration/test_tftp_integration.py
"""Integration tests for TFTP server."""
import asyncio
import socket
from pathlib import Path

import pytest

from src.pxe.tftp_server import TFTPServer, TFTPPacket, OpCode


class TestTFTPServerIntegration:
    """Integration tests for TFTP server."""

    @pytest.fixture
    def tftp_root(self, tmp_path: Path) -> Path:
        """Create TFTP root with test files."""
        bios_dir = tmp_path / "bios"
        bios_dir.mkdir()
        (bios_dir / "test.bin").write_bytes(b"Hello TFTP!")
        return tmp_path

    @pytest.fixture
    async def tftp_server(self, tftp_root: Path):
        """Start TFTP server on random port."""
        server = TFTPServer(tftp_root, host="127.0.0.1", port=0)
        await server.start()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_read_small_file(self, tftp_server: TFTPServer, tftp_root: Path):
        """Read a small file via TFTP."""
        # Create UDP client
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        # Send RRQ
        rrq = b"\x00\x01bios/test.bin\x00octet\x00"
        sock.sendto(rrq, ("127.0.0.1", tftp_server.port))

        # Receive DATA
        loop = asyncio.get_event_loop()
        data, addr = await asyncio.wait_for(
            loop.sock_recvfrom(sock, 1024),
            timeout=5.0
        )

        packet = TFTPPacket.parse(data)
        assert packet.opcode == OpCode.DATA
        assert packet.block_num == 1
        assert packet.data == b"Hello TFTP!"

        sock.close()

    @pytest.mark.asyncio
    async def test_file_not_found_error(self, tftp_server: TFTPServer):
        """Get error for nonexistent file."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        rrq = b"\x00\x01nonexistent.bin\x00octet\x00"
        sock.sendto(rrq, ("127.0.0.1", tftp_server.port))

        loop = asyncio.get_event_loop()
        data, _ = await asyncio.wait_for(
            loop.sock_recvfrom(sock, 1024),
            timeout=5.0
        )

        packet = TFTPPacket.parse(data)
        assert packet.opcode == OpCode.ERROR
        assert packet.error_code == 1  # File not found

        sock.close()
