# File Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement unified file management with storage backend integration, checksums, and bandwidth throttling.

**Architecture:** Files served from single "default boot backend" via HTTP/TFTP. Checksums computed on upload, served with downloads. Bandwidth fairly shared with priority for small files and near-completion transfers.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio, Pydantic

---

## Task 1: Add FileChecksum Model

**Files:**
- Modify: `src/db/models.py`
- Modify: `tests/unit/test_models.py`

Add `FileChecksum` model after `StorageBackend`:

```python
class FileChecksum(Base):
    __tablename__ = "file_checksums"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    backend_id: Mapped[str] = mapped_column(ForeignKey("storage_backends.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    computed_at: Mapped[datetime] = mapped_column(default=func.now())

    backend: Mapped["StorageBackend"] = relationship()

    __table_args__ = (
        UniqueConstraint("backend_id", "file_path", name="uq_backend_file_path"),
    )
```

**Commit:** `feat: add FileChecksum model for file integrity tracking`

---

## Task 2: Add SystemSetting Model and Service

**Files:**
- Modify: `src/db/models.py`
- Create: `src/core/system_settings.py`
- Create: `tests/unit/test_system_settings.py`

Add `SystemSetting` model:

```python
class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

Create service `src/core/system_settings.py` with:
- `get_setting(db, key)` / `set_setting(db, key, value)`
- `get_default_boot_backend_id(db)`
- `get_file_serving_bandwidth_mbps(db)` (default 1000)

**Commit:** `feat: add SystemSetting model and settings service`

---

## Task 3: Add System Settings API

**Files:**
- Modify: `src/api/routes/system.py`
- Create: `tests/integration/test_system_settings_api.py`

Add endpoints:
- `GET /api/v1/system/settings` - Returns `default_boot_backend_id`, `file_serving_bandwidth_mbps`
- `PATCH /api/v1/system/settings` - Updates settings, validates backend exists

**Commit:** `feat: add system settings API endpoints`

---

## Task 4: Create Boot Files Endpoint

**Files:**
- Create: `src/api/routes/boot_files.py`
- Modify: `src/api/routes/__init__.py`
- Create: `tests/integration/test_boot_files_api.py`

Create `GET /api/v1/files/{path:path}`:
1. Look up `default_boot_backend_id`
2. Fetch file from backend
3. Look up checksum from `file_checksums` table
4. Return `StreamingResponse` with headers:
   - `ETag: "sha256:<checksum>"`
   - `X-Checksum-SHA256: <checksum>`

Return 503 if no default backend configured, 404 if file not found.

**Commit:** `feat: add boot files serving endpoint with checksum headers`

---

## Task 5: Add Checksum Computation on Upload

**Files:**
- Modify: `src/api/routes/files.py`
- Modify: `src/api/schemas.py` (add `checksum_sha256` to `StorageFile`)

Modify `upload_file` endpoint:
1. Read entire file content
2. Compute SHA256
3. If `expected_checksum` provided, verify match (422 on mismatch)
4. Upload to backend
5. Store/update `FileChecksum` record
6. Return checksum in response

**Commit:** `feat: compute and store checksum on file upload`

---

## Task 6: Implement Bandwidth Throttler

**Files:**
- Create: `src/core/bandwidth_throttler.py`
- Create: `tests/unit/test_bandwidth_throttler.py`

Implement `BandwidthThrottler` class:
- Track active transfers with `ActiveTransfer` dataclass
- `calculate_priority(transfer)` - Higher for small files and near-completion
- `register_transfer()` / `unregister_transfer()`
- `get_allowed_bytes(transfer_id, interval)` - Returns bytes allowed based on priority share
- Minimum bandwidth floor (1 Mbps default)

**Commit:** `feat: implement priority-based bandwidth throttler`

---

## Task 7: Integrate Throttler with File Serving

**Files:**
- Modify: `src/api/routes/boot_files.py`

Wrap content iterator with throttling:
1. Register transfer on request
2. Stream chunks respecting `get_allowed_bytes()` limit
3. Update progress after each chunk
4. Unregister on completion/error

**Commit:** `feat: integrate bandwidth throttling with file serving`

---

## Task 8: Update Boot Scripts to Use New URLs

**Files:**
- Modify: `src/api/routes/boot.py`

Change kernel/initrd URLs from:
```python
kernel_url = f"{server}{workflow.kernel_path}"
```
To:
```python
kernel_url = f"{server}/api/v1/files{workflow.kernel_path}"
```

Update both `generate_install_script` and `get_grub_config`.

**Commit:** `feat: update boot scripts to use /api/v1/files endpoint`

---

## Task 9: Add Migration

**Files:**
- Create: `migrations/versions/002_add_file_checksums.sql`

```sql
CREATE TABLE IF NOT EXISTS file_checksums (
    id VARCHAR(36) PRIMARY KEY,
    backend_id VARCHAR(36) NOT NULL REFERENCES storage_backends(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_backend_file_path UNIQUE (backend_id, file_path)
);

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Commit:** `feat: add migration for file checksums and system settings`

---

## Final Checklist

- [ ] All tests pass: `pytest tests/ -v`
- [ ] FileChecksum model working
- [ ] SystemSetting model and service working
- [ ] System settings API working
- [ ] Boot files endpoint serving with checksums
- [ ] Upload computes checksums
- [ ] Bandwidth throttler working
- [ ] Throttling integrated with file serving
- [ ] Boot scripts using new URLs
- [ ] Migration script created