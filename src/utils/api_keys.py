"""API key generation and verification utilities."""
import secrets

import bcrypt


def generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        tuple of (full_key, key_prefix, key_hash)
        - full_key: The complete key to show user once (pb_live_XXXXXXXX_SECRET)
        - key_prefix: First part for identification (pb_live_XXXXXXXX)
        - key_hash: bcrypt hash of the secret portion for storage
    """
    # Generate 8-char ID and 48-char secret
    key_id = secrets.token_hex(4)  # 8 hex chars
    secret = secrets.token_hex(24)  # 48 hex chars

    # Format: pb_{env}_{id}_{secret}
    prefix = f"pb_{environment}_{key_id}"
    full_key = f"{prefix}_{secret}"

    # Hash only the secret portion
    key_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

    return full_key, prefix, key_hash


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    """
    Verify an API key against its stored hash.

    Args:
        full_key: The complete API key (pb_live_XXXXXXXX_SECRET)
        stored_hash: The bcrypt hash of the secret

    Returns:
        True if valid, False otherwise
    """
    try:
        parts = full_key.split("_")
        if len(parts) != 4:
            return False

        secret = parts[3]
        return bcrypt.checkpw(secret.encode(), stored_hash.encode())
    except Exception:
        return False


def parse_api_key(full_key: str) -> tuple[str, str] | None:
    """
    Parse an API key to extract prefix and secret.

    Args:
        full_key: The complete API key

    Returns:
        tuple of (prefix, secret) or None if invalid format
    """
    try:
        parts = full_key.split("_")
        if len(parts) != 4:
            return None

        prefix = f"{parts[0]}_{parts[1]}_{parts[2]}"
        secret = parts[3]
        return prefix, secret
    except Exception:
        return None
