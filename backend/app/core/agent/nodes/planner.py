import json
import logging
from datetime import datetime
from typing import Dict, Any

from app.core.agent.state import AgentState, AgentIntent, Observation, ObservationType
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class PlannerNode:
    """
    规划节点

    分析用户请求，输出结构化的执行计划。
    使用 Few-shot 提示词引导 LLM 输出 JSON 格式。
    """

    PLANNER_PROMPT = """你是一个智能知识管理助手。分析用户请求并制定执行计划。

## 可用能力
- 检索：从知识库中搜索相关内容
- 整理：对知识进行聚类、打标签、去重
- 生成：写邮件、写大纲、生成学习计划
- 调度：设置提醒、创建待办、发送邮件
- 分析：发现知识间的隐含联系、趋势分析

## 输出格式（只返回 JSON）
{{
    "reasoning": "一步步的思考过程...",
    "intent": "query|search|organize|generate|schedule|analyze",
    "plan": ["步骤1", "步骤2", "步骤3"],
    "needs_search": true/false,
    "needs_tools": ["tool1", "tool2"]
}}

## 用户请求
{query}

## 输出
"""

    def __init__(self):
        self.llm = get_llm()

    async def execute(self, state: AgentState) -> AgentState:
        """执行规划节点"""
        logger.info(f"Planning for: {state['user_query'][:50]}...")

        heuristic = self._heuristic_plan(state["user_query"])
        if heuristic:
            self._apply_plan(state, heuristic)
            return state

        prompt = self.PLANNER_PROMPT.format(query=state["user_query"])

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)

            plan_data = self._parse_response(response.content)
            self._apply_plan(state, plan_data)
            self._add_observation(
                state, f"规划完成，意图: {state['intent'].value}", "info"
            )

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            state["error"] = str(e)
            self._apply_plan(
                state,
                {
                    "reasoning": f"自动规划（解析失败: {e}）",
                    "intent": "query",
                    "plan": ["生成回答"],
                    "needs_search": False,
                    "needs_tools": [],
                },
            )

        return state

    def _heuristic_plan(self, query: str) -> dict | None:
        from app.core.agent.fast_path import classify_query

        mode = classify_query(query)
        if mode == "chitchat":
            return {
                "reasoning": "寒暄类问题，无需检索知识库",
                "intent": "query",
                "plan": ["直接回答"],
                "needs_search": False,
                "needs_tools": [],
            }
        if mode == "knowledge":
            return {
                "reasoning": "知识问答，检索后回答",
                "intent": "search",
                "plan": ["检索相关知识", "生成回答"],
                "needs_search": True,
                "needs_tools": [],
            }
        return None

    def _parse_intent(self, raw: str) -> AgentIntent:
        try:
            return AgentIntent(raw)
        except ValueError:
            return AgentIntent.UNKNOWN

    def _apply_plan(self, state: AgentState, plan_data: dict) -> None:
        needs_search = plan_data.get("needs_search", True)
        if isinstance(needs_search, str):
            needs_search = needs_search.lower() in ("true", "1", "yes")

        state["reasoning"] = plan_data.get("reasoning", "")
        state["intent"] = self._parse_intent(plan_data.get("intent", "query"))
        state["plan"] = plan_data.get("plan", [])
        state["search_queries"] = [state["user_query"]] if needs_search else []
        state["memory_context"]["needs_tools"] = plan_data.get("needs_tools", [])

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 响应，提取 JSON"""
        content = content.strip()

        # 处理 markdown 代码块
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "reasoning": content[:300],
                "intent": "query",
                "plan": ["检索相关知识", "生成回答"],
                "needs_search": True,
                "needs_tools": [],
            }

    def _add_observation(
        self,
        state: AgentState,
        content: str,
        obs_type: ObservationType = "info",
    ):
        """添加观察记录"""
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
