"""FastAPI 依赖：当前登录用户。"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.tenant import Tenant, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    username: str
    tenant_slug: str
    tenant_name: str
    role: str
    display_name: str | None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或令牌缺失",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )

    user_id = uuid.UUID(payload["sub"])
    tenant_id = uuid.UUID(payload["tenant_id"])

    stmt = (
        select(User)
        .where(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True))
        .options(selectinload(User.tenant))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user or not user.tenant:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        tenant_slug=user.tenant.slug,
        tenant_name=user.tenant.name,
        role=user.role,
        display_name=user.display_name,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
