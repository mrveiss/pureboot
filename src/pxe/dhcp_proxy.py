"""Proxy DHCP server for PXE boot options.

This proxy DHCP server implements iPXE chainloading:
1. Raw UEFI/BIOS firmware requests → serve iPXE binary (ipxe.efi/undionly.kpxe)
2. iPXE requests (detected via user-class) → serve HTTP boot script URL

This enables network boot without requiring custom-compiled iPXE binaries.
"""
import asyncio
import logging
import struct
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger(__name__)


class ClientArchitecture(IntEnum):
    """Client system architecture types (RFC 4578)."""
    BIOS = 0x00
    UEFI_X64 = 0x07
    UEFI_X64_ALT = 0x09


# Boot files for initial PXE boot (firmware → iPXE)
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
    is_ipxe: bool = False
    options: dict = field(default_factory=dict)

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
        is_ipxe = False

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

                # Option 77: User Class - iPXE identifies itself here
                if opt_code == 77:
                    user_class = opt_data.decode("ascii", errors="ignore")
                    if "iPXE" in user_class:
                        is_ipxe = True

                # Option 175: iPXE encapsulated options (alternative detection)
                if opt_code == 175:
                    is_ipxe = True

                i += 2 + opt_len

        return cls(
            op=op,
            htype=htype,
            hlen=hlen,
            xid=xid,
            client_mac=client_mac,
            client_arch=client_arch,
            is_ipxe=is_ipxe,
            options=options
        )


class DHCPProxy:
    """Proxy DHCP server for PXE options with iPXE chainloading support.

    This server implements two-stage booting:
    1. First request (raw firmware): Serve iPXE binary via TFTP
    2. Second request (iPXE): Serve HTTP boot script URL

    This allows stock iPXE binaries to work without embedded scripts.
    """

    def __init__(
        self,
        tftp_server: str,
        http_server: str,
        host: str = "0.0.0.0",
        port: int = 4011
    ):
        """Initialize proxy DHCP server.

        Args:
            tftp_server: TFTP server IP for serving iPXE binaries
            http_server: HTTP server address (ip:port) for boot scripts
            host: Address to bind to
            port: Port to listen on (default 4011 for ProxyDHCP)
        """
        self.tftp_server = tftp_server
        self.http_server = http_server
        self.host = host
        self.port = port
        self.transport = None

    def get_boot_file(self, arch: ClientArchitecture | None) -> str:
        """Get boot file path for client architecture."""
        if arch is None:
            arch = ClientArchitecture.BIOS
        return BOOT_FILES.get(arch, BOOT_FILES[ClientArchitecture.BIOS])

    def get_ipxe_script_url(self) -> str:
        """Get the HTTP URL for the iPXE boot script."""
        return f"http://{self.http_server}/api/v1/ipxe/boot.ipxe"

    def build_offer(self, request: DHCPPacket) -> bytes:
        """Build DHCP OFFER/ACK response with PXE options.

        For raw firmware: Returns TFTP server + boot file (iPXE binary)
        For iPXE clients: Returns HTTP boot script URL
        """
        response = bytearray(512)  # Larger buffer for HTTP URLs

        # BOOTP header
        response[0] = 2  # op: BOOTREPLY
        response[1] = request.htype
        response[2] = request.hlen
        response[4:8] = request.xid

        # Copy client MAC
        response[28:28 + request.hlen] = request.client_mac

        # Determine boot file based on client type
        if request.is_ipxe:
            # iPXE client - serve HTTP boot script URL
            boot_file = self.get_ipxe_script_url()
        else:
            # Raw firmware - serve iPXE binary via TFTP
            boot_file = self.get_boot_file(request.client_arch)

        boot_file_bytes = boot_file.encode("ascii")

        # For non-iPXE, put boot file in sname field (bytes 108-171, 63 chars max)
        # For iPXE with HTTP URL, we only use option 67
        if not request.is_ipxe:
            sname_bytes = boot_file_bytes[:63]
            response[108:108 + len(sname_bytes)] = sname_bytes

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

        if not request.is_ipxe:
            # Option 66: TFTP Server Name (only for initial boot)
            tftp_bytes = self.tftp_server.encode("ascii")
            response[i:i + 2 + len(tftp_bytes) + 1] = (
                bytes([66, len(tftp_bytes) + 1]) + tftp_bytes + b"\x00"
            )
            i += 2 + len(tftp_bytes) + 1

        # Option 67: Boot File Name
        # For iPXE: HTTP URL to boot script
        # For firmware: Path to iPXE binary
        response[i:i + 2 + len(boot_file_bytes) + 1] = (
            bytes([67, len(boot_file_bytes) + 1]) + boot_file_bytes + b"\x00"
        )
        i += 2 + len(boot_file_bytes) + 1

        # Option 255: End
        response[i] = 255

        return bytes(response[:i + 1])

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
                arch = packet.client_arch.name if packet.client_arch else "unknown"
                client_type = "iPXE" if packet.is_ipxe else "firmware"

                if packet.is_ipxe:
                    boot_target = self.proxy.get_ipxe_script_url()
                else:
                    boot_target = self.proxy.get_boot_file(packet.client_arch)

                logger.info(
                    f"DHCP request: {client_type} ({arch}) → {boot_target}"
                )

                response = self.proxy.build_offer(packet)
                self.transport.sendto(response, addr)

        except Exception as e:
            logger.error(f"Error handling DHCP packet: {e}")
