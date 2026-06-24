"""API authentication and authorization.

All endpoints except /health require a valid Bearer token (API key).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials

from config import settings

security = HTTPBearer()


async def verify_api_key(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    """Verify Bearer token matches configured API key.

    Raises:
        HTTPException: 403 if token is missing or invalid.

    Returns:
        The API key (for audit/logging purposes).
    """
    if credentials.credentials != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return credentials.credentials
