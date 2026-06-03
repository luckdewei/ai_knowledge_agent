"""
知识问答：知识库未命中时联网搜索，并生成可入库草稿。
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools.web_search import tavily_web_search
from app.models.schemas import SearchRequest
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

# 低于此相似度视为「知识库不足以回答」
RELEVANCE_THRESHOLD = 0.55
RETRIEVE_MIN_SIMILARITY = 0.35
WEB_SEARCH_TIMEOUT_SEC = 22.0
KB_SEARCH_TIMEOUT_SEC = 10.0

# 用户明确要求联网 / 实时行情类问题
WEB_SEARCH_HINTS = (
    "联网",
    "网络搜索",
    "网上搜",
    "网上查",
    "实时",
    "最新",
    "A股",
    "a股",
    "港股",
    "沪深",
    "上证",
    "深证",
    "创业板",
    "北交所",
    "股票",
    "行情",
    "股价",
    "大盘",
    "指数",
    "涨停",
    "跌停",
    "东方财富",
    "同花顺",
)


def query_wants_web(query: str) -> bool:
    q = query.strip()
    return any(h in q for h in WEB_SEARCH_HINTS)


def optimize_web_query(query: str) -> str:
    """为 Tavily 优化检索词（尤其 A 股/行情类）。"""
    q = query.strip()
    if any(k in q for k in ("A股", "a股", "沪深", "股票", "行情", "大盘", "指数")):
        if "2024" not in q and "2025" not in q and "2026" not in q:
            return f"{q} 中国股市 最新行情"
    return q


@dataclass
class KnowledgeContext:
    kb_lines: str
    web_lines: Optional[str]
    web_used: bool
    kb_hit: bool
    web_items: list[dict[str, Any]]


async def retrieve_kb_context(
    db: AsyncSession, query: str, tenant_id, top_k: int = 4
) -> tuple[KnowledgeContext, str]:
    """仅检索知识库，返回上下文与思考过程摘要。"""
    service = KnowledgeService(db, tenant_id)
    kb_hit = False
    kb_lines = "（知识库中未找到高相关内容）"
    summary = "知识库检索完成：未找到足够相关内容"

    try:
        rows, _ = await asyncio.wait_for(
            service.search_semantic(
                SearchRequest(
                    query=query,
                    top_k=top_k,
                    min_similarity=RETRIEVE_MIN_SIMILARITY,
                )
            ),
            timeout=KB_SEARCH_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning("Knowledge retrieval timed out after %ss", KB_SEARCH_TIMEOUT_SEC)
        rows = []
        summary = f"知识库检索超时（>{KB_SEARCH_TIMEOUT_SEC:.0f}s），已跳过"
    except Exception as e:
        logger.warning("Knowledge retrieval failed: %s", e)
        rows = []
        summary = f"知识库检索异常：{e}"

    strong = [(k, s) for k, s in rows if s >= RELEVANCE_THRESHOLD]
    if strong:
        kb_hit = True
        lines = []
        for i, (k, score) in enumerate(strong[:top_k], 1):
            lines.append(
                f"{i}. 《{k.title}》（相关度 {score:.0%}）\n{k.content[:400]}"
            )
        kb_lines = "\n\n".join(lines)
        top_score = strong[0][1]
        summary = (
            f"知识库命中 {len(strong)} 条（最高相关度 {top_score:.0%}），"
            f"例如《{strong[0][0].title[:30]}》"
        )

    ctx = KnowledgeContext(
        kb_lines=kb_lines,
        web_lines=None,
        web_used=False,
        kb_hit=kb_hit,
        web_items=[],
    )
    return ctx, summary


async def gather_knowledge_context(
    db: AsyncSession, query: str, tenant_id, top_k: int = 4
) -> KnowledgeContext:
    """检索知识库；不足时补充网络搜索。"""
    ctx, _ = await retrieve_kb_context(db, query, tenant_id, top_k)
    if ctx.kb_hit:
        return ctx

    web_lines, web_items, _err = await _fetch_web_search(db, query, top_k=5)
    ctx.web_lines = web_lines
    ctx.web_items = web_items
    ctx.web_used = bool(web_items)
    return ctx


async def _fetch_web_search(
    db: AsyncSession, query: str, top_k: int = 5
) -> tuple[str, list[dict[str, Any]], Optional[str]]:
    """直连 Tavily，避免经工具注册表导致额外耗时与 18s 误超时。"""
    del db  # 保留签名以兼容调用方

    search_q = optimize_web_query(query)
    try:
        items, err = await asyncio.wait_for(
            tavily_web_search(search_q, top_k, timeout=WEB_SEARCH_TIMEOUT_SEC),
            timeout=WEB_SEARCH_TIMEOUT_SEC + 3,
        )
    except asyncio.TimeoutError:
        logger.warning("Web search wait_for timed out after %ss", WEB_SEARCH_TIMEOUT_SEC)
        err = f"联网搜索超时（>{WEB_SEARCH_TIMEOUT_SEC:.0f}s）"
        items = []

    if err:
        return f"（联网搜索失败：{err}）", [], err
    if not items:
        return "（联网搜索未返回结果）", [], "Tavily 返回 0 条结果"

    lines = ["## 网络搜索结果（知识库未覆盖，以下为补充资料）"]
    for i, item in enumerate(items[:top_k], 1):
        title = item.get("title") or "无标题"
        url = item.get("url") or ""
        content = (item.get("content") or "")[:400]
        head = f"{i}. [{title}]({url})" if url else f"{i}. {title}"
        lines.append(f"{head}\n{content}")
    return "\n\n".join(lines), items, None


def build_user_prompt(query: str, ctx: KnowledgeContext) -> str:
    parts = [f"## 知识库资料\n{ctx.kb_lines}"]
    if ctx.web_lines:
        parts.append(ctx.web_lines)
    parts.append(f"\n## 用户问题\n{query}")
    return "\n".join(parts)


_MD_FORMAT = (
    "请使用 Markdown 格式输出（可用 ## 标题、列表、表格、**加粗**、`代码`、链接等），"
    "结构清晰，便于界面渲染。不要输出 ```markdown 代码围栏包裹整段回答。"
)

KNOWLEDGE_SYSTEM = (
    "你是个人知识库助手。优先依据「知识库资料」回答；若提供了「网络搜索结果」，"
    "可结合网络资料补充回答，并简要说明信息来源（知识库 / 网络）。"
    "不要编造未在参考资料中出现的事实。回答末尾可提示用户：若需保留本次回答，"
    "可点击「保存到知识库」或使用保存功能。"
    + _MD_FORMAT
)

KNOWLEDGE_SYSTEM_KB_ONLY = (
    "你是个人知识库助手。根据「知识库资料」回答用户问题。"
    "有相关内容时引用要点；没有时诚实说明，可建议用户先导入笔记。"
    + _MD_FORMAT
)


def system_prompt_for(ctx: KnowledgeContext) -> str:
    return KNOWLEDGE_SYSTEM if ctx.web_used else KNOWLEDGE_SYSTEM_KB_ONLY


def build_save_draft(
    query: str, answer: str, ctx: KnowledgeContext
) -> dict[str, Any]:
    """生成可写入知识库的草稿（供前端一键保存）。"""
    title = _title_from_query(query)
    content_parts = [answer.strip()]
    if ctx.web_items:
        content_parts.append("\n\n---\n## 参考来源（联网搜索）")
        for item in ctx.web_items[:5]:
            t = item.get("title") or ""
            u = item.get("url") or ""
            snippet = (item.get("content") or "")[:200]
            if u:
                content_parts.append(f"- [{t}]({u})\n  {snippet}")
            elif t:
                content_parts.append(f"- {t}\n  {snippet}")
    content_parts.append(f"\n\n---\n*原始问题：{query.strip()}*")
    return {
        "title": title,
        "content": "\n".join(content_parts).strip(),
        "tags": ["agent", "web-search"] if ctx.web_used else ["agent"],
        "source_query": query.strip(),
    }


def _title_from_query(query: str) -> str:
    q = re.sub(r"\s+", " ", query.strip())
    if len(q) <= 60:
        return q or "Agent 对话摘录"
    return q[:57] + "…"


def save_draft_json(draft: dict[str, Any]) -> str:
    return json.dumps(draft, ensure_ascii=False)
