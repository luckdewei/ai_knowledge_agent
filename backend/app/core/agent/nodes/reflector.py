import json
import logging
from datetime import datetime
from typing import Dict, Any

from app.core.agent.state import AgentState, Observation, ObservationType
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class ReflectorNode:
    """反思节点"""

    REFLECTOR_PROMPT = """评估以下执行结果。

## 用户问题
{query}

## 执行计划
{plan}

## 当前进度
第 {step}/{total} 步

## 执行结果
{results}

## 观察记录
{observations}

输出JSON格式：
{{
    "reasoning": "评估思考过程...",
    "is_satisfied": true/false,
    "needs_retry": true/false,
    "should_continue": true/false,
    "adjustments": ["调整建议"],
    "final_answer": "如果可以回答，直接给出答案"
}}

## 输出
"""

    def __init__(self, max_retries: int = 3):
        self.llm = get_llm()
        self.max_retries = max_retries

    async def execute(self, state: AgentState) -> AgentState:
        logger.info("Reflecting on execution...")

        if state["retry_count"] >= self.max_retries:
            self._add_observation(
                state, f"达到最大重试次数 ({self.max_retries})", "warning"
            )
            state["is_satisfied"] = True
            return state

        prompt = self.REFLECTOR_PROMPT.format(
            query=state["user_query"],
            plan=" -> ".join(state["plan"]),
            step=state["current_step"],
            total=len(state["plan"]),
            results=self._format_results(state),
            observations=self._format_observations(state.get("observations", [])),
        )

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)

            reflection = self._parse_response(response.content)

            state["reasoning"] = reflection.get("reasoning", state["reasoning"])

            if reflection.get("is_satisfied", False):
                state["is_satisfied"] = True
                if "final_answer" in reflection and reflection["final_answer"]:
                    state["final_response"] = reflection["final_answer"]
            else:
                state["is_satisfied"] = False

                if reflection.get("needs_retry", False):
                    state["needs_retry"] = True
                    state["retry_count"] += 1

                    adjustments = reflection.get("adjustments", [])
                    if adjustments:
                        state["plan"] = (
                            adjustments + state["plan"][state["current_step"] :]
                        )
                        state["current_step"] = 0

                    self._add_observation(
                        state, f"需要重试 (第 {state['retry_count']} 次)", "info"
                    )
                else:
                    state["needs_retry"] = False
                    state["is_satisfied"] = True

            state["should_continue"] = reflection.get(
                "should_continue",
                not state["is_satisfied"]
                and state["current_step"] < state["max_steps"],
            )

        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            state["is_satisfied"] = True
            state["should_continue"] = False

        return state

    def _format_results(self, state: AgentState) -> str:
        results = []

        for tool_call in state.get("tool_calls", []):
            results.append(f"- 工具 {tool_call['tool_name']}: {tool_call['status']}")

        if state.get("retrieved_knowledge"):
            results.append(f"- 检索到 {len(state['retrieved_knowledge'])} 条知识")

        return "\n".join(results) if results else "无执行结果"

    def _format_observations(self, observations: list) -> str:
        if not observations:
            return "无观察记录"
        return "\n".join(
            [f"- [{obs['type']}] {obs['content']}" for obs in observations[-10:]]
        )

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
                "is_satisfied": True,
                "needs_retry": False,
                "should_continue": False,
                "adjustments": [],
                "final_answer": content,
            }

    def _add_observation(
        self, state: AgentState, content: str, obs_type: ObservationType
    ):
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
