# Issue 007: File Delete Endpoint Path Mismatch

**Priority:** MEDIUM
**Type:** Bug - API Mismatch
**Component:** API - Storage Files
**Status:** Open

---

## Summary

The frontend expects a `POST` endpoint for deleting files, but the backend provides a `DELETE` endpoint. This causes a 404/405 error when users try to delete files from the storage browser.

## Current Behavior

**Frontend calls:** `POST /api/v1/storage/backends/{id}/files/delete`
**Backend provides:** `DELETE /api/v1/storage/backends/{id}/files`

**Frontend location:** `frontend/src/api/storage.ts:57-62`
```typescript
async delete(backendId: string, paths: string[]): Promise<ApiResponse<{ deleted: number }>> {
  return apiClient.post<ApiResponse<{ deleted: number }>>(
    `/storage/backends/${backendId}/files/delete`,
    { paths }
  )
}
```

**Backend location:** `src/api/routes/files.py:144`
```python
@router.delete("/storage/backends/{backend_id}/files", response_model=ApiResponse[dict])
async def delete_files(
    backend_id: str,
    body: FileDelete,
    db: AsyncSession = Depends(get_db),
):
```

## Expected Behavior

Either:
1. **Option A (Recommended):** Add `POST /files/delete` endpoint to backend
2. **Option B:** Change frontend to use `DELETE` with request body

Option A is recommended because:
- POST with body is more compatible across HTTP clients
- Bulk deletions fit POST semantics better
- Some proxies/load balancers strip DELETE request bodies

## Implementation

**Option A - Add POST endpoint in `src/api/routes/files.py`:**

```python
@router.post("/storage/backends/{backend_id}/files/delete", response_model=ApiResponse[dict])
async def delete_files_post(
    backend_id: str,
    body: FileDelete,
    db: AsyncSession = Depends(get_db),
):
    """Delete files from storage backend (POST variant for bulk operations)."""
    return await delete_files(backend_id, body, db)
```

**Option B - Update frontend `frontend/src/api/storage.ts`:**

```typescript
async delete(backendId: string, paths: string[]): Promise<ApiResponse<{ deleted: number }>> {
  return apiClient.delete<ApiResponse<{ deleted: number }>>(
    `/storage/backends/${backendId}/files`,
    { paths }
  )
}
```

Note: Option B requires the API client to support DELETE with body.

## Acceptance Criteria

- [ ] File deletion works from frontend storage browser
- [ ] Multiple files can be deleted in one request
- [ ] Proper error messages for failed deletions

## Related Files

- `frontend/src/api/storage.ts`
- `src/api/routes/files.py`
