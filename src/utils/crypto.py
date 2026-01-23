"""Cryptographic utilities for encrypting sensitive values."""
import base64
import hashlib

from cryptography.fernet import Fernet

from src.config import settings


def get_fernet() -> Fernet:
    """Get Fernet instance with encryption key derived from secret_key."""
    # Derive a 32-byte key from the secret_key using SHA256
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    key_b64 = base64.urlsafe_b64encode(key)
    return Fernet(key_b64)


def encrypt_value(value: str) -> str:
    """Encrypt a string value.

    Args:
        value: The plaintext string to encrypt.

    Returns:
        The encrypted value as a base64-encoded string.
    """
    f = get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt an encrypted value.

    Args:
        encrypted: The encrypted string (base64-encoded).

    Returns:
        The decrypted plaintext string.
    """
    f = get_fernet()
    return f.decrypt(encrypted.encode()).decode()
