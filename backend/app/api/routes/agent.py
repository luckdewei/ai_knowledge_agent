from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import AsyncGenerator
import json
import logging

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.agent.graph import PersonalKnowledgeAgent
from app.models.response import APIResponse, success_response
from app.services.chat_service import ChatService
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    stream: bool = False
    use_memory: bool = True
    auto_memory: bool = True


class MemoryCreateBody(BaseModel):
    content: str
    memory_type: str = "long_term"
    importance_score: float = 0.6
    ttl_hours: int | None = None
    session_id: str | None = None


class MemorySummarizeBody(BaseModel):
    session_id: str


class SaveKnowledgeFromChatRequest(BaseModel):
    title: str
    content: str
    tags: list[str] | None = None
    source_query: str | None = None


class ChatData(BaseModel):
    response: str
    session_id: str
    thinking_chain: dict | None = None


_agent_cache: dict[str, PersonalKnowledgeAgent] = {}


async def get_agent(
    db_session: AsyncSession, tenant_id
) -> PersonalKnowledgeAgent:
    from app.core.agent.tools.init_tools import ensure_tools_initialized

    cache_key = str(tenant_id)
    await ensure_tools_initialized(db_session, tenant_id)
    if cache_key not in _agent_cache:
        _agent_cache[cache_key] = PersonalKnowledgeAgent(db_session, tenant_id)
    else:
        _agent_cache[cache_key].db_session = db_session
        _agent_cache[cache_key].tenant_id = tenant_id
    return _agent_cache[cache_key]


@router.post("/chat", response_model=APIResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """对话接口（租户隔离）"""
    chat_svc = ChatService(db, current)
    try:
        session_id = await chat_svc.resolve_session_id(request.session_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    await chat_svc.add_message(session_id, "user", request.query)
    agent = await get_agent(db, current.tenant_id)

    if request.stream:
        return StreamingResponse(
            stream_agent_response(
                agent,
                request.query,
                session_id,
                db,
                current,
                use_memory=request.use_memory,
                auto_memory=request.auto_memory,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    response = await agent.run(
        request.query,
        session_id,
        user_id=current.id,
        use_memory=request.use_memory,
    )
    await chat_svc.add_message(session_id, "assistant", response)
    if request.auto_memory and response:
        await _auto_save_memories(
            db, current, session_id, request.query, response
        )
    return success_response(
        data=ChatData(
            response=response,
            session_id=session_id,
            thinking_chain=None,
        )
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _auto_save_memories(
    db: AsyncSession,
    current: CurrentUser,
    session_id: str,
    user_query: str,
    assistant_answer: str,
) -> list[dict]:
    from app.services.memory_service import MemoryService

    saved = await MemoryService(
        db, current.tenant_id, current.id
    ).llm_extract_and_save_memories(session_id, user_query, assistant_answer)
    return [
        {
            "id": str(m.id),
            "memory_type": m.memory_type,
            "content": m.content,
        }
        for m in saved
    ]


async def stream_agent_response(
    agent: PersonalKnowledgeAgent,
    query: str,
    session_id: str,
    db: AsyncSession,
    current: CurrentUser,
    *,
    use_memory: bool = True,
    auto_memory: bool = True,
) -> AsyncGenerator[str, None]:
    from app.core.agent.fast_path import classify_query

    chat_svc = ChatService(db, current)
    mode = classify_query(query)
    hints = {
        "chitchat": "正在回复…",
        "knowledge": "正在检索知识库…",
        "tools": "正在调用工具…",
        "complex": "正在规划与执行任务…",
    }
    yield _sse({"type": "session", "content": session_id})
    yield _sse({"type": "thinking_start", "content": hints.get(mode, "处理中…")})
    yield _sse(
        {
            "type": "thinking_step",
            "content": f"路由：{mode} 模式 — {hints.get(mode, '处理中…')}",
        }
    )

    chunks: list[str] = []
    try:
        async for item in agent.stream_tokens(
            query,
            session_id,
            user_id=current.id,
            use_memory=use_memory,
        ):
            if isinstance(item, dict):
                step = item.get("content")
                if item.get("type") == "status" and step:
                    yield _sse({"type": "thinking_step", "content": step})
                yield _sse(item)
            elif item:
                chunks.append(item)
                yield _sse({"type": "content", "content": item})
        answer = "".join(chunks)
        if answer:
            await chat_svc.add_message(session_id, "assistant", answer)
            if auto_memory:
                yield _sse(
                    {"type": "thinking_step", "content": "正在分析是否需要写入记忆…"}
                )
                saved = await _auto_save_memories(
                    db, current, session_id, query, answer
                )
                if saved:
                    summary = "；".join(s["content"][:40] for s in saved[:2])
                    yield _sse(
                        {
                            "type": "thinking_step",
                            "content": f"已记住 {len(saved)} 条：{summary}",
                        }
                    )
                    yield _sse(
                        {
                            "type": "memory_saved",
                            "content": json.dumps(saved, ensure_ascii=False),
                        }
                    )
        yield _sse({"type": "end"})
    except Exception as e:
        logger.exception("Agent stream error")
        yield _sse({"type": "error", "content": str(e)})
        yield _sse({"type": "end"})


@router.post("/sessions", response_model=APIResponse)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    chat_svc = ChatService(db, current)
    session_id = await chat_svc.create_session()
    return success_response(
        data={"id": session_id, "title": None},
        message="新对话已创建",
    )


@router.delete("/sessions/{session_id}", response_model=APIResponse)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    chat_svc = ChatService(db, current)
    ok = await chat_svc.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success_response(message="对话已删除")


@router.get("/sessions", response_model=APIResponse)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    chat_svc = ChatService(db, current)
    sessions = await chat_svc.list_sessions()
    return success_response(
        data=[
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    )


@router.get("/sessions/{session_id}/messages", response_model=APIResponse)
async def list_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    chat_svc = ChatService(db, current)
    try:
        messages = await chat_svc.list_messages(session_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return success_response(
        data=[
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "thinking": m.thinking,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    )


@router.post("/save-knowledge", response_model=APIResponse)
async def save_knowledge_from_chat(
    body: SaveKnowledgeFromChatRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    from app.models.schemas import KnowledgeCreate

    if not body.title.strip() or not body.content.strip():
        raise HTTPException(status_code=400, detail="标题与内容不能为空")

    service = KnowledgeService(db, current.tenant_id)
    meta: dict = {"saved_via": "agent_chat", "user_id": str(current.id)}
    if body.source_query:
        meta["source_query"] = body.source_query

    knowledge = await service.create(
        KnowledgeCreate(
            title=body.title.strip()[:500],
            content=body.content.strip(),
            source_type="agent",
            tags=body.tags or ["agent"],
            metadata=meta,
        )
    )
    return success_response(
        data={"knowledge_id": str(knowledge.id), "title": knowledge.title}
    )


@router.get("/memories", response_model=APIResponse)
async def list_memories(
    memory_type: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    from app.services.memory_service import MemoryService

    items = await MemoryService(db, current.tenant_id, current.id).list_memories(
        memory_type=memory_type, session_id=session_id, limit=min(limit, 100)
    )
    return success_response(data=[m.to_dict() for m in items])


@router.post("/memories", response_model=APIResponse)
async def create_memory(
    body: MemoryCreateBody,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    from app.services.memory_service import MemoryService

    if body.memory_type not in ("short_term", "long_term", "episodic"):
        raise HTTPException(status_code=400, detail="无效的记忆类型")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="记忆内容不能为空")

    ctx = {}
    if body.session_id:
        ctx["session_id"] = body.session_id

    mem = await MemoryService(db, current.tenant_id, current.id).add_memory(
        content=body.content.strip(),
        memory_type=body.memory_type,
        context=ctx or None,
        importance_score=body.importance_score,
        ttl_hours=body.ttl_hours,
    )
    return success_response(data=mem.to_dict(), message="记忆已保存")


@router.delete("/memories/{memory_id}", response_model=APIResponse)
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    import uuid as uuid_mod

    from app.services.memory_service import MemoryService

    try:
        mid = uuid_mod.UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的记忆 ID")

    ok = await MemoryService(db, current.tenant_id, current.id).delete_memory(mid)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return success_response(message="已删除")


@router.post("/memories/{memory_id}/promote", response_model=APIResponse)
async def promote_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    import uuid as uuid_mod

    from app.services.memory_service import MemoryService

    try:
        mid = uuid_mod.UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的记忆 ID")

    mem = await MemoryService(db, current.tenant_id, current.id).promote_to_long_term(
        mid
    )
    if not mem:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return success_response(data=mem.to_dict(), message="已转为长期记忆")


@router.post("/memories/summarize", response_model=APIResponse)
async def summarize_session_memories(
    body: MemorySummarizeBody,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    from app.services.memory_service import MemoryService

    chat_svc = ChatService(db, current)
    try:
        messages = await chat_svc.list_messages(body.session_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    conversation = [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in ("user", "assistant") and m.content
    ]
    summary = await MemoryService(db, current.tenant_id, current.id).summarize_session(
        body.session_id, conversation
    )
    return success_response(data={"summary": summary}, message="会话已总结为情景记忆")


@router.get("/think/{session_id}")
async def get_thinking_chain(session_id: str):
    raise HTTPException(status_code=501, detail="思考链查询尚未实现")
