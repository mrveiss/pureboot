"""PureBoot main application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import boot
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting PureBoot...")

    # TODO: Start TFTP server if enabled
    # TODO: Start Proxy DHCP if enabled

    yield

    logger.info("Shutting down PureBoot...")


app = FastAPI(
    title="PureBoot",
    description="Unified Vendor-Neutral Node Lifecycle Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount API routes
app.include_router(boot.router, prefix="/api/v1", tags=["boot"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
