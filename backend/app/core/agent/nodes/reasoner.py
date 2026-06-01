import json
import logging
from datetime import datetime
from typing import Dict, Any

from app.core.agent.state import AgentState, Observation, ObservationType
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class ReasonerNode:
    """推理节点"""

    REASONER_PROMPT = """基于以下信息进行推理。

## 用户问题
{query}

## 检索到的知识
{knowledge}

## 观察记录
{observations}

输出JSON格式：
{{
    "reasoning": "一步步的推理过程...",
    "can_answer": true/false,
    "missing_info": ["缺失信息1"],
    "insights": ["洞察1"],
    "suggested_tools": ["tool1"],
    "confidence": 0.95
}}

## 输出
"""

    def __init__(self):
        self.llm = get_llm()

    async def execute(self, state: AgentState) -> AgentState:
        logger.info("Reasoning...")

        prompt = self.REASONER_PROMPT.format(
            query=state["user_query"],
            knowledge=self._summarize_knowledge(state["retrieved_knowledge"]),
            observations=self._summarize_observations(state.get("observations", [])),
        )

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)

            reasoning_data = self._parse_response(response.content)

            state["reasoning"] = reasoning_data.get("reasoning", state["reasoning"])
            state["hypotheses"] = reasoning_data.get("insights", [])

            if reasoning_data.get("can_answer", False):
                state["is_satisfied"] = True
            else:
                suggested_tools = reasoning_data.get("suggested_tools", [])
                if suggested_tools:
                    for tool in suggested_tools:
                        state["plan"].append(f"调用{tool}")
                    state["needs_retry"] = True

            self._add_observation(
                state,
                f"推理完成，置信度: {reasoning_data.get('confidence', 0)}",
                "info",
            )

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            state["reasoning"] = f"推理失败: {e}"
            state["is_satisfied"] = True

        return state

    def _summarize_knowledge(self, knowledge: list) -> str:
        if not knowledge:
            return "未检索到相关知识"

        summaries = []
        for i, item in enumerate(knowledge[:5]):
            if isinstance(item, dict):
                title = item.get("title", "无标题")
                content = item.get("content", "")[:200]
                similarity = item.get("similarity", 0)
                summaries.append(
                    f"{i+1}. [{title}] (相似度: {similarity:.2f})\n   {content}..."
                )

        return "\n\n".join(summaries)

    def _summarize_observations(self, observations: list) -> str:
        if not observations:
            return "无观察记录"
        return "\n".join([f"- {obs['content']}" for obs in observations[-5:]])

    def _parse_response(self, content: str) -> Dict[str, Any]:
        content = content.strip()

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
                "can_answer": True,
                "missing_info": [],
                "insights": [],
                "suggested_tools": [],
                "confidence": 0.5,
            }

    def _add_observation(
        self, state: AgentState, content: str, obs_type: ObservationType = "info"
    ):
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
