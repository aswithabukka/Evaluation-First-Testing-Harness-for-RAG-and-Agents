"""
API key authentication for production endpoints.

When API_KEYS is set (comma-separated list), every request to protected
endpoints must include a valid key via the X-API-Key header.
When API_KEYS is empty, authentication is disabled (local development).
"""
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_valid_keys() -> set[str]:
    """Parse the comma-separated API_KEYS setting."""
    if not settings.API_KEYS:
        return set()
    return {k.strip() for k in settings.API_KEYS.split(",") if k.strip()}


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """
    FastAPI dependency that enforces API key authentication.

    - If API_KEYS is empty: auth is disabled → returns None
    - If API_KEYS is set: the request must include a valid X-API-Key header
    """
    valid_keys = _get_valid_keys()
    if not valid_keys:
        return None  # Auth disabled

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
