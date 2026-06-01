from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import AsyncGenerator
import json
import asyncio

from app.core.database import get_db
from app.core.agent.graph import PersonalKnowledgeAgent

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    thinking_chain: dict | None = None


# 全局 Agent 实例缓存
_agent_cache: dict[str, PersonalKnowledgeAgent] = {}


async def get_agent(db_session: AsyncSession) -> PersonalKnowledgeAgent:
    """获取或创建 Agent 实例"""
    # 简单缓存，实际可根据 session_id 管理
    if "default" not in _agent_cache:
        _agent_cache["default"] = PersonalKnowledgeAgent(db_session)
    return _agent_cache["default"]


@router.post("/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """对话接口"""
    agent = await get_agent(db)

    if request.stream:
        # 流式响应
        return StreamingResponse(
            stream_agent_response(agent, request.query, request.session_id),
            media_type="text/event-stream",
        )
    else:
        # 非流式响应
        response = await agent.run(request.query, request.session_id)
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            thinking_chain=None,  # 可扩展返回思考链
        )


async def stream_agent_response(
    agent: PersonalKnowledgeAgent, query: str, session_id: str
) -> AsyncGenerator[str, None]:
    """流式输出 Agent 思考和响应"""

    # 发送思考开始标记
    yield f"data: {json.dumps({'type': 'thinking_start', 'content': '正在分析您的问题...'})}\n\n"
    await asyncio.sleep(0.1)

    # 这里简化实现，实际应该逐节点输出
    response = await agent.run(query, session_id)

    # 逐字符输出响应
    for char in response:
        yield f"data: {json.dumps({'type': 'content', 'content': char})}\n\n"
        await asyncio.sleep(0.01)

    # 发送结束标记
    yield f"data: {json.dumps({'type': 'end'})}\n\n"


@router.get("/think/{session_id}")
async def get_thinking_chain(session_id: str):
    """
    获取思考链（用于调试和展示）

    返回 Agent 的完整思考过程
    """
    # 需要从检查点恢复状态
    # LangGraph 的 MemorySaver 支持状态恢复
    raise HTTPException(status_code=501, detail="思考链查询尚未实现")
