"""
Agent 快速路径：闲聊 / 知识问答不走完整 LangGraph，减少 LLM 调用与延迟。
"""

import json
import re
import logging
import uuid
from typing import AsyncIterator, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.llm import get_llm, Message, MessageRole
from app.core.agent.memory_context import (
    append_memory_to_system,
    load_memory_for_query,
)
from app.core.agent.knowledge_gap import (
    gather_knowledge_context,
    retrieve_kb_context,
    build_user_prompt,
    system_prompt_for,
    build_save_draft,
    save_draft_json,
    KNOWLEDGE_SYSTEM,
    _fetch_web_search,
    query_wants_web,
)

logger = logging.getLogger(__name__)

QueryMode = Literal["chitchat", "knowledge", "tools", "complex"]

_CHITCHAT_RE = re.compile(
    r"^(你好|您好|嗨|hello|hi|hey|谢谢|感谢|再见|拜拜|在吗|你是谁|"
    r"介绍一下|早上好|晚上好|下午好)[\s!！?？。~]*$",
    re.IGNORECASE,
)

_COMPLEX_KEYWORDS = ("整理", "聚类", "去重", "发邮件", "待办", "日程", "调用工具", "批量")

_KNOWLEDGE_HINTS = (
    "知识",
    "笔记",
    "学了",
    "学习",
    "总结",
    "查找",
    "搜索",
    "检索",
    "最近",
    "相关",
    "有哪些",
    "帮我找",
    "告诉我",
)

_SAVE_KNOWLEDGE_RE = re.compile(
    r"(保存|存入|记入|写入).{0,12}(知识库|笔记|库里)",
    re.IGNORECASE,
)


def query_wants_save(query: str) -> bool:
    return bool(_SAVE_KNOWLEDGE_RE.search(query.strip()))


def classify_query(query: str) -> QueryMode:
    from app.core.agent.tool_invoker import query_needs_tools

    q = query.strip()
    if not q:
        return "chitchat"
    if len(q) <= 36 and _CHITCHAT_RE.match(q):
        return "chitchat"
    # 联网/A股等走知识路径 + 强制 Tavily，避免「搜索」关键词误入 tools 卡住
    if query_wants_web(q):
        return "knowledge"
    if query_wants_save(q):
        return "tools"
    if query_needs_tools(q):
        return "tools"
    if any(k in q for k in _COMPLEX_KEYWORDS):
        return "complex"
    if any(k in q for k in _KNOWLEDGE_HINTS) or len(q) > 12:
        return "knowledge"
    if len(q) <= 20:
        return "chitchat"
    return "knowledge"


CHITCHAT_SYSTEM = (
    "你是「智能个人知识库助手」。用简洁友好的中文回复。"
    "用户若是寒暄，直接回应即可，不要编造知识库内容。"
    "回复请使用 Markdown 格式（列表、加粗等），便于界面渲染。"
)


async def _load_memory_addon(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    session_id: str,
    query: str,
    use_memory: bool,
) -> tuple[str, list]:
    return await load_memory_for_query(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )


async def _prepare_knowledge_messages(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> tuple[list[Message], object]:
    ctx = await gather_knowledge_context(db, query, tenant_id)
    user_content = build_user_prompt(query, ctx)
    addon, _ = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    system = append_memory_to_system(system_prompt_for(ctx), addon)
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=user_content),
    ]
    return messages, ctx


async def run_chitchat(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> str:
    addon, _ = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    llm = get_llm(fast=True)
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=append_memory_to_system(CHITCHAT_SYSTEM, addon),
        ),
        Message(role=MessageRole.USER, content=query),
    ]
    resp = await llm.invoke(messages)
    return resp.content or "你好！有什么可以帮你的？"


async def run_with_tools(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> str:
    from app.core.agent.tool_invoker import invoke_tools_for_query, format_tool_results

    results = await invoke_tools_for_query(db, query, tenant_id=tenant_id)
    tool_ctx = format_tool_results(results)
    llm = get_llm(fast=True)
    addon, _ = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    user_content = f"{tool_ctx}\n\n## 用户问题\n{query}\n\n请根据工具结果用中文回答用户。"
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=append_memory_to_system(KNOWLEDGE_SYSTEM, addon),
        ),
        Message(role=MessageRole.USER, content=user_content or query),
    ]
    resp = await llm.invoke(messages)
    return resp.content or "工具已执行，但未生成说明。"


async def stream_with_tools(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> AsyncIterator[str | dict]:
    import asyncio

    from app.core.agent.tool_invoker import invoke_tools_for_query, format_tool_results

    # 明确要求联网时改走知识路径（直连 Tavily，更快且有心智进度）
    if query_wants_web(query):
        async for item in stream_knowledge(
            db,
            query,
            tenant_id,
            session_id=session_id,
            user_id=user_id,
            use_memory=use_memory,
        ):
            yield item
        return

    addon, mem_items = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    if mem_items:
        yield _thinking_step(f"① 已加载 {len(mem_items)} 条相关记忆")
        yield {
            "type": "memory_context",
            "content": json.dumps(mem_items, ensure_ascii=False),
        }
    yield _thinking_step("② 分析用户意图，选择工具…")
    yield {"type": "status", "content": "正在调用工具…"}
    try:
        results = await asyncio.wait_for(
            invoke_tools_for_query(db, query, tenant_id=tenant_id),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        results = [
            {
                "tool_name": "tools",
                "success": False,
                "error": "工具调用超时（>40s），请稍后重试或检查 API 配置",
            }
        ]
    yield _thinking_step(f"③ 工具调用完成（共 {len(results)} 项）")
    for r in results:
        yield {
            "type": "tool_call",
            "content": json.dumps(
                {
                    "tool": r.get("tool_name"),
                    "success": r.get("success"),
                    "error": r.get("error"),
                },
                ensure_ascii=False,
            ),
        }
    tool_ctx = format_tool_results(results)
    user_content = f"{tool_ctx}\n\n## 用户问题\n{query}"
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=append_memory_to_system(KNOWLEDGE_SYSTEM, addon),
        ),
        Message(role=MessageRole.USER, content=user_content),
    ]
    yield _thinking_step("④ 根据工具结果生成回答…")
    async for token in stream_llm_reply(messages):
        yield token


async def run_knowledge(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> str:
    messages, _ctx = await _prepare_knowledge_messages(
        db,
        query,
        tenant_id,
        session_id=session_id,
        user_id=user_id,
        use_memory=use_memory,
    )
    llm = get_llm(fast=True)
    resp = await llm.invoke(messages)
    return resp.content or "抱歉，我暂时无法生成回复。"


async def stream_llm_reply(messages: list[Message]) -> AsyncIterator[str]:
    llm = get_llm(fast=True)
    async for token in llm.stream(messages):
        if token:
            yield token


async def stream_chitchat(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> AsyncIterator[str | dict]:
    addon, mem_items = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    if mem_items:
        yield _thinking_step(f"已加载 {len(mem_items)} 条相关记忆")
        yield {
            "type": "memory_context",
            "content": json.dumps(mem_items, ensure_ascii=False),
        }
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=append_memory_to_system(CHITCHAT_SYSTEM, addon),
        ),
        Message(role=MessageRole.USER, content=query),
    ]
    async for token in stream_llm_reply(messages):
        yield token


def _thinking_step(content: str) -> dict:
    return {"type": "thinking_step", "content": content}


async def stream_knowledge(
    db: AsyncSession,
    query: str,
    tenant_id: uuid.UUID,
    *,
    session_id: str = "default",
    user_id: uuid.UUID | None = None,
    use_memory: bool = True,
) -> AsyncIterator[str | dict]:
    addon, mem_items = await _load_memory_addon(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        query=query,
        use_memory=use_memory,
    )
    if mem_items:
        yield _thinking_step(f"① 已加载 {len(mem_items)} 条相关记忆")
        yield {
            "type": "memory_context",
            "content": json.dumps(mem_items, ensure_ascii=False),
        }
    force_web = query_wants_web(query)

    if force_web:
        yield _thinking_step("② 用户要求联网，正在检索实时信息（Tavily）…")
        yield {"type": "status", "content": "正在联网搜索…"}
        web_lines, web_items, web_err = await _fetch_web_search(db, query, top_k=8)
        yield _thinking_step("③ 并行检索知识库（补充内部笔记，最多 10s）…")
        ctx, kb_summary = await retrieve_kb_context(db, query, tenant_id)
        ctx.web_lines = web_lines
        ctx.web_items = web_items
        ctx.web_used = bool(web_items)
        n = len(web_items)
        if n:
            yield _thinking_step(f"④ 联网搜索完成，获取 {n} 条；{kb_summary}")
        elif web_err:
            yield _thinking_step(f"④ 联网搜索失败：{web_err}；{kb_summary}")
        else:
            yield _thinking_step(f"④ 联网无结果；{kb_summary}")
        yield {
            "type": "tool_call",
            "content": json.dumps(
                {
                    "tool": "search",
                    "success": bool(web_items),
                    "source": "web",
                    "error": web_err,
                },
                ensure_ascii=False,
            ),
        }
    else:
        yield _thinking_step("② 理解用户问题并准备检索…")
        yield {"type": "status", "content": "正在检索知识库…"}
        yield _thinking_step("③ 生成查询向量，并在知识库中语义检索…")
        ctx, kb_summary = await retrieve_kb_context(db, query, tenant_id)
        yield _thinking_step(f"④ {kb_summary}")

        if not ctx.kb_hit:
            yield _thinking_step("⑤ 知识库未覆盖，正在联网搜索…")
            yield {"type": "status", "content": "知识库未命中，正在联网搜索…"}
            web_lines, web_items, web_err = await _fetch_web_search(db, query, top_k=5)
            ctx.web_lines = web_lines
            ctx.web_items = web_items
            ctx.web_used = bool(web_items)
            n = len(web_items)
            if n:
                yield _thinking_step(f"⑥ 联网搜索完成，获取 {n} 条参考结果")
            elif web_err:
                yield _thinking_step(f"⑥ 联网搜索失败：{web_err}")
            else:
                yield _thinking_step("⑥ 联网搜索无结果，将基于模型知识回答")
            yield {
                "type": "tool_call",
                "content": json.dumps(
                    {
                        "tool": "search",
                        "success": bool(web_items),
                        "source": "web",
                        "error": web_err,
                    },
                    ensure_ascii=False,
                ),
            }
        else:
            yield _thinking_step("⑤ 知识库已有相关内容，跳过联网搜索")

    yield _thinking_step("正在组织回答并流式生成…")
    yield {"type": "status", "content": "正在生成回答…"}

    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=append_memory_to_system(system_prompt_for(ctx), addon),
        ),
        Message(role=MessageRole.USER, content=build_user_prompt(query, ctx)),
    ]

    chunks: list[str] = []
    async for token in stream_llm_reply(messages):
        chunks.append(token)
        yield token

    answer = "".join(chunks)
    if answer:
        yield _thinking_step("⑦ 回答生成完成")
    if answer and (ctx.web_used or not ctx.kb_hit):
        draft = build_save_draft(query, answer, ctx)
        yield {"type": "save_suggestion", "content": save_draft_json(draft)}
