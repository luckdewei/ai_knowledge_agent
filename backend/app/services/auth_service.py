"""账号注册与登录（每人自动拥有独立数据空间，对外仅暴露账号密码）。"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password, verify_password
from app.models.tenant import Tenant, User


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:80] or "user"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _unique_tenant_slug(self, base: str) -> str:
        slug = slugify(base)
        candidate = slug
        n = 0
        while True:
            existing = await self.db.execute(
                select(Tenant.id).where(Tenant.slug == candidate)
            )
            if existing.scalar_one_or_none() is None:
                return candidate
            n += 1
            suffix = f"-{n}" if n < 100 else f"-{uuid.uuid4().hex[:8]}"
            candidate = f"{slug}{suffix}"[:100]

    async def register(self, username: str, password: str) -> dict:
        uname = username.strip().lower()
        if len(uname) < 2 or len(password) < 6:
            raise ValueError("账号至少 2 位，密码至少 6 位")

        existing_user = await self.db.execute(
            select(User.id).where(User.username == uname)
        )
        if existing_user.scalar_one_or_none():
            raise ValueError("该账号已被注册")

        slug = await self._unique_tenant_slug(uname)
        tenant = Tenant(name=uname, slug=slug)
        self.db.add(tenant)
        await self.db.flush()

        user = User(
            tenant_id=tenant.id,
            username=uname,
            password_hash=hash_password(password),
            display_name=uname,
            role="member",
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(tenant)

        token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            username=user.username,
            tenant_slug=tenant.slug,
        )
        return self._login_payload(user, tenant, token)

    async def login(self, username: str, password: str) -> dict:
        uname = username.strip().lower()

        stmt = (
            select(User)
            .where(User.username == uname, User.is_active.is_(True))
            .options(selectinload(User.tenant))
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user or not user.tenant or not verify_password(password, user.password_hash):
            raise ValueError("账号或密码错误")

        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            tenant_slug=user.tenant.slug,
        )
        return self._login_payload(user, user.tenant, token)

    @staticmethod
    def _login_payload(user: User, tenant: Tenant, token: str) -> dict:
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "username": user.username,
                "display_name": user.display_name,
            },
            "tenant": {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
            },
        }
