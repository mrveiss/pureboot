"""TFTP server implementation (RFC 1350, 2347, 2348)."""
import asyncio
import logging
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import AsyncIterator

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
    """Handles TFTP file operations."""

    def __init__(self, root: Path):
        """Initialize handler with TFTP root directory."""
        self.root = Path(root).resolve()

    def _resolve_path(self, filename: str) -> Path:
        """Resolve filename to safe path within root."""
        # Normalize and resolve
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
