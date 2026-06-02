"""
智能摘要生成服务

支持长文本的 MapReduce 分块摘要
"""

import logging
from typing import List, Optional
from datetime import datetime

from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class SummaryService:
    """摘要生成服务"""

    # 分块大小（字符数）
    CHUNK_SIZE = 1500
    # 分块重叠大小
    CHUNK_OVERLAP = 200

    def __init__(self):
        self.llm = get_llm()

    async def summarize(
        self, content: str, max_length: int = 200, title: str = ""
    ) -> str:
        """
        生成内容摘要

        Args:
            content: 原始内容
            max_length: 摘要最大长度（字符）
            title: 标题（可选）

        Returns:
            摘要文本
        """
        if not content:
            return ""

        # 短文本直接摘要
        if len(content) <= self.CHUNK_SIZE:
            return await self._summarize_short(content, max_length, title)

        # 长文本使用 MapReduce
        return await self._summarize_long(content, max_length, title)

    async def _summarize_short(self, content: str, max_length: int, title: str) -> str:
        """短文本摘要"""
        prompt = f"""请为以下文本生成一个简短的摘要（{max_length}字以内）。

{title if title else "无标题"}

原文：
{content[:2000]}

摘要："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)
            summary = response.content.strip()

            # 限制长度
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."

            return summary

        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return content[:max_length] + "..."

    async def _summarize_long(self, content: str, max_length: int, title: str) -> str:
        """长文本 MapReduce 摘要"""

        # 1. Map: 分块并生成每块摘要
        chunks = self._split_into_chunks(content)
        logger.info(f"Split content into {len(chunks)} chunks")

        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            chunk_summary = await self._summarize_short(
                chunk,
                max_length=max_length // 2,
                title=f"{title} (第{i+1}部分)" if title else "",
            )
            chunk_summaries.append(chunk_summary)

        # 2. Reduce: 合并摘要
        combined = "\n".join(chunk_summaries)

        reduce_prompt = f"""请将以下 {len(chunk_summaries)} 个片段摘要合并成一个完整的摘要（{max_length}字以内）。

{title if title else "无标题"}

片段摘要：
{combined}

完整摘要："""

        try:
            messages = [Message(role=MessageRole.USER, content=reduce_prompt)]
            response = await self.llm.invoke(messages)
            final_summary = response.content.strip()

            if len(final_summary) > max_length:
                final_summary = final_summary[:max_length] + "..."

            return final_summary

        except Exception as e:
            logger.error(f"Reduce summary failed: {e}")
            return " ".join(chunk_summaries)[:max_length]

    def _split_into_chunks(self, text: str) -> List[str]:
        """将文本分块"""
        if len(text) <= self.CHUNK_SIZE:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.CHUNK_SIZE, len(text))

            # 尝试在句号、问号、感叹号处分割
            if end < len(text):
                # 向后查找最佳分割点
                for sep in ["。", "！", "？", "\n\n", "\n", "。", ".", "!", "?"]:
                    pos = text.rfind(sep, start, end)
                    if pos > start + self.CHUNK_SIZE // 2:
                        end = pos + 1
                        break

            chunks.append(text[start:end].strip())
            start = end - self.CHUNK_OVERLAP if end < len(text) else end

        return chunks

    async def summarize_batch(
        self, items: List[dict], max_length: int = 100
    ) -> List[dict]:
        """
        批量生成摘要

        Args:
            items: [{"id": "...", "content": "...", "title": "..."}]
            max_length: 每个摘要的最大长度

        Returns:
            添加了 summary 字段的 items
        """
        results = []
        for item in items:
            summary = await self.summarize(
                item.get("content", ""),
                max_length=max_length,
                title=item.get("title", ""),
            )
            item["summary"] = summary
            results.append(item)

        return results
