"""TFTP server implementation (RFC 1350, 2347, 2348)."""
import asyncio
import logging
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_BLKSIZE = 512
MAX_BLKSIZE = 65464


class OpCode(IntEnum):
    """TFTP operation codes."""
    RRQ = 1    # Read request
    WRQ = 2    # Write request
    DATA = 3   # Data
    ACK = 4    # Acknowledgment
    ERROR = 5  # Error
    OACK = 6   # Option acknowledgment


class ErrorCode(IntEnum):
    """TFTP error codes."""
    NOT_DEFINED = 0
    FILE_NOT_FOUND = 1
    ACCESS_VIOLATION = 2
    DISK_FULL = 3
    ILLEGAL_OPERATION = 4
    UNKNOWN_TID = 5
    FILE_EXISTS = 6
    NO_SUCH_USER = 7


@dataclass
class TFTPPacket:
    """Parsed TFTP packet."""
    opcode: OpCode
    filename: str = ""
    mode: str = "octet"
    block_num: int = 0
    data: bytes = b""
    error_code: int = 0
    error_message: str = ""
    options: dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: bytes) -> "TFTPPacket":
        """Parse raw bytes into a TFTPPacket."""
        if len(data) < 2:
            raise ValueError("Packet too short")

        opcode = OpCode(struct.unpack("!H", data[:2])[0])

        if opcode in (OpCode.RRQ, OpCode.WRQ):
            return cls._parse_request(opcode, data[2:])
        elif opcode == OpCode.DATA:
            return cls._parse_data(data[2:])
        elif opcode == OpCode.ACK:
            return cls._parse_ack(data[2:])
        elif opcode == OpCode.ERROR:
            return cls._parse_error(data[2:])
        else:
            raise ValueError(f"Unknown opcode: {opcode}")

    @classmethod
    def _parse_request(cls, opcode: OpCode, data: bytes) -> "TFTPPacket":
        """Parse RRQ/WRQ packet."""
        parts = data.split(b"\x00")
        filename = parts[0].decode("ascii")
        mode = parts[1].decode("ascii").lower() if len(parts) > 1 else "octet"

        # Parse options (RFC 2347)
        options = {}
        i = 2
        while i + 1 < len(parts) and parts[i]:
            key = parts[i].decode("ascii").lower()
            value = parts[i + 1].decode("ascii") if i + 1 < len(parts) else ""
            options[key] = value
            i += 2

        return cls(opcode=opcode, filename=filename, mode=mode, options=options)

    @classmethod
    def _parse_data(cls, data: bytes) -> "TFTPPacket":
        """Parse DATA packet."""
        block_num = struct.unpack("!H", data[:2])[0]
        return cls(opcode=OpCode.DATA, block_num=block_num, data=data[2:])

    @classmethod
    def _parse_ack(cls, data: bytes) -> "TFTPPacket":
        """Parse ACK packet."""
        block_num = struct.unpack("!H", data[:2])[0]
        return cls(opcode=OpCode.ACK, block_num=block_num)

    @classmethod
    def _parse_error(cls, data: bytes) -> "TFTPPacket":
        """Parse ERROR packet."""
        error_code = struct.unpack("!H", data[:2])[0]
        error_message = data[2:].split(b"\x00")[0].decode("ascii")
        return cls(opcode=OpCode.ERROR, error_code=error_code, error_message=error_message)

    @staticmethod
    def build_data(block_num: int, data: bytes) -> bytes:
        """Build a DATA packet."""
        return struct.pack("!HH", OpCode.DATA, block_num) + data

    @staticmethod
    def build_ack(block_num: int) -> bytes:
        """Build an ACK packet."""
        return struct.pack("!HH", OpCode.ACK, block_num)

    @staticmethod
    def build_error(error_code: int, message: str) -> bytes:
        """Build an ERROR packet."""
        return struct.pack("!HH", OpCode.ERROR, error_code) + message.encode("ascii") + b"\x00"

    @staticmethod
    def build_oack(options: dict[str, str]) -> bytes:
        """Build an OACK packet."""
        packet = struct.pack("!H", OpCode.OACK)
        for key, value in options.items():
            packet += key.encode("ascii") + b"\x00" + value.encode("ascii") + b"\x00"
        return packet


class TFTPHandler:
    """Handles TFTP file operations with Pi discovery fallback.

    This handler supports automatic Pi discovery by detecting requests
    that look like Pi network boot (8-char hex serial + known boot file)
    and falling back to a discovery directory when the serial directory
    doesn't exist.
    """

    def __init__(
        self,
        root: Path,
        pi_discovery_enabled: bool = False,
        pi_discovery_dir: Optional[Path] = None,
        pi_nodes_dir: Optional[Path] = None,
        on_pi_discovery: Optional[Callable[[str, str], None]] = None,
    ):
        """Initialize handler with TFTP root directory.

        Args:
            root: TFTP root directory.
            pi_discovery_enabled: Enable Pi auto-discovery fallback.
            pi_discovery_dir: Directory containing discovery boot files.
            pi_nodes_dir: Directory containing per-node directories.
            on_pi_discovery: Callback when a discovery request is detected.
                Called with (serial, filename).
        """
        self.root = Path(root).resolve()
        self.pi_discovery_enabled = pi_discovery_enabled
        self.pi_discovery_dir = Path(pi_discovery_dir).resolve() if pi_discovery_dir else None
        self.pi_nodes_dir = Path(pi_nodes_dir).resolve() if pi_nodes_dir else None
        self.on_pi_discovery = on_pi_discovery

    def _is_pi_serial_request(self, path: str) -> tuple[bool, str, str]:
        """Check if a TFTP path looks like a Pi serial number request.

        Pi network boot requests files with paths like:
        - /<serial>/start4.elf
        - /<serial>/bootcode.bin
        - /<serial>/config.txt

        Uses combined detection: path must have 8-hex-char directory
        AND the file must be a known Pi boot file.

        Args:
            path: The TFTP request path.

        Returns:
            Tuple of (is_pi_request, serial_number, filename).
        """
        # Import here to avoid circular imports
        from src.pxe.pi_manager import is_pi_serial_request
        return is_pi_serial_request(path)

    def _resolve_path(self, filename: str) -> Path:
        """Resolve filename to safe path within root.

        For Pi network boot requests, this method implements fallback logic:
        1. Check if the serial directory exists in pi_nodes_dir
        2. If not, and discovery is enabled, fallback to pi_discovery_dir
        3. Otherwise, use the standard root path resolution
        """
        # Strip leading slashes - TFTP paths are relative to root
        original_filename = filename
        filename = filename.lstrip("/")

        # Check for Pi discovery fallback
        if self.pi_discovery_enabled and self.pi_discovery_dir:
            is_pi_request, serial, boot_file = self._is_pi_serial_request(original_filename)

            if is_pi_request:
                # Check if this serial has a registered node directory
                if self.pi_nodes_dir:
                    node_dir = self.pi_nodes_dir / serial
                    if node_dir.exists():
                        # Node exists, resolve normally from root
                        requested = (self.root / filename).resolve()
                        if not str(requested).startswith(str(self.root)):
                            raise PermissionError(f"Access denied: {filename}")
                        return requested

                # Unknown Pi - use discovery fallback
                logger.info(
                    f"Pi discovery: Unknown serial {serial} requesting {boot_file}, "
                    f"using discovery directory"
                )

                # Call discovery callback if set
                if self.on_pi_discovery:
                    try:
                        self.on_pi_discovery(serial, boot_file)
                    except Exception as e:
                        logger.error(f"Pi discovery callback error: {e}")

                # Resolve from discovery directory
                requested = (self.pi_discovery_dir / boot_file).resolve()
                if not str(requested).startswith(str(self.pi_discovery_dir)):
                    raise PermissionError(f"Access denied: {boot_file}")
                return requested

        # Standard path resolution
        requested = (self.root / filename).resolve()

        # Ensure path is within root (prevent directory traversal)
        if not str(requested).startswith(str(self.root)):
            raise PermissionError(f"Access denied: {filename}")

        return requested

    async def read_file(
        self, filename: str, blksize: int = DEFAULT_BLKSIZE
    ) -> AsyncIterator[bytes]:
        """Read file in chunks for TFTP transfer."""
        filepath = self._resolve_path(filename)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        if not filepath.is_file():
            raise PermissionError(f"Not a file: {filename}")

        blksize = min(blksize, MAX_BLKSIZE)

        # Read file in chunks
        loop = asyncio.get_event_loop()
        with open(filepath, "rb") as f:
            while True:
                chunk = await loop.run_in_executor(None, f.read, blksize)
                if not chunk:
                    break
                yield chunk

    def get_file_size(self, filename: str) -> int:
        """Get file size for tsize option."""
        filepath = self._resolve_path(filename)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        return filepath.stat().st_size


class TFTPTransfer:
    """Handles a single TFTP transfer session with proper ACK handling."""

    TIMEOUT = 3.0  # Seconds to wait for ACK
    MAX_RETRIES = 3

    def __init__(self, handler: TFTPHandler, client_addr: tuple):
        self.handler = handler
        self.client_addr = client_addr
        self.transport = None
        self.ack_event = asyncio.Event()
        self.last_ack_block = -1
        self.done = False

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        """Handle incoming packet (should be ACK)."""
        try:
            packet = TFTPPacket.parse(data)
            if packet.opcode == OpCode.ACK:
                self.last_ack_block = packet.block_num
                self.ack_event.set()
            elif packet.opcode == OpCode.ERROR:
                # Hyper-V UEFI sends "User aborted" immediately but then retries
                # Only abort if we've already started sending data
                if self.last_ack_block >= 0:
                    logger.error(f"Client error during transfer: {packet.error_message}")
                    self.done = True
                    self.ack_event.set()
                else:
                    logger.warning(f"Client sent early error (ignoring): {packet.error_message}")
        except Exception as e:
            logger.error(f"Error parsing ACK: {e}")

    def error_received(self, exc):
        logger.error(f"Transfer error: {exc}")
        self.done = True
        self.ack_event.set()

    def connection_lost(self, exc):
        self.done = True
        self.ack_event.set()

    async def wait_for_ack(self, expected_block: int) -> bool:
        """Wait for ACK with timeout and retry."""
        for retry in range(self.MAX_RETRIES):
            self.ack_event.clear()
            try:
                await asyncio.wait_for(self.ack_event.wait(), timeout=self.TIMEOUT)
                if self.done:
                    return False
                if self.last_ack_block == expected_block:
                    return True
            except asyncio.TimeoutError:
                if retry < self.MAX_RETRIES - 1:
                    logger.debug(f"ACK timeout for block {expected_block}, retry {retry + 1}")
        return False

    async def send_file(self, filename: str, options: dict) -> bool:
        """Send file to client with proper ACK handling."""
        try:
            blksize = DEFAULT_BLKSIZE

            # Handle TFTP options (RFC 2347)
            if options:
                # Build OACK with options we support
                oack_options = {}

                # tsize - report file size if client requested it
                if "tsize" in options:
                    try:
                        file_size = self.handler.get_file_size(filename)
                        oack_options["tsize"] = str(file_size)
                    except FileNotFoundError:
                        pass

                # blksize - accept requested block size (up to our max)
                if "blksize" in options:
                    requested = int(options["blksize"])
                    blksize = min(requested, MAX_BLKSIZE)
                    oack_options["blksize"] = str(blksize)

                # Send OACK if we have any options to acknowledge
                if oack_options:
                    oack_packet = TFTPPacket.build_oack(oack_options)
                    logger.info(f"Sending OACK: {oack_options} (packet: {oack_packet.hex()})")
                    self.transport.sendto(oack_packet, self.client_addr)

                    # Wait for ACK 0 (client acknowledges OACK)
                    if not await self.wait_for_ack(0):
                        logger.error("No ACK for OACK")
                        return False
                    logger.info("OACK acknowledged by client")

            # Send file data
            block_num = 1
            chunk = b""
            async for chunk in self.handler.read_file(filename, blksize):
                data_packet = TFTPPacket.build_data(block_num, chunk)

                # Send and wait for ACK with retry
                for retry in range(self.MAX_RETRIES):
                    self.transport.sendto(data_packet, self.client_addr)
                    if await self.wait_for_ack(block_num):
                        break
                    if retry == self.MAX_RETRIES - 1:
                        logger.error(f"Transfer failed: no ACK for block {block_num}")
                        return False

                block_num += 1

            # Send final empty packet if last chunk was full
            if len(chunk) == blksize:
                data_packet = TFTPPacket.build_data(block_num, b"")
                self.transport.sendto(data_packet, self.client_addr)
                await self.wait_for_ack(block_num)

            logger.info(f"Transfer complete: {filename} ({block_num - 1} blocks)")
            return True

        except FileNotFoundError:
            error = TFTPPacket.build_error(ErrorCode.FILE_NOT_FOUND, "File not found")
            self.transport.sendto(error, self.client_addr)
            return False

        except PermissionError as e:
            error = TFTPPacket.build_error(ErrorCode.ACCESS_VIOLATION, str(e))
            self.transport.sendto(error, self.client_addr)
            return False

        except Exception as e:
            logger.error(f"Transfer error: {e}")
            error = TFTPPacket.build_error(ErrorCode.NOT_DEFINED, str(e))
            self.transport.sendto(error, self.client_addr)
            return False


class TFTPServerProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for TFTP server."""

    def __init__(self, handler: TFTPHandler, on_request: callable = None):
        self.handler = handler
        self.on_request = on_request
        self.transport = None
        self.transfers: dict[tuple, asyncio.Task] = {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        """Handle incoming TFTP packet."""
        try:
            packet = TFTPPacket.parse(data)

            if packet.opcode == OpCode.RRQ:
                logger.info(f"RRQ from {addr}: {packet.filename} options={packet.options}")
                if self.on_request:
                    self.on_request(addr, packet.filename)
                # Start transfer in background task with dedicated socket
                task = asyncio.create_task(
                    self._handle_read_request(addr, packet)
                )
                self.transfers[addr] = task

            elif packet.opcode == OpCode.WRQ:
                # Write requests not supported
                error = TFTPPacket.build_error(
                    ErrorCode.ACCESS_VIOLATION,
                    "Write not supported"
                )
                self.transport.sendto(error, addr)

        except Exception as e:
            logger.error(f"Error handling packet from {addr}: {e}")
            error = TFTPPacket.build_error(ErrorCode.NOT_DEFINED, str(e))
            self.transport.sendto(error, addr)

    async def _handle_read_request(self, client_addr: tuple, packet: TFTPPacket):
        """Handle a read request using a dedicated socket for the transfer."""
        transfer = None
        transport = None
        try:
            # Create dedicated socket for this transfer (TFTP spec requirement)
            loop = asyncio.get_event_loop()
            transfer = TFTPTransfer(self.handler, client_addr)
            transport, _ = await loop.create_datagram_endpoint(
                lambda: transfer,
                local_addr=("0.0.0.0", 0)  # Random port
            )

            await transfer.send_file(packet.filename, packet.options)

        except Exception as e:
            logger.error(f"Transfer setup error: {e}")

        finally:
            if transport:
                transport.close()
            self.transfers.pop(client_addr, None)


class TFTPServer:
    """Async TFTP server with Pi discovery support."""

    def __init__(
        self,
        root: Path,
        host: str = "0.0.0.0",
        port: int = 69,
        on_request: Callable = None,
        pi_discovery_enabled: bool = False,
        pi_discovery_dir: Optional[Path] = None,
        pi_nodes_dir: Optional[Path] = None,
        on_pi_discovery: Optional[Callable[[str, str], None]] = None,
    ):
        """Initialize TFTP server.

        Args:
            root: TFTP root directory.
            host: Host to bind to.
            port: Port to bind to (default 69).
            on_request: Callback for TFTP requests.
            pi_discovery_enabled: Enable Pi auto-discovery fallback.
            pi_discovery_dir: Directory containing Pi discovery boot files.
            pi_nodes_dir: Directory containing per-Pi node directories.
            on_pi_discovery: Callback when a Pi discovery request is detected.
        """
        self.root = Path(root)
        self.host = host
        self._port = port
        self.on_request = on_request
        self.pi_discovery_enabled = pi_discovery_enabled
        self.pi_discovery_dir = pi_discovery_dir
        self.pi_nodes_dir = pi_nodes_dir
        self.on_pi_discovery = on_pi_discovery
        self.transport = None
        self.protocol = None

    @property
    def port(self) -> int:
        """Get actual bound port."""
        if self.transport:
            return self.transport.get_extra_info("sockname")[1]
        return self._port

    async def start(self):
        """Start the TFTP server."""
        handler = TFTPHandler(
            root=self.root,
            pi_discovery_enabled=self.pi_discovery_enabled,
            pi_discovery_dir=self.pi_discovery_dir,
            pi_nodes_dir=self.pi_nodes_dir,
            on_pi_discovery=self.on_pi_discovery,
        )
        loop = asyncio.get_event_loop()

        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: TFTPServerProtocol(handler, self.on_request),
            local_addr=(self.host, self._port)
        )

        actual_port = self.transport.get_extra_info("sockname")[1]
        logger.info(f"TFTP server started on {self.host}:{actual_port}")
        if self.pi_discovery_enabled:
            logger.info(f"Pi discovery enabled, fallback dir: {self.pi_discovery_dir}")

    async def stop(self):
        """Stop the TFTP server."""
        if self.transport:
            self.transport.close()
            self.transport = None
            logger.info("TFTP server stopped")
