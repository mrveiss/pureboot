"""Tests for TFTP server."""
import pytest
from src.pxe.tftp_server import TFTPPacket, OpCode


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
