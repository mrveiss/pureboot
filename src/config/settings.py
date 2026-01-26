"""Application settings using Pydantic."""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TFTPSettings(BaseSettings):
    """TFTP server settings."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 69
    root: Path = Path("./tftp")


class DHCPProxySettings(BaseSettings):
    """Proxy DHCP settings.

    The proxy DHCP server enables two-stage PXE booting:
    1. Raw firmware → iPXE binary (via TFTP)
    2. iPXE → HTTP boot script (via HTTP)

    This allows stock iPXE binaries to work without embedded scripts.
    """
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 4011
    tftp_server: str | None = None  # Auto-detect from main host if None
    http_server: str | None = None  # Auto-detect from main host:port if None


class BootMenuSettings(BaseSettings):
    """Boot menu settings."""
    timeout: int = 5
    show_menu: bool = True
    logo_url: str = "/assets/pureboot-logo.png"


class DatabaseSettings(BaseSettings):
    """Database settings."""
    url: str = "sqlite+aiosqlite:///./data/pureboot.db"
    echo: bool = False  # Log SQL statements


class RegistrationSettings(BaseSettings):
    """Node registration settings."""
    auto_register: bool = True  # Auto-register unknown MACs
    default_group_id: str | None = None  # Default group for new nodes


class AuditSettings(BaseSettings):
    """Audit logging configuration."""
    file_enabled: bool = False
    file_path: str = "/var/log/pureboot/audit.log"
    siem_enabled: bool = False
    siem_webhook_url: str | None = None


class CASettings(BaseSettings):
    """Certificate Authority settings for clone session TLS."""
    enabled: bool = True
    cert_dir: Path = Path("/opt/pureboot/certs")
    ca_validity_years: int = 10
    session_cert_validity_hours: int = 24
    key_algorithm: str = "ECDSA"  # ECDSA or RSA
    key_size: int = 256  # 256 for ECDSA (P-256), 2048/4096 for RSA


class PiSettings(BaseSettings):
    """Raspberry Pi boot settings."""
    enabled: bool = True
    firmware_dir: Path = Path("./tftp/rpi-firmware")
    deploy_dir: Path = Path("./tftp/deploy-arm64")
    deploy_kernel: str = "kernel8.img"
    deploy_initrd: str = "initramfs.img"
    # Directory for per-node TFTP files (will contain serial number subdirs)
    nodes_dir: Path = Path("./tftp/pi-nodes")


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_prefix="PUREBOOT_",
        env_nested_delimiter="__",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # Secret key for encryption (MUST be set in production)
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_32_CHARS!"

    # Workflow definitions directory
    workflows_dir: Path = Path("/var/lib/pureboot/workflows")

    tftp: TFTPSettings = Field(default_factory=TFTPSettings)
    dhcp_proxy: DHCPProxySettings = Field(default_factory=DHCPProxySettings)
    boot_menu: BootMenuSettings = Field(default_factory=BootMenuSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    registration: RegistrationSettings = Field(default_factory=RegistrationSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    ca: CASettings = Field(default_factory=CASettings)
    pi: PiSettings = Field(default_factory=PiSettings)

    # Installation timeout in minutes (0 = disabled)
    install_timeout_minutes: int = 60


settings = Settings()
