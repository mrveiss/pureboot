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


class NFSSettings(BaseSettings):
    """NFS root filesystem settings for diskless Pi boot."""
    enabled: bool = False
    root_path: Path = Path("/srv/nfsroot")
    base_dir: str = "base"
    nodes_dir: str = "nodes"
    default_base_image: str = "ubuntu-arm64"


class AgentSettings(BaseSettings):
    """Site agent configuration.

    When mode='agent', PureBoot runs as a site agent instead of central controller.
    The agent serves boot files locally and reports to the central controller.
    """
    # Operating mode: 'controller' (default) or 'agent'
    mode: str = "controller"

    # Site ID this agent belongs to (required when mode=agent)
    site_id: str | None = None

    # Central controller URL (required when mode=agent)
    central_url: str | None = None

    # Registration token (used for initial registration)
    registration_token: str | None = None

    # Heartbeat interval in seconds
    heartbeat_interval: int = 60

    # Local data directory for agent
    data_dir: Path = Path("/var/lib/pureboot-agent")

    # Cache settings
    cache_dir: Path = Path("/var/lib/pureboot-agent/cache")
    cache_max_size_gb: int = 50

    # Cache policy: minimal, assigned, mirror, pattern
    # - minimal: Bootloaders only
    # - assigned: Bootloaders + content assigned to this site
    # - mirror: Full sync of all content from central
    # - pattern: Cache items matching glob patterns
    cache_policy: str = "assigned"

    # Glob patterns for pattern policy (e.g., "templates/kickstart/*")
    cache_patterns: list[str] = []

    # Cache retention in days (0 = never expire)
    cache_retention_days: int = 30

    # Node state cache TTL in seconds
    node_cache_ttl: int = 300  # 5 minutes

    # Sync schedule (cron format, e.g., "0 2 * * *" for 2 AM daily)
    sync_schedule: str = "0 2 * * *"

    # Retry settings for central communication
    retry_max_attempts: int = 3
    retry_backoff_seconds: int = 5

    # Whether agent has completed initial registration
    registered: bool = False

    # Phase 4: Offline operation settings
    # Connectivity monitoring
    connectivity_check_interval: int = 30  # Seconds between connectivity checks
    connectivity_timeout: float = 5.0  # Timeout for health check
    connectivity_failure_threshold: int = 3  # Failures before marking offline

    # Offline boot behavior
    offline_default_action: str = "local"  # local, discovery, last_known

    # Queue settings for offline operations
    queue_batch_size: int = 10  # Items to process per batch
    queue_retry_delay: float = 5.0  # Seconds between retries
    queue_max_retries: int = 3  # Max retry attempts


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
    nfs: NFSSettings = Field(default_factory=NFSSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)

    # Installation timeout in minutes (0 = disabled)
    install_timeout_minutes: int = 60

    @property
    def is_agent_mode(self) -> bool:
        """Check if running in agent mode."""
        return self.agent.mode == "agent"

    @property
    def is_controller_mode(self) -> bool:
        """Check if running in controller mode."""
        return self.agent.mode == "controller"


settings = Settings()
