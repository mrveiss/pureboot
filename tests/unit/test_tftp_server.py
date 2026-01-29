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


class TestTFTPHandlerPiDiscovery:
    """Test TFTP handler Pi discovery fallback functionality."""

    @pytest.fixture
    def pi_tftp_root(self, tmp_path: Path) -> dict:
        """Create TFTP root with Pi discovery and nodes directories."""
        # Main TFTP root
        tftp_root = tmp_path / "tftp"
        tftp_root.mkdir()

        # Pi nodes directory
        nodes_dir = tftp_root / "pi-nodes"
        nodes_dir.mkdir()

        # Create a known node directory
        known_node = nodes_dir / "d83add36"
        known_node.mkdir()
        (known_node / "start4.elf").write_bytes(b"known node start4")
        (known_node / "config.txt").write_bytes(b"known node config")

        # Pi discovery directory
        discovery_dir = tftp_root / "pi-discovery"
        discovery_dir.mkdir()
        (discovery_dir / "bootcode.bin").write_bytes(b"discovery bootcode")
        (discovery_dir / "start.elf").write_bytes(b"discovery start")
        (discovery_dir / "start4.elf").write_bytes(b"discovery start4")
        (discovery_dir / "config.txt").write_bytes(b"discovery config")

        return {
            "root": tftp_root,
            "nodes_dir": nodes_dir,
            "discovery_dir": discovery_dir,
        }

    @pytest.mark.asyncio
    async def test_known_node_returns_node_file(self, pi_tftp_root):
        """Request for known node serial returns node-specific file."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        chunks = []
        async for chunk in handler.read_file("/d83add36/start4.elf"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"known node start4"

    @pytest.mark.asyncio
    async def test_unknown_node_falls_back_to_discovery(self, pi_tftp_root):
        """Request for unknown serial falls back to discovery directory."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        chunks = []
        # a1b2c3d4 is an unknown serial
        async for chunk in handler.read_file("/a1b2c3d4/start4.elf"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"discovery start4"

    @pytest.mark.asyncio
    async def test_pi3_unknown_gets_bootcode_from_discovery(self, pi_tftp_root):
        """Pi 3 bootcode.bin request from unknown serial uses discovery."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        chunks = []
        async for chunk in handler.read_file("/abcd1234/bootcode.bin"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"discovery bootcode"

    @pytest.mark.asyncio
    async def test_discovery_callback_called(self, pi_tftp_root):
        """Discovery callback is called for unknown Pi requests."""
        callback_calls = []

        def on_discovery(serial, filename):
            callback_calls.append((serial, filename))

        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
            on_pi_discovery=on_discovery,
        )

        # Make request for unknown Pi
        async for _ in handler.read_file("/abcd1234/start4.elf"):
            pass

        assert len(callback_calls) == 1
        assert callback_calls[0] == ("abcd1234", "start4.elf")

    @pytest.mark.asyncio
    async def test_discovery_disabled_returns_not_found(self, pi_tftp_root):
        """With discovery disabled, unknown Pi request returns FileNotFoundError."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=False,
        )

        with pytest.raises(FileNotFoundError):
            async for _ in handler.read_file("/abcd1234/start4.elf"):
                pass

    @pytest.mark.asyncio
    async def test_non_pi_request_not_affected(self, pi_tftp_root):
        """Non-Pi requests are not affected by discovery logic."""
        # Create a regular file in the TFTP root
        regular_file = pi_tftp_root["root"] / "bios"
        regular_file.mkdir()
        (regular_file / "ipxe.efi").write_bytes(b"regular ipxe")

        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        chunks = []
        async for chunk in handler.read_file("/bios/ipxe.efi"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"regular ipxe"

    @pytest.mark.asyncio
    async def test_invalid_serial_not_treated_as_pi_request(self, pi_tftp_root):
        """Requests with invalid serial format don't trigger discovery."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        # "toolong12" is 9 chars, not 8, so should not be treated as Pi serial
        with pytest.raises(FileNotFoundError):
            async for _ in handler.read_file("/toolong12/start4.elf"):
                pass

    @pytest.mark.asyncio
    async def test_non_boot_file_not_treated_as_pi_request(self, pi_tftp_root):
        """Requests for non-boot files with valid serial don't trigger discovery."""
        handler = TFTPHandler(
            root=pi_tftp_root["root"],
            pi_discovery_enabled=True,
            pi_discovery_dir=pi_tftp_root["discovery_dir"],
            pi_nodes_dir=pi_tftp_root["nodes_dir"],
        )

        # Valid serial, but "random.txt" is not a Pi boot file
        with pytest.raises(FileNotFoundError):
            async for _ in handler.read_file("/a1b2c3d4/random.txt"):
                pass
