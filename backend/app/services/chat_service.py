"""租户隔离的 Agent 会话与消息持久化。"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import AgentSession, ChatMessage
from app.core.deps import CurrentUser


class ChatService:
    def __init__(self, db: AsyncSession, user: CurrentUser):
        self.db = db
        self.user = user

    def _new_session_id(self) -> str:
        return (
            f"t{self.user.tenant_id.hex[:8]}-"
            f"u{self.user.id.hex[:8]}-"
            f"{uuid.uuid4().hex[:12]}"
        )

    async def create_session(self, title: str | None = None) -> str:
        new_id = self._new_session_id()
        session = AgentSession(
            id=new_id,
            tenant_id=self.user.tenant_id,
            user_id=self.user.id,
            title=title,
        )
        self.db.add(session)
        await self.db.commit()
        return new_id

    async def resolve_session_id(self, session_id: str | None) -> str:
        """校验已有会话，或为占位符创建新会话。"""
        sid = (session_id or "").strip()
        if sid and sid not in ("default", "new"):
            existing = await self.get_session(sid)
            if existing:
                return sid
            raise PermissionError("会话不存在或无权访问")
        return await self.create_session()

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        stmt = select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.tenant_id == self.user.tenant_id,
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session and session.user_id and session.user_id != self.user.id:
            return None
        return session

    async def _touch_session(
        self, session_id: str, *, user_content: str | None = None
    ) -> None:
        session = await self.get_session(session_id)
        if not session:
            return
        session.updated_at = datetime.now(timezone.utc)
        if user_content and not (session.title or "").strip():
            text = user_content.strip().replace("\n", " ")
            session.title = (text[:80] + "…") if len(text) > 80 else text or "新对话"
        await self.db.commit()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        if not await self.get_session(session_id):
            raise PermissionError("会话不存在或无权访问")
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            extra_metadata=metadata,
        )
        self.db.add(msg)
        await self.db.flush()
        if role == "user":
            await self._touch_session(session_id, user_content=content)
        else:
            await self._touch_session(session_id)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def list_sessions(self, limit: int = 50) -> list[AgentSession]:
        stmt = (
            select(AgentSession)
            .where(
                AgentSession.tenant_id == self.user.tenant_id,
                AgentSession.user_id == self.user.id,
            )
            .order_by(desc(AgentSession.updated_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_messages(self, session_id: str, limit: int = 200) -> list[ChatMessage]:
        if not await self.get_session(session_id):
            raise PermissionError("会话不存在或无权访问")
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_session(self, session_id: str) -> bool:
        session = await self.get_session(session_id)
        if not session:
            return False
        await self.db.delete(session)
        await self.db.commit()
        return True
