"""Tests for Proxy DHCP server."""
import pytest
from src.pxe.dhcp_proxy import DHCPPacket, DHCPProxy, ClientArchitecture


class TestDHCPPacketParsing:
    """Test DHCP packet parsing."""

    def test_parse_discover_packet(self):
        """Parse a DHCP DISCOVER packet."""
        # Minimal DHCP DISCOVER with client arch option (93)
        packet = self._build_discover_packet(arch=0x00)  # BIOS
        parsed = DHCPPacket.parse(packet)

        assert parsed.op == 1  # BOOTREQUEST
        assert parsed.client_arch == ClientArchitecture.BIOS

    def test_detect_uefi_client(self):
        """Detect UEFI x64 client."""
        packet = self._build_discover_packet(arch=0x07)  # UEFI x64
        parsed = DHCPPacket.parse(packet)

        assert parsed.client_arch == ClientArchitecture.UEFI_X64

    def test_get_boot_file_for_bios(self):
        """Return correct boot file for BIOS."""
        proxy = DHCPProxy(tftp_server="192.168.1.10")

        boot_file = proxy.get_boot_file(ClientArchitecture.BIOS)
        assert boot_file == "bios/undionly.kpxe"

    def test_get_boot_file_for_uefi(self):
        """Return correct boot file for UEFI."""
        proxy = DHCPProxy(tftp_server="192.168.1.10")

        boot_file = proxy.get_boot_file(ClientArchitecture.UEFI_X64)
        assert boot_file == "uefi/ipxe.efi"

    def _build_discover_packet(self, arch: int) -> bytes:
        """Build a minimal DHCP DISCOVER packet."""
        # BOOTP header (236 bytes minimum)
        packet = bytearray(300)
        packet[0] = 1  # op: BOOTREQUEST
        packet[1] = 1  # htype: Ethernet
        packet[2] = 6  # hlen: MAC length
        packet[3] = 0  # hops

        # Transaction ID
        packet[4:8] = b"\x12\x34\x56\x78"

        # Client MAC (bytes 28-33)
        packet[28:34] = b"\x00\x11\x22\x33\x44\x55"

        # Magic cookie (bytes 236-240)
        packet[236:240] = b"\x63\x82\x53\x63"

        # Option 93: Client System Architecture (PXE)
        packet[240] = 93  # Option code
        packet[241] = 2   # Length
        packet[242] = (arch >> 8) & 0xFF
        packet[243] = arch & 0xFF

        # Option 255: End
        packet[244] = 255

        return bytes(packet)
