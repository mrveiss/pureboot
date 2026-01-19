"""Tests for TFTP server."""
import asyncio
from pathlib import Path

import pytest
from src.pxe.tftp_server import TFTPPacket, OpCode, TFTPHandler


class TestTFTPPacketParsing:
    """Test TFTP packet parsing."""

    def test_parse_rrq_packet(self):
        """Parse a Read Request packet."""
        # RRQ: opcode (2 bytes) + filename + 0 + mode + 0
        packet = b"\x00\x01bios/undionly.kpxe\x00octet\x00"
        parsed = TFTPPacket.parse(packet)

        assert parsed.opcode == OpCode.RRQ
        assert parsed.filename == "bios/undionly.kpxe"
        assert parsed.mode == "octet"

    def test_parse_rrq_with_options(self):
        """Parse RRQ with blksize option."""
        packet = b"\x00\x01test.bin\x00octet\x00blksize\x001024\x00"
        parsed = TFTPPacket.parse(packet)

        assert parsed.opcode == OpCode.RRQ
        assert parsed.filename == "test.bin"
        assert parsed.options.get("blksize") == "1024"

    def test_build_data_packet(self):
        """Build a DATA packet."""
        data = b"Hello, World!"
        packet = TFTPPacket.build_data(block_num=1, data=data)

        assert packet[:2] == b"\x00\x03"  # DATA opcode
        assert packet[2:4] == b"\x00\x01"  # Block number
        assert packet[4:] == data

    def test_build_error_packet(self):
        """Build an ERROR packet."""
        packet = TFTPPacket.build_error(error_code=1, message="File not found")

        assert packet[:2] == b"\x00\x05"  # ERROR opcode
        assert packet[2:4] == b"\x00\x01"  # Error code
        assert b"File not found" in packet

    def test_build_oack_packet(self):
        """Build an OACK (Option Acknowledgment) packet."""
        options = {"blksize": "1024", "tsize": "4096"}
        packet = TFTPPacket.build_oack(options)

        assert packet[:2] == b"\x00\x06"  # OACK opcode
        assert b"blksize\x001024\x00" in packet


class TestTFTPHandler:
    """Test TFTP file handling."""

    @pytest.fixture
    def tftp_root(self, tmp_path: Path) -> Path:
        """Create a temporary TFTP root."""
        bios_dir = tmp_path / "bios"
        bios_dir.mkdir()
        (bios_dir / "test.bin").write_bytes(b"X" * 1000)
        return tmp_path

    @pytest.mark.asyncio
    async def test_read_file_success(self, tftp_root: Path):
        """Read a file that exists."""
        handler = TFTPHandler(tftp_root)
        chunks = []

        async for chunk in handler.read_file("bios/test.bin"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"X" * 1000

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tftp_root: Path):
        """Error when file doesn't exist."""
        handler = TFTPHandler(tftp_root)

        with pytest.raises(FileNotFoundError):
            async for _ in handler.read_file("nonexistent.bin"):
                pass

    @pytest.mark.asyncio
    async def test_read_file_directory_traversal_blocked(self, tftp_root: Path):
        """Block directory traversal attempts."""
        handler = TFTPHandler(tftp_root)

        with pytest.raises(PermissionError):
            async for _ in handler.read_file("../../../etc/passwd"):
                pass

    @pytest.mark.asyncio
    async def test_read_file_with_blksize(self, tftp_root: Path):
        """Respect blksize option."""
        handler = TFTPHandler(tftp_root)
        chunks = []

        async for chunk in handler.read_file("bios/test.bin", blksize=256):
            chunks.append(chunk)
            assert len(chunk) <= 256

        assert len(chunks) == 4  # 1000 bytes / 256 = 4 chunks
