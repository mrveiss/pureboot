"""PureBoot main application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.routes import boot, ipxe, nodes, groups, storage, files, luns, system
from src.api.routes.sync_jobs import router as sync_jobs_router
from src.api.routes.workflows import router as workflows_router
from src.api.routes.templates import router as templates_router
from src.db.database import init_db, close_db, async_session_factory
from src.config import settings
from src.pxe.tftp_server import TFTPServer
from src.pxe.dhcp_proxy import DHCPProxy
from src.core.scheduler import sync_scheduler

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
        http_addr = (
            settings.dhcp_proxy.http_server
            or f"{settings.host}:{settings.port}"
        )
        dhcp_proxy = DHCPProxy(
            tftp_server=tftp_addr,
            http_server=http_addr,
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

    # Start scheduler and re-register scheduled jobs
    sync_scheduler.start()
    await _register_scheduled_jobs()
    logger.info("Scheduler started")

    logger.info(f"PureBoot ready on http://{settings.host}:{settings.port}")

    yield

    # Cleanup
    logger.info("Shutting down PureBoot...")

    # Stop scheduler
    sync_scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")

    if tftp_server:
        await tftp_server.stop()

    if dhcp_proxy:
        await dhcp_proxy.stop()

    await close_db()
    logger.info("Database connections closed")


async def _register_scheduled_jobs():
    """Re-register all non-manual sync jobs on startup."""
    from src.db.models import SyncJob
    from sqlalchemy import select

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        result = await db.execute(
            select(SyncJob).where(SyncJob.schedule != "manual")
        )
        jobs = result.scalars().all()

        for job in jobs:
            next_run = sync_scheduler.schedule_job(
                job.id,
                job.schedule,
                job.schedule_day,
                job.schedule_time,
            )
            if next_run:
                job.next_run_at = next_run

        await db.commit()
        logger.info(f"Re-registered {len(jobs)} scheduled sync jobs")


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
app.include_router(system.router, prefix="/api/v1", tags=["system"])
app.include_router(sync_jobs_router, prefix="/api/v1", tags=["sync-jobs"])
app.include_router(workflows_router, prefix="/api/v1", tags=["workflows"])
app.include_router(templates_router, prefix="/api/v1", tags=["templates"])

# Static assets directory
assets_dir = Path("assets")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "tftp_enabled": tftp_server is not None,
        "dhcp_proxy_enabled": dhcp_proxy is not None,
    }


# Serve React SPA - must be after API routes
# Mount static assets subdirectory if it exists (contains JS, CSS from Vite build)
assets_subdir = assets_dir / "assets"
if assets_subdir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_subdir)), name="static-assets")


@app.get("/")
async def serve_spa_root():
    """Serve the React SPA index.html at root."""
    index_file = assets_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}


@app.get("/{full_path:path}")
async def serve_spa_catchall(request: Request, full_path: str):
    """Serve static files or fallback to index.html for SPA routing."""
    # Skip API paths (should be handled by routers above)
    if full_path.startswith("api/"):
        return {"error": "Not found"}

    # Try to serve the exact file first
    # Resolve the path and verify it stays within assets_dir to prevent path traversal
    file_path = (assets_dir / full_path).resolve()
    if file_path.is_relative_to(assets_dir.resolve()) and file_path.exists() and file_path.is_file():
        return FileResponse(file_path)

    # Fallback to index.html for SPA client-side routing
    index_file = assets_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}


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
