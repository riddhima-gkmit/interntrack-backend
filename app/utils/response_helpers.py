"""Unified success response helpers (success: true, data, meta/message) for consistent API responses."""

def success_list_response(
    data: list,
    skip: int,
    limit: int,
    total: int,
) -> dict:
    """Return unified list format: success, data, meta (page, page_size, total) for paginated endpoints."""
    # 1-based page from skip/limit; avoid div-by-zero when limit is 0.
    page = (skip // limit) + 1 if limit else 1
    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": limit,
            "total": total,
        },
    }

def success_response(
    data: dict | list | None = None, message: str | None = None
) -> dict:
    """Return unified single/success format: success, data, optional message (for non-list or simple success)."""
    # Default data to {} so clients always get an object; omit message key when not provided.
    out: dict = {"success": True, "data": data if data is not None else {}}
    if message is not None:
        out["message"] = message
    return out
