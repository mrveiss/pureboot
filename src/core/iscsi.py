"""iSCSI LUN service layer using targetcli."""
import asyncio
import logging
import os
import re
import secrets
import string
from base64 import urlsafe_b64encode
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Constants
TARGETCLI_TIMEOUT_SECONDS = 60
SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$")

# Encryption key derivation
_SECRET_KEY = os.environ.get("PUREBOOT_SECRET_KEY", "")
_SALT = b"pureboot-iscsi-salt"


def _check_secret_key() -> None:
    """Check that a valid secret key is configured."""
    if not _SECRET_KEY or _SECRET_KEY == "pureboot-dev-secret-key-change-in-prod":
        logger.warning(
            "PUREBOOT_SECRET_KEY not set or using default value. "
            "CHAP passwords will not be securely encrypted. "
            "Set PUREBOOT_SECRET_KEY environment variable in production."
        )


def _get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption."""
    key_material = _SECRET_KEY or "pureboot-dev-secret-key-change-in-prod"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480000,
    )
    key = urlsafe_b64encode(kdf.derive(key_material.encode()))
    return Fernet(key)


def _validate_safe_name(name: str) -> bool:
    """Validate that a name is safe for use in shell commands."""
    if not name or len(name) > 100:
        return False
    return bool(SAFE_NAME_PATTERN.match(name))


def encrypt_password(password: str) -> str:
    """Encrypt a CHAP password."""
    _check_secret_key()
    f = _get_fernet()
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a CHAP password."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def generate_chap_password(length: int = 16) -> str:
    """Generate a random CHAP password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_iqn(name: str) -> str:
    """Generate an IQN for a LUN."""
    return f"iqn.2026-01.local.pureboot:{name}"


def generate_initiator_iqn(mac_address: str) -> str:
    """Generate an initiator IQN for a node."""
    # Remove colons and lowercase
    mac_clean = mac_address.replace(":", "").lower()
    return f"iqn.2026-01.local.pureboot:node:{mac_clean}"


class IscsiLunService:
    """Service for managing iSCSI LUNs via targetcli."""

    def __init__(self, backend_config: dict[str, Any]):
        self.config = backend_config
        self.target_name = backend_config.get(
            "target_name", "iqn.2026-01.local.pureboot:target1"
        )
        self.portal_ip = backend_config.get("portal_ip", "0.0.0.0")
        self.portal_port = backend_config.get("portal_port", 3260)
        self.backingstore_type = backend_config.get("backingstore_type", "file")
        self.backingstore_path = backend_config.get(
            "backingstore_path", "/var/lib/pureboot/luns"
        )

    async def _run_targetcli(
        self, *args: str, mask_args: bool = False
    ) -> tuple[bool, str]:
        """Run a targetcli command.

        Args:
            *args: Command arguments for targetcli
            mask_args: If True, mask arguments in log output (for sensitive commands)
        """
        cmd = ["sudo", "targetcli"] + list(args)

        # Log command, masking sensitive data if requested
        if mask_args:
            logger.info("Running: sudo targetcli [command with sensitive data]")
        else:
            logger.info(f"Running: {' '.join(cmd)}")

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TARGETCLI_TIMEOUT_SECONDS
            )

            if proc.returncode != 0:
                error = stderr.decode().strip() or stdout.decode().strip()
                logger.error(f"targetcli failed: {error}")
                return False, error

            return True, stdout.decode().strip()
        except asyncio.TimeoutError:
            logger.error("targetcli command timed out")
            if proc:
                proc.kill()
                await proc.wait()
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"targetcli error: {e}")
            return False, str(e)

    async def create_backingstore(self, name: str, size_gb: int) -> tuple[bool, str]:
        """Create a backingstore for a LUN."""
        if not _validate_safe_name(name):
            return False, f"Invalid name: {name}"

        if self.backingstore_type == "file":
            # Ensure directory exists
            await asyncio.to_thread(
                os.makedirs, self.backingstore_path, exist_ok=True
            )
            file_path = f"{self.backingstore_path}/{name}.img"
            return await self._run_targetcli(
                f"/backstores/fileio create {name} {file_path} {size_gb}G sparse=true"
            )
        elif self.backingstore_type == "block":
            # Assume LVM - backingstore_path is the VG name
            vg_name = self.backingstore_path
            # First create the LV
            try:
                create_lv = await asyncio.create_subprocess_exec(
                    "sudo", "lvcreate", "-L", f"{size_gb}G", "-n", name, vg_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    create_lv.communicate(), timeout=TARGETCLI_TIMEOUT_SECONDS
                )
                if create_lv.returncode != 0:
                    return False, stderr.decode().strip()
            except asyncio.TimeoutError:
                return False, "LV creation timed out"

            # Then create the block backingstore
            return await self._run_targetcli(
                f"/backstores/block create {name} /dev/{vg_name}/{name}"
            )
        else:
            return False, f"Unknown backingstore type: {self.backingstore_type}"

    async def delete_backingstore(self, name: str) -> tuple[bool, str]:
        """Delete a backingstore."""
        if not _validate_safe_name(name):
            return False, f"Invalid name: {name}"

        if self.backingstore_type == "file":
            success, msg = await self._run_targetcli(
                f"/backstores/fileio delete {name}"
            )
            if success:
                # Also remove the file
                file_path = f"{self.backingstore_path}/{name}.img"
                try:
                    await asyncio.to_thread(os.remove, file_path)
                except OSError:
                    pass
            return success, msg
        elif self.backingstore_type == "block":
            success, msg = await self._run_targetcli(
                f"/backstores/block delete {name}"
            )
            if success:
                # Also remove the LV
                vg_name = self.backingstore_path
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "sudo", "lvremove", "-f", f"/dev/{vg_name}/{name}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(
                        proc.communicate(), timeout=TARGETCLI_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"LV removal timed out for {name}")
            return success, msg
        else:
            return False, f"Unknown backingstore type: {self.backingstore_type}"

    async def create_lun(self, name: str, lun_number: int = 0) -> tuple[bool, str]:
        """Create a LUN under the target."""
        if not _validate_safe_name(name):
            return False, f"Invalid name: {name}"

        backingstore = "fileio" if self.backingstore_type == "file" else "block"
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/luns create "
            f"/backstores/{backingstore}/{name} lun={lun_number}"
        )

    async def delete_lun(self, lun_number: int) -> tuple[bool, str]:
        """Delete a LUN from the target."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/luns delete lun{lun_number}"
        )

    async def create_acl(self, initiator_iqn: str) -> tuple[bool, str]:
        """Create an ACL for an initiator."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls create {initiator_iqn}"
        )

    async def delete_acl(self, initiator_iqn: str) -> tuple[bool, str]:
        """Delete an ACL for an initiator."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls delete {initiator_iqn}"
        )

    async def set_chap(
        self, initiator_iqn: str, username: str, password: str
    ) -> tuple[bool, str]:
        """Set CHAP credentials for an initiator."""
        # Use mask_args=True to avoid logging the password
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls/{initiator_iqn} "
            f"set auth userid={username} password={password}",
            mask_args=True,
        )

    async def save_config(self) -> tuple[bool, str]:
        """Save targetcli configuration."""
        return await self._run_targetcli("saveconfig")

    async def ensure_target_exists(self) -> tuple[bool, str]:
        """Ensure the iSCSI target exists, create if not."""
        # Check if target exists
        success, output = await self._run_targetcli("/iscsi ls")
        if self.target_name in output:
            return True, "Target exists"

        # Create target
        success, msg = await self._run_targetcli(
            f"/iscsi create {self.target_name}"
        )
        if not success:
            return False, msg

        # Set portal
        await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/portals create "
            f"{self.portal_ip} {self.portal_port}"
        )

        # Enable target
        await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1 set attribute authentication=0"
        )
        await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1 set attribute generate_node_acls=0"
        )

        return await self.save_config()
