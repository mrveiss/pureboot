"""iPXE builder API endpoints."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.pxe.ipxe_builder import IPXEBuilder
from src.pxe.ipxe_scripts import IPXEScriptGenerator

router = APIRouter()

builder = IPXEBuilder()


class BuildRequest(BaseModel):
    """iPXE build request."""
    server_address: str
    architecture: Literal["bios", "uefi"] = "bios"
    timeout: int = 5


@router.post("/ipxe/build")
async def build_ipxe(request: BuildRequest):
    """
    Build a custom iPXE binary with embedded boot script.

    The generated binary will automatically connect to the specified
    PureBoot server on boot.
    """
    try:
        binary = await builder.build(
            architecture=request.architecture,
            server_address=request.server_address,
            timeout=request.timeout
        )

        ext = "kpxe" if request.architecture == "bios" else "efi"
        filename = f"pureboot-{request.architecture}.{ext}"

        return StreamingResponse(
            iter([binary]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ipxe/boot.ipxe", response_class=StreamingResponse)
async def get_boot_script(server: str | None = None):
    """
    Get the main iPXE boot script.

    This is the script that embedded iPXE binaries chain to.
    """
    from src.config import settings

    server_address = server or f"{settings.host}:{settings.port}"

    generator = IPXEScriptGenerator(
        server_address=server_address,
        timeout=settings.boot_menu.timeout,
        logo_url=settings.boot_menu.logo_url
    )

    script = generator.generate_boot_script()

    return StreamingResponse(
        iter([script.encode()]),
        media_type="text/plain"
    )
