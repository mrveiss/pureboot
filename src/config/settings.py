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
    """Proxy DHCP settings."""
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 4011
    tftp_server: str | None = None  # Auto-detect if None


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


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_prefix="PUREBOOT_",
        env_nested_delimiter="__",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    tftp: TFTPSettings = Field(default_factory=TFTPSettings)
    dhcp_proxy: DHCPProxySettings = Field(default_factory=DHCPProxySettings)
    boot_menu: BootMenuSettings = Field(default_factory=BootMenuSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    registration: RegistrationSettings = Field(default_factory=RegistrationSettings)


settings = Settings()
