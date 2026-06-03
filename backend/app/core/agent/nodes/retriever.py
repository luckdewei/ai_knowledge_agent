import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.state import AgentState, AgentIntent, Observation, ObservationType
from app.services.knowledge_service import KnowledgeService
from app.models.schemas import SearchRequest

logger = logging.getLogger(__name__)


class RetrieverNode:
    """检索节点"""

    def __init__(self, db_session: AsyncSession, tenant_id):
        self.db = db_session
        self.knowledge_service = KnowledgeService(db_session, tenant_id)

    async def execute(self, state: AgentState) -> AgentState:
        logger.info(f"Retrieving for intent: {state['intent'].value}")

        intent = state["intent"]

        if intent == AgentIntent.ANALYZE:
            await self._retrieve_timeline(state)
        elif intent == AgentIntent.ORGANIZE:
            await self._retrieve_unorganized(state)
        else:
            await self._retrieve_semantic(state)

        if intent == AgentIntent.ANALYZE and len(state["retrieved_knowledge"]) >= 2:
            await self._discover_connections(state)

        self._add_observation(
            state, f"检索到 {len(state['retrieved_knowledge'])} 条相关知识", "info"
        )

        return state

    async def _retrieve_semantic(self, state: AgentState):
        """语义向量检索"""
        query = state["user_query"]

        search_request = SearchRequest(query=query, top_k=5, min_similarity=0.58)
        results, _ = await self.knowledge_service.search_semantic(search_request)

        state["retrieved_knowledge"] = [
            {
                "id": str(k.id),
                "title": k.title,
                "content": k.content[:500],
                "similarity": score,
                "tags": k.tags or [],
                "created_at": k.created_at.isoformat(),
                "source_type": k.source_type,
            }
            for k, score in results
        ]
        state["search_queries"].append(query)

    async def _retrieve_timeline(self, state: AgentState):
        """时间序列检索"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        knowledge_list = await self.knowledge_service.get_by_time_range(
            start_date, end_date
        )

        state["retrieved_knowledge"] = [
            {
                "timeline": self._group_by_date(knowledge_list),
                "total_count": len(knowledge_list),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
            }
        ]

    async def _retrieve_unorganized(self, state: AgentState):
        """检索未分类内容"""
        from sqlalchemy import select
        from app.models.knowledge import Knowledge

        stmt = (
            select(Knowledge)
            .where(Knowledge.tags.is_(None))
            .order_by(Knowledge.created_at.desc())
            .limit(20)
        )

        result = await self.db.execute(stmt)
        unorganized = result.scalars().all()

        state["retrieved_knowledge"] = [
            {
                "id": str(k.id),
                "title": k.title,
                "content": k.content[:500],
                "created_at": k.created_at.isoformat(),
            }
            for k in unorganized
        ]

    async def _discover_connections(self, state: AgentState):
        """发现隐含联系"""
        if not state["retrieved_knowledge"]:
            return

        # 提取内容
        contents = []
        for item in state["retrieved_knowledge"][:5]:
            if isinstance(item, dict) and "content" in item:
                contents.append(
                    f"标题: {item.get('title', '')}\n内容: {item.get('content', '')[:200]}"
                )

        if len(contents) < 2:
            return

        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()
        prompt = f"""分析以下知识片段之间的隐含联系：

{chr(10).join([f'--- 片段{i+1} ---{c}' for i, c in enumerate(contents)])}

输出JSON格式：
{{"is_connected": true/false, "common_theme": "共同主题", "insights": ["洞察1", "洞察2"]}}"""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)

            import json

            content = response.content.strip()
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end]

            connections = json.loads(content)

            if connections.get("is_connected"):
                self._add_observation(
                    state,
                    f"发现隐含联系: {connections.get('common_theme', '未知主题')}",
                    "info",
                )
                state["suggested_actions"].append(
                    f"归类到「{connections.get('common_theme')}」"
                )
        except Exception as e:
            logger.debug(f"Connection discovery failed: {e}")

    def _group_by_date(self, knowledge_list) -> Dict[str, List]:
        """按日期分组"""
        timeline = {}
        for k in knowledge_list:
            date_key = k.created_at.strftime("%Y-%m-%d")
            if date_key not in timeline:
                timeline[date_key] = []
            timeline[date_key].append({"id": str(k.id), "title": k.title})
        return timeline

    def _add_observation(
        self,
        state: AgentState,
        content: str,
        obs_type: ObservationType = "info",
    ):
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
