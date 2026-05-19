from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db

bearer = HTTPBearer()


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
) -> str:
    if credentials.credentials != settings.app_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


async def get_session(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[AsyncSession, None]:
    yield db
