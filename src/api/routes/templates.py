"""Template management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import Template, StorageBackend

router = APIRouter()


# --- Pydantic Schemas ---

class TemplateCreate(BaseModel):
    """Request body for creating a template."""
    name: str
    type: str  # iso, kickstart, preseed, autounattend, cloud-init, script
    os_family: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    architecture: str = "x86_64"
    file_path: str | None = None
    storage_backend_id: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    description: str | None = None


class TemplateUpdate(BaseModel):
    """Request body for updating a template."""
    name: str | None = None
    type: str | None = None
    os_family: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    file_path: str | None = None
    storage_backend_id: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    description: str | None = None


class TemplateResponse(BaseModel):
    """Template response."""
    id: str
    name: str
    type: str
    os_family: str | None
    os_name: str | None
    os_version: str | None
    architecture: str
    file_path: str | None
    storage_backend_id: str | None
    storage_backend_name: str | None = None
    size_bytes: int | None
    checksum: str | None
    description: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_template(cls, template: Template) -> "TemplateResponse":
        return cls(
            id=template.id,
            name=template.name,
            type=template.type,
            os_family=template.os_family,
            os_name=template.os_name,
            os_version=template.os_version,
            architecture=template.architecture,
            file_path=template.file_path,
            storage_backend_id=template.storage_backend_id,
            storage_backend_name=template.storage_backend.name if template.storage_backend else None,
            size_bytes=template.size_bytes,
            checksum=template.checksum,
            description=template.description,
            created_at=template.created_at.isoformat() if template.created_at else "",
            updated_at=template.updated_at.isoformat() if template.updated_at else "",
        )


class TemplateListResponse(BaseModel):
    """Response for list of templates."""
    data: list[TemplateResponse]
    total: int


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: TemplateResponse | None = None


# --- Endpoints ---

VALID_TYPES = {"iso", "kickstart", "preseed", "autounattend", "cloud-init", "script"}
VALID_OS_FAMILIES = {"linux", "windows", "bsd"}
VALID_ARCHITECTURES = {"x86_64", "aarch64", "armv7l"}


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    type: str | None = Query(None, description="Filter by template type"),
    os_family: str | None = Query(None, description="Filter by OS family"),
    os_name: str | None = Query(None, description="Filter by OS name"),
    architecture: str | None = Query(None, description="Filter by architecture"),
    db: AsyncSession = Depends(get_db),
):
    """List all templates with optional filtering."""
    query = select(Template).options(selectinload(Template.storage_backend))

    if type:
        query = query.where(Template.type == type)
    if os_family:
        query = query.where(Template.os_family == os_family)
    if os_name:
        query = query.where(Template.os_name == os_name)
    if architecture:
        query = query.where(Template.architecture == architecture)

    query = query.order_by(Template.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return TemplateListResponse(
        data=[TemplateResponse.from_template(t) for t in templates],
        total=len(templates),
    )


@router.get("/templates/{template_id}", response_model=ApiResponse)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get template details by ID."""
    result = await db.execute(
        select(Template)
        .options(selectinload(Template.storage_backend))
        .where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return ApiResponse(data=TemplateResponse.from_template(template))


@router.post("/templates", response_model=ApiResponse, status_code=201)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new template."""
    # Validate type
    if data.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template type. Must be one of: {', '.join(VALID_TYPES)}",
        )

    # Validate os_family if provided
    if data.os_family and data.os_family not in VALID_OS_FAMILIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OS family. Must be one of: {', '.join(VALID_OS_FAMILIES)}",
        )

    # Validate architecture
    if data.architecture not in VALID_ARCHITECTURES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid architecture. Must be one of: {', '.join(VALID_ARCHITECTURES)}",
        )

    # Check for duplicate name
    existing = await db.execute(
        select(Template).where(Template.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Template with this name already exists")

    # Validate storage backend if provided
    if data.storage_backend_id:
        backend = await db.execute(
            select(StorageBackend).where(StorageBackend.id == data.storage_backend_id)
        )
        if not backend.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Storage backend not found")

    template = Template(
        name=data.name,
        type=data.type,
        os_family=data.os_family,
        os_name=data.os_name,
        os_version=data.os_version,
        architecture=data.architecture,
        file_path=data.file_path,
        storage_backend_id=data.storage_backend_id,
        size_bytes=data.size_bytes,
        checksum=data.checksum,
        description=data.description,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template, ["storage_backend"])

    return ApiResponse(
        data=TemplateResponse.from_template(template),
        message="Template created successfully",
    )


@router.patch("/templates/{template_id}", response_model=ApiResponse)
async def update_template(
    template_id: str,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update template metadata."""
    result = await db.execute(
        select(Template)
        .options(selectinload(Template.storage_backend))
        .where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate type if provided
    if data.type and data.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template type. Must be one of: {', '.join(VALID_TYPES)}",
        )

    # Validate os_family if provided
    if data.os_family and data.os_family not in VALID_OS_FAMILIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OS family. Must be one of: {', '.join(VALID_OS_FAMILIES)}",
        )

    # Validate architecture if provided
    if data.architecture and data.architecture not in VALID_ARCHITECTURES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid architecture. Must be one of: {', '.join(VALID_ARCHITECTURES)}",
        )

    # Check for duplicate name if changing
    if data.name and data.name != template.name:
        existing = await db.execute(
            select(Template).where(Template.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Template with this name already exists")

    # Validate storage backend if changing
    if data.storage_backend_id and data.storage_backend_id != template.storage_backend_id:
        backend = await db.execute(
            select(StorageBackend).where(StorageBackend.id == data.storage_backend_id)
        )
        if not backend.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Storage backend not found")

    # Apply updates
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.flush()
    await db.refresh(template, ["storage_backend"])

    return ApiResponse(
        data=TemplateResponse.from_template(template),
        message="Template updated successfully",
    )


@router.delete("/templates/{template_id}", response_model=ApiResponse)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a template."""
    result = await db.execute(
        select(Template)
        .options(selectinload(Template.storage_backend))
        .where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    response = TemplateResponse.from_template(template)
    await db.delete(template)
    await db.flush()

    return ApiResponse(
        data=response,
        message="Template deleted successfully",
    )
