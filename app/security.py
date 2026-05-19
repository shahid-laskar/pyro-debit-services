from fastapi import Header, HTTPException, status

from app.config import settings


async def require_admin_api_key(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    """Require the configured admin API key for operational endpoints."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured",
        )

    if x_admin_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )


# async def require_callback_secret(
#     x_callback_secret: str | None = Header(default=None, alias="X-Callback-Secret"),
# ) -> None:
#     """Optionally require a shared secret for Pyro callbacks."""
#     if settings.callback_secret and x_callback_secret != settings.callback_secret:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Invalid callback secret",
#         )
