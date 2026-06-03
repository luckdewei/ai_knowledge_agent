"""
Agent 工具调用：根据用户意图选择并执行注册表中的工具。
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.llm import get_llm, Message, MessageRole
from app.core.agent.tools.init_tools import ensure_tools_initialized
from app.core.agent.tools.registry import get_tool_registry
from app.core.agent.tools.base import ToolStatus

logger = logging.getLogger(__name__)

_TOOL_KEYWORDS = (
    "待办",
    "任务",
    "todo",
    "日历",
    "日程",
    "会议",
    "邮件",
    "发邮件",
    "搜索",
    "查一下",
    "联网",
    "保存",
    "存入",
)


def query_needs_tools(query: str) -> bool:
    q = query.lower()
    return any(k.lower() in q for k in _TOOL_KEYWORDS)


def _parse_save_params(query: str) -> Optional[dict[str, Any]]:
    """从「保存到知识库」类消息中解析标题与正文。"""
    m_title = re.search(r"标题[：:]\s*(.+?)(?:\n|内容[：:]|$)", query, re.S | re.I)
    m_content = re.search(r"内容[：:]\s*(.+)$", query, re.S | re.I)
    if m_title and m_content:
        return {
            "title": m_title.group(1).strip()[:500],
            "content": m_content.group(1).strip(),
        }
    return None


def _heuristic_tool_call(query: str) -> Optional[dict[str, Any]]:
    q = query.strip()

    if re.search(r"(保存|存入|记入|写入).{0,12}(知识库|笔记|库里)", q, re.I):
        params = _parse_save_params(q)
        if params:
            return {"tool_name": "save_knowledge", "params": params}
        return None

    if re.search(r"待办|任务|todo", q, re.I):
        if re.search(r"添加|创建|新建|记", q):
            title = re.sub(r".*?(添加|创建|新建|记录?)\s*", "", q).strip(" ：:，,")
            return {
                "tool_name": "todo",
                "params": {
                    "action": "add",
                    "title": title[:200] or "新待办",
                    "priority": 2,
                },
            }
        return {"tool_name": "todo", "params": {"action": "list", "status": "pending"}}

    if re.search(r"日历|日程|会议|空闲", q, re.I):
        return {"tool_name": "calendar", "params": {"action": "query", "days": 7}}

    if re.search(r"邮件|发邮件", q, re.I):
        return {
            "tool_name": "email",
            "params": {
                "action": "send",
                "subject": "来自知识助手的邮件",
                "body": q,
            },
        }

    if re.search(r"知识库|笔记|内部", q, re.I):
        return {
            "tool_name": "search",
            "params": {"query": q, "source": "knowledge", "top_k": 5},
        }

    if re.search(r"搜索|查一下|联网|网络搜索", q, re.I):
        from app.core.agent.knowledge_gap import query_wants_web

        source = "web" if query_wants_web(q) else "both"
        return {
            "tool_name": "search",
            "params": {"query": q, "source": source, "top_k": 8 if source == "web" else 5},
        }

    return None


async def _llm_select_tool(query: str) -> Optional[dict[str, Any]]:
    await ensure_tools_initialized()
    registry = get_tool_registry()
    tools = registry.list_tools()
    if not tools:
        return None

    prompt = f"""根据用户请求，从下列工具中选择一个并给出参数 JSON。
只返回 JSON：{{"tool_name": "...", "params": {{...}}}}
若无合适工具，返回 {{"tool_name": null}}

可用工具：
{json.dumps(tools, ensure_ascii=False, indent=2)}

用户请求：{query}
"""
    llm = get_llm(fast=True)
    resp = await llm.invoke([Message(role=MessageRole.USER, content=prompt)])
    content = resp.content.strip()
    if "```" in content:
        start = content.find("{")
        end = content.rfind("}") + 1
        content = content[start:end] if start >= 0 else content
    try:
        data = json.loads(content)
        if data.get("tool_name"):
            return {"tool_name": data["tool_name"], "params": data.get("params", {})}
    except json.JSONDecodeError:
        logger.warning("Tool selection JSON parse failed")
    return None


async def invoke_tools_for_query(
    db: AsyncSession,
    query: str,
    *,
    tenant_id=None,
    use_llm: bool = True,
) -> list[dict[str, Any]]:
    """执行工具链，返回每次调用的结果摘要。"""
    await ensure_tools_initialized(db, tenant_id)
    registry = get_tool_registry()

    call = _heuristic_tool_call(query)
    if not call and use_llm:
        call = await _llm_select_tool(query)

    if not call:
        from app.core.agent.fast_path import query_wants_save

        if query_wants_save(query):
            return [
                {
                    "tool_name": "save_knowledge",
                    "success": False,
                    "error": "请使用回答下方的「保存到知识库」按钮，或在消息中写明「标题：」「内容：」",
                }
            ]
        return []

    tool_name = call["tool_name"]
    params = call.get("params") or {}

    if tool_name not in {t["name"] for t in registry.list_tools()}:
        return [
            {
                "tool_name": tool_name,
                "success": False,
                "error": f"工具 {tool_name} 未注册",
            }
        ]

    try:
        result = await asyncio.wait_for(
            registry.execute(tool_name, **params),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        return [
            {
                "tool_name": tool_name,
                "success": False,
                "error": "工具执行超时（>40s）",
            }
        ]
    return [
        {
            "tool_name": tool_name,
            "params": params,
            "success": result.status == ToolStatus.SUCCESS,
            "data": result.data,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }
    ]


def format_tool_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = ["## 工具执行结果"]
    for r in results:
        name = r.get("tool_name", "?")
        if r.get("success"):
            lines.append(f"- **{name}** 成功：{json.dumps(r.get('data'), ensure_ascii=False)[:800]}")
        else:
            lines.append(f"- **{name}** 失败：{r.get('error', 'unknown')}")
    return "\n".join(lines)
