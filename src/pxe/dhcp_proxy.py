"""Proxy DHCP server for PXE boot options."""
import asyncio
import logging
import struct
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class ClientArchitecture(IntEnum):
    """Client system architecture types (RFC 4578)."""
    BIOS = 0x00
    UEFI_X64 = 0x07
    UEFI_X64_ALT = 0x09


BOOT_FILES = {
    ClientArchitecture.BIOS: "bios/undionly.kpxe",
    ClientArchitecture.UEFI_X64: "uefi/ipxe.efi",
    ClientArchitecture.UEFI_X64_ALT: "uefi/ipxe.efi",
}


@dataclass
class DHCPPacket:
    """Parsed DHCP packet."""
    op: int
    htype: int
    hlen: int
    xid: bytes
    client_mac: bytes
    client_arch: ClientArchitecture | None = None
    options: dict = None

    @classmethod
    def parse(cls, data: bytes) -> "DHCPPacket":
        """Parse raw DHCP packet."""
        if len(data) < 240:
            raise ValueError("Packet too short")

        op = data[0]
        htype = data[1]
        hlen = data[2]
        xid = data[4:8]
        client_mac = data[28:28 + hlen]

        # Parse options (after magic cookie at byte 236)
        options = {}
        client_arch = None

        if data[236:240] == b"\x63\x82\x53\x63":  # Magic cookie
            i = 240
            while i < len(data):
                opt_code = data[i]
                if opt_code == 255:  # End
                    break
                if opt_code == 0:  # Padding
                    i += 1
                    continue

                opt_len = data[i + 1]
                opt_data = data[i + 2:i + 2 + opt_len]
                options[opt_code] = opt_data

                # Option 93: Client System Architecture
                if opt_code == 93 and opt_len >= 2:
                    arch_type = struct.unpack("!H", opt_data[:2])[0]
                    try:
                        client_arch = ClientArchitecture(arch_type)
                    except ValueError:
                        client_arch = None

                i += 2 + opt_len

        return cls(
            op=op,
            htype=htype,
            hlen=hlen,
            xid=xid,
            client_mac=client_mac,
            client_arch=client_arch,
            options=options
        )


class DHCPProxy:
    """Proxy DHCP server for PXE options."""

    def __init__(self, tftp_server: str, host: str = "0.0.0.0", port: int = 4011):
        self.tftp_server = tftp_server
        self.host = host
        self.port = port
        self.transport = None

    def get_boot_file(self, arch: ClientArchitecture | None) -> str:
        """Get boot file path for client architecture."""
        if arch is None:
            arch = ClientArchitecture.BIOS
        return BOOT_FILES.get(arch, BOOT_FILES[ClientArchitecture.BIOS])

    def build_offer(self, request: DHCPPacket) -> bytes:
        """Build DHCP OFFER/ACK response with PXE options."""
        response = bytearray(300)

        # BOOTP header
        response[0] = 2  # op: BOOTREPLY
        response[1] = request.htype
        response[2] = request.hlen
        response[4:8] = request.xid

        # Copy client MAC
        response[28:28 + request.hlen] = request.client_mac

        # Server IP (siaddr) - option 66 is preferred but siaddr works too
        # This would need the actual server IP

        # Boot file (sname field, bytes 44-107)
        boot_file = self.get_boot_file(request.client_arch)
        boot_file_bytes = boot_file.encode("ascii")[:63]
        response[108:108 + len(boot_file_bytes)] = boot_file_bytes

        # Magic cookie
        response[236:240] = b"\x63\x82\x53\x63"

        # Options
        i = 240

        # Option 53: DHCP Message Type (OFFER = 2)
        response[i:i + 3] = bytes([53, 1, 2])
        i += 3

        # Option 54: Server Identifier
        server_ip = self._parse_ip(self.tftp_server)
        response[i:i + 6] = bytes([54, 4]) + server_ip
        i += 6

        # Option 66: TFTP Server Name
        tftp_bytes = self.tftp_server.encode("ascii")
        response[i:i + 2 + len(tftp_bytes) + 1] = bytes([66, len(tftp_bytes) + 1]) + tftp_bytes + b"\x00"
        i += 2 + len(tftp_bytes) + 1

        # Option 67: Boot File Name
        response[i:i + 2 + len(boot_file_bytes) + 1] = bytes([67, len(boot_file_bytes) + 1]) + boot_file_bytes + b"\x00"
        i += 2 + len(boot_file_bytes) + 1

        # Option 255: End
        response[i] = 255

        return bytes(response)

    def _parse_ip(self, ip_str: str) -> bytes:
        """Parse IP address string to bytes."""
        # Handle IP:port format
        ip = ip_str.split(":")[0]
        return bytes(int(x) for x in ip.split("."))

    async def start(self):
        """Start the proxy DHCP server."""
        loop = asyncio.get_event_loop()

        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: DHCPProxyProtocol(self),
            local_addr=(self.host, self.port)
        )

        logger.info(f"Proxy DHCP server started on {self.host}:{self.port}")

    async def stop(self):
        """Stop the proxy DHCP server."""
        if self.transport:
            self.transport.close()
            self.transport = None
            logger.info("Proxy DHCP server stopped")


class DHCPProxyProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for proxy DHCP."""

    def __init__(self, proxy: DHCPProxy):
        self.proxy = proxy
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        """Handle incoming DHCP packet."""
        try:
            packet = DHCPPacket.parse(data)

            if packet.op == 1:  # BOOTREQUEST
                mac = ":".join(f"{b:02x}" for b in packet.client_mac)
                arch = packet.client_arch.name if packet.client_arch else "unknown"
                logger.info(f"DHCP request from {mac} (arch: {arch})")

                response = self.proxy.build_offer(packet)
                self.transport.sendto(response, addr)

        except Exception as e:
            logger.error(f"Error handling DHCP packet: {e}")
