"""Template management API endpoints."""
import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import Template, StorageBackend, TemplateVersion

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


# --- Template Version Schemas ---


class TemplateVersionCreate(BaseModel):
    """Request body for creating a template version."""
    content: str = Field(..., max_length=10_000_000)  # 10MB limit
    commit_message: str | None = None


class TemplateVersionResponse(BaseModel):
    """Template version response."""
    id: str
    template_id: str
    major: int
    minor: int
    version_string: str
    content: str
    content_hash: str
    size_bytes: int | None
    commit_message: str | None
    created_at: str

    @classmethod
    def from_version(cls, version: TemplateVersion) -> "TemplateVersionResponse":
        return cls(
            id=version.id,
            template_id=version.template_id,
            major=version.major,
            minor=version.minor,
            version_string=version.version_string,
            content=version.content,
            content_hash=version.content_hash,
            size_bytes=version.size_bytes,
            commit_message=version.commit_message,
            created_at=version.created_at.isoformat() if version.created_at else "",
        )


class TemplateVersionListResponse(BaseModel):
    """Response for list of template versions."""
    data: list[TemplateVersionResponse]
    total: int


class VersionApiResponse(BaseModel):
    """API response for template version operations."""
    success: bool = True
    message: str | None = None
    data: TemplateVersionResponse | None = None


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


# --- Template Version Endpoints ---


def parse_version_string(version_str: str) -> tuple[int, int] | None:
    """Parse a version string like 'v1.0', 'v1', '1.0' into (major, minor).

    Returns None if the version string cannot be parsed.
    """
    # Handle various formats: v1.0, v1, 1.0, 1
    match = re.match(r'^v?(\d+)(?:\.(\d+))?$', version_str)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    return (major, minor)


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


@router.post(
    "/templates/{template_id}/versions",
    response_model=VersionApiResponse,
    status_code=201,
)
async def create_template_version(
    template_id: str,
    data: TemplateVersionCreate,
    bump: str = Query("minor", description="Version bump type: 'major' or 'minor'"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new version of a template.

    If this is the first version, it will be v1.0.
    Otherwise, it will increment based on the bump parameter:
    - bump=minor: increments minor version (e.g., v1.0 -> v1.1)
    - bump=major: increments major version and resets minor to 0 (e.g., v1.5 -> v2.0)
    """
    # Find the template
    result = await db.execute(
        select(Template)
        .options(selectinload(Template.versions))
        .where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate bump parameter
    if bump not in ("major", "minor"):
        raise HTTPException(status_code=400, detail="Invalid bump type. Must be 'major' or 'minor'")

    # Determine version numbers
    if not template.versions:
        # First version
        major, minor = 1, 0
    else:
        # Find the highest version
        latest_version = max(
            template.versions,
            key=lambda v: (v.major, v.minor)
        )
        if bump == "major":
            major = latest_version.major + 1
            minor = 0
        else:
            major = latest_version.major
            minor = latest_version.minor + 1

    # Create the version
    content_hash = compute_content_hash(data.content)
    version = TemplateVersion(
        template_id=template_id,
        major=major,
        minor=minor,
        content=data.content,
        content_hash=content_hash,
        size_bytes=len(data.content.encode('utf-8')),
        commit_message=data.commit_message,
    )
    db.add(version)
    await db.flush()

    # Update template's current version
    template.current_version_id = version.id
    await db.flush()

    return VersionApiResponse(
        data=TemplateVersionResponse.from_version(version),
        message=f"Template version {version.version_string} created successfully",
    )


@router.get(
    "/templates/{template_id}/versions",
    response_model=TemplateVersionListResponse,
)
async def list_template_versions(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all versions of a template."""
    # Verify template exists
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get all versions
    result = await db.execute(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.major.desc(), TemplateVersion.minor.desc())
    )
    versions = result.scalars().all()

    return TemplateVersionListResponse(
        data=[TemplateVersionResponse.from_version(v) for v in versions],
        total=len(versions),
    )


@router.get(
    "/templates/{template_id}/versions/{version}",
    response_model=VersionApiResponse,
)
async def get_template_version(
    template_id: str,
    version: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version of a template.

    The version can be:
    - 'latest': Returns the template's current version
    - A version string like 'v1.0', 'v1', '1.0', '1'
    """
    # Verify template exists
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if version.lower() == "latest":
        if not template.current_version_id:
            raise HTTPException(
                status_code=404,
                detail="No versions available for this template"
            )
        result = await db.execute(
            select(TemplateVersion)
            .where(TemplateVersion.id == template.current_version_id)
        )
        template_version = result.scalar_one_or_none()
    else:
        # Parse version string
        parsed = parse_version_string(version)
        if parsed is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid version format: {version}"
            )
        major, minor = parsed

        result = await db.execute(
            select(TemplateVersion)
            .where(
                TemplateVersion.template_id == template_id,
                TemplateVersion.major == major,
                TemplateVersion.minor == minor,
            )
        )
        template_version = result.scalar_one_or_none()

    if not template_version:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for this template"
        )

    return VersionApiResponse(
        data=TemplateVersionResponse.from_version(template_version),
    )
