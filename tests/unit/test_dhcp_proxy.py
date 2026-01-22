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
        assert parsed.is_ipxe is False

    def test_detect_uefi_client(self):
        """Detect UEFI x64 client."""
        packet = self._build_discover_packet(arch=0x07)  # UEFI x64
        parsed = DHCPPacket.parse(packet)

        assert parsed.client_arch == ClientArchitecture.UEFI_X64
        assert parsed.is_ipxe is False

    def test_detect_ipxe_via_user_class(self):
        """Detect iPXE client via user-class option 77."""
        packet = self._build_discover_packet(arch=0x07, user_class=b"iPXE")
        parsed = DHCPPacket.parse(packet)

        assert parsed.is_ipxe is True

    def test_detect_ipxe_via_option_175(self):
        """Detect iPXE client via encapsulated options 175."""
        packet = self._build_discover_packet(arch=0x07, ipxe_options=True)
        parsed = DHCPPacket.parse(packet)

        assert parsed.is_ipxe is True

    def test_get_boot_file_for_bios(self):
        """Return correct boot file for BIOS."""
        proxy = DHCPProxy(
            tftp_server="192.168.1.10",
            http_server="192.168.1.10:8080"
        )

        boot_file = proxy.get_boot_file(ClientArchitecture.BIOS)
        assert boot_file == "bios/undionly.kpxe"

    def test_get_boot_file_for_uefi(self):
        """Return correct boot file for UEFI."""
        proxy = DHCPProxy(
            tftp_server="192.168.1.10",
            http_server="192.168.1.10:8080"
        )

        boot_file = proxy.get_boot_file(ClientArchitecture.UEFI_X64)
        assert boot_file == "uefi/ipxe.efi"

    def test_get_ipxe_script_url(self):
        """Return HTTP URL for iPXE boot script."""
        proxy = DHCPProxy(
            tftp_server="192.168.1.10",
            http_server="192.168.1.10:8080"
        )

        url = proxy.get_ipxe_script_url()
        assert url == "http://192.168.1.10:8080/api/v1/ipxe/boot.ipxe"

    def test_build_offer_for_firmware(self):
        """Build DHCP offer for raw firmware (serves iPXE binary)."""
        proxy = DHCPProxy(
            tftp_server="192.168.1.10",
            http_server="192.168.1.10:8080"
        )
        packet = self._build_discover_packet(arch=0x07)  # UEFI
        parsed = DHCPPacket.parse(packet)

        response = proxy.build_offer(parsed)

        # Should contain TFTP path to iPXE binary
        assert b"uefi/ipxe.efi" in response
        # Should contain TFTP server option 66
        assert b"192.168.1.10" in response

    def test_build_offer_for_ipxe(self):
        """Build DHCP offer for iPXE (serves HTTP script URL)."""
        proxy = DHCPProxy(
            tftp_server="192.168.1.10",
            http_server="192.168.1.10:8080"
        )
        packet = self._build_discover_packet(arch=0x07, user_class=b"iPXE")
        parsed = DHCPPacket.parse(packet)

        response = proxy.build_offer(parsed)

        # Should contain HTTP URL to boot script
        assert b"http://192.168.1.10:8080/api/v1/ipxe/boot.ipxe" in response
        # Should NOT contain TFTP server option for iPXE
        # (iPXE uses HTTP, not TFTP for the script)

    def _build_discover_packet(
        self,
        arch: int,
        user_class: bytes | None = None,
        ipxe_options: bool = False
    ) -> bytes:
        """Build a minimal DHCP DISCOVER packet."""
        # BOOTP header (236 bytes minimum)
        packet = bytearray(400)
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

        i = 240

        # Option 93: Client System Architecture (PXE)
        packet[i] = 93  # Option code
        packet[i + 1] = 2   # Length
        packet[i + 2] = (arch >> 8) & 0xFF
        packet[i + 3] = arch & 0xFF
        i += 4

        # Option 77: User Class (for iPXE detection)
        if user_class:
            packet[i] = 77
            packet[i + 1] = len(user_class)
            packet[i + 2:i + 2 + len(user_class)] = user_class
            i += 2 + len(user_class)

        # Option 175: iPXE encapsulated options
        if ipxe_options:
            packet[i] = 175
            packet[i + 1] = 1  # Minimal length
            packet[i + 2] = 0  # Empty sub-option
            i += 3

        # Option 255: End
        packet[i] = 255

        return bytes(packet)
