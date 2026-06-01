import logging
from datetime import datetime

from app.core.agent.state import AgentState, Observation, ObservationType
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class ResponderNode:
    """响应节点"""

    RESPONDER_PROMPT = """根据以下信息生成最终回复。

## 用户问题
{query}

## 检索到的知识
{knowledge}

## 推理过程
{reasoning}

## 执行结果
{results}

## 观察记录
{observations}

请生成友好、自然的回复。如果知识库中有相关信息，请引用；如果没有，请诚实告知。
"""

    def __init__(self):
        self.llm = get_llm()

    async def execute(self, state: AgentState) -> AgentState:
        logger.info("Generating final response...")

        # 如果反思节点已经生成了最终答案，直接使用
        if state["final_response"]:
            return state

        prompt = self.RESPONDER_PROMPT.format(
            query=state["user_query"],
            knowledge=self._format_knowledge(state["retrieved_knowledge"]),
            reasoning=state.get("reasoning", "无推理过程"),
            results=self._format_results(state),
            observations=self._format_observations(state.get("observations", [])),
        )

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)

            state["final_response"] = response.content

            self._add_observation(state, "最终响应生成完成", "success")

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            state["final_response"] = f"抱歉，生成回复时遇到问题: {e}"

        return state

    def _format_knowledge(self, knowledge: list) -> str:
        if not knowledge:
            return "未找到相关知识"

        lines = []
        for i, item in enumerate(knowledge[:5]):
            if isinstance(item, dict):
                title = item.get("title", "无标题")
                content = item.get("content", "")[:300]
                similarity = item.get("similarity", 0)
                lines.append(
                    f"{i+1}. **{title}** (相关度: {similarity:.0%})\n   {content}..."
                )

        return "\n\n".join(lines)

    def _format_results(self, state: AgentState) -> str:
        results = []

        for key, value in state.get("tool_results", {}).items():
            if key.startswith("generation_"):
                results.append(f"生成内容: {str(value)[:200]}...")
            elif key.startswith("llm_action_"):
                results.append(f"执行结果: {str(value)[:200]}...")

        return "\n".join(results) if results else "无执行结果"

    def _format_observations(self, observations: list) -> str:
        if not observations:
            return "无"
        return "\n".join([f"- {obs['content']}" for obs in observations[-10:]])

    def _add_observation(
        self, state: AgentState, content: str, obs_type: ObservationType
    ):
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
