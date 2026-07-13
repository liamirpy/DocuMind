from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.api.settings import ApiSettings


def require_api_key(settings: ApiSettings):
    async def dependency(x_api_key: str | None = Header(default=None)) -> None:
        if settings.api_key is None:
            return
        if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key header",
            )

    return dependency
