from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import AsyncGenerator
import json
import asyncio

from app.core.database import get_db
from app.core.agent.graph import PersonalKnowledgeAgent
from app.models.response import APIResponse, success_response

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    stream: bool = False


class ChatData(BaseModel):
    response: str
    session_id: str
    thinking_chain: dict | None = None


_agent_cache: dict[str, PersonalKnowledgeAgent] = {}


async def get_agent(db_session: AsyncSession) -> PersonalKnowledgeAgent:
    """获取或创建 Agent 实例"""
    if "default" not in _agent_cache:
        _agent_cache["default"] = PersonalKnowledgeAgent(db_session)
    return _agent_cache["default"]


@router.post("/chat", response_model=APIResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """对话接口"""
    agent = await get_agent(db)

    if request.stream:
        return StreamingResponse(
            stream_agent_response(agent, request.query, request.session_id),
            media_type="text/event-stream",
        )

    response = await agent.run(request.query, request.session_id)
    return success_response(
        data=ChatData(
            response=response,
            session_id=request.session_id,
            thinking_chain=None,
        )
    )


async def stream_agent_response(
    agent: PersonalKnowledgeAgent, query: str, session_id: str
) -> AsyncGenerator[str, None]:
    """流式输出 Agent 思考和响应"""
    yield f"data: {json.dumps({'type': 'thinking_start', 'content': '正在分析您的问题...'})}\n\n"
    await asyncio.sleep(0.1)

    response = await agent.run(query, session_id)

    for char in response:
        yield f"data: {json.dumps({'type': 'content', 'content': char})}\n\n"
        await asyncio.sleep(0.01)

    yield f"data: {json.dumps({'type': 'end'})}\n\n"


@router.get("/think/{session_id}")
async def get_thinking_chain(session_id: str):
    """获取思考链（用于调试和展示）"""
    raise HTTPException(status_code=501, detail="思考链查询尚未实现")
