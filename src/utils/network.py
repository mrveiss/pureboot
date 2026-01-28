"""Network utility functions."""
import socket


def get_primary_ip() -> str:
    """Get the primary IP address of this machine.

    Uses a UDP socket trick to determine which IP would be used
    to reach an external address (doesn't actually send data).

    Returns:
        Primary IP address as string, or "127.0.0.1" if detection fails.
    """
    try:
        # Create a UDP socket and "connect" to an external address
        # This doesn't actually send data, just determines routing
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        # Fallback to localhost if detection fails
        return "127.0.0.1"


def resolve_server_address(host: str, port: int) -> str:
    """Resolve server address for client communication.

    If host is 0.0.0.0 (bind-all), auto-detect the actual IP.

    Args:
        host: Configured host (may be 0.0.0.0)
        port: Server port

    Returns:
        Server address in "ip:port" format suitable for clients.
    """
    if host == "0.0.0.0":
        actual_ip = get_primary_ip()
        return f"{actual_ip}:{port}"
    return f"{host}:{port}"


def get_server_url() -> str:
    """Get the server URL for client communication.

    Auto-detects the IP if host is 0.0.0.0.

    Returns:
        Server URL in "http://ip:port" format.
    """
    from src.config import settings

    address = resolve_server_address(settings.host, settings.port)
    return f"http://{address}"
