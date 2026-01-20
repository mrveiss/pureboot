"""PureBoot main application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import boot, ipxe, nodes, groups, storage, files, luns
from src.db.database import init_db, close_db
from src.config import settings
from src.pxe.tftp_server import TFTPServer
from src.pxe.dhcp_proxy import DHCPProxy

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global server instances
tftp_server: TFTPServer | None = None
dhcp_proxy: DHCPProxy | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global tftp_server, dhcp_proxy

    logger.info("Starting PureBoot...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Ensure TFTP root exists
    tftp_root = Path(settings.tftp.root)
    tftp_root.mkdir(parents=True, exist_ok=True)
    (tftp_root / "bios").mkdir(exist_ok=True)
    (tftp_root / "uefi").mkdir(exist_ok=True)

    # Start TFTP server if enabled
    if settings.tftp.enabled:
        tftp_server = TFTPServer(
            root=tftp_root,
            host=settings.tftp.host,
            port=settings.tftp.port
        )
        try:
            await tftp_server.start()
        except PermissionError:
            logger.warning(
                f"Cannot bind to port {settings.tftp.port} (requires root). "
                "TFTP server disabled."
            )
            tftp_server = None

    # Start Proxy DHCP if enabled
    if settings.dhcp_proxy.enabled:
        tftp_addr = settings.dhcp_proxy.tftp_server or settings.host
        dhcp_proxy = DHCPProxy(
            tftp_server=tftp_addr,
            host=settings.dhcp_proxy.host,
            port=settings.dhcp_proxy.port
        )
        try:
            await dhcp_proxy.start()
        except PermissionError:
            logger.warning(
                f"Cannot bind to port {settings.dhcp_proxy.port}. "
                "Proxy DHCP disabled."
            )
            dhcp_proxy = None

    logger.info(f"PureBoot ready on http://{settings.host}:{settings.port}")

    yield

    # Cleanup
    logger.info("Shutting down PureBoot...")

    if tftp_server:
        await tftp_server.stop()

    if dhcp_proxy:
        await dhcp_proxy.stop()

    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title="PureBoot",
    description="Unified Vendor-Neutral Node Lifecycle Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount API routes
app.include_router(boot.router, prefix="/api/v1", tags=["boot"])
app.include_router(ipxe.router, prefix="/api/v1", tags=["ipxe"])
app.include_router(nodes.router, prefix="/api/v1", tags=["nodes"])
app.include_router(groups.router, prefix="/api/v1", tags=["groups"])
app.include_router(storage.router, prefix="/api/v1", tags=["storage"])
app.include_router(files.router, prefix="/api/v1", tags=["files"])
app.include_router(luns.router, prefix="/api/v1", tags=["luns"])

# Mount static files for assets (if directory exists)
assets_dir = Path("assets")
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "tftp_enabled": tftp_server is not None,
        "dhcp_proxy_enabled": dhcp_proxy is not None,
    }


def main():
    """Run the application."""
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


if __name__ == "__main__":
    main()
