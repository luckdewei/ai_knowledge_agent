import logging
from datetime import datetime
from typing import Dict, Any

from app.core.agent.state import AgentState, ToolCall, Observation, ObservationType
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class ExecutorNode:
    """执行节点"""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry  # 第七章实现

    async def execute(self, state: AgentState) -> AgentState:
        logger.info(f"Executing step {state['current_step'] + 1}/{len(state['plan'])}")

        if state["current_step"] >= len(state["plan"]):
            state["is_satisfied"] = True
            return state

        current_action = state["plan"][state["current_step"]]

        if current_action.startswith("调用"):
            await self._execute_tool_call(state, current_action)
        elif current_action.startswith("生成"):
            await self._execute_generation(state, current_action)
        else:
            await self._execute_llm_action(state, current_action)

        state["current_step"] += 1
        return state

    async def _execute_tool_call(self, state: AgentState, action: str):
        """执行工具调用"""
        parts = action.split(":", 1)
        if len(parts) != 2:
            tool_name = action.replace("调用", "").strip()
            tool_args = {"query": state["user_query"]}
        else:
            tool_name = parts[0].replace("调用", "").strip()
            tool_args = {"query": parts[1].strip()}

        tool_call: ToolCall = {
            "tool_name": tool_name,
            "arguments": tool_args,
            "result": None,
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
        }
        state["tool_calls"].append(tool_call)

        if self.tool_registry:
            try:
                result = await self.tool_registry.execute(tool_name, **tool_args)
                tool_call["result"] = str(result)[:1000]
                tool_call["status"] = "success"
                state["tool_results"][tool_name] = result
                self._add_observation(state, f"工具 {tool_name} 执行成功", "success")
            except Exception as e:
                tool_call["result"] = str(e)
                tool_call["status"] = "failed"
                self._add_observation(state, f"工具 {tool_name} 失败: {e}", "error")
        else:
            tool_call["status"] = "failed"
            tool_call["result"] = "工具注册表未初始化"

    async def _execute_generation(self, state: AgentState, action: str):
        """执行生成任务"""
        llm = get_llm()

        prompt = f"""根据以下信息，{action}

用户问题: {state['user_query']}

检索到的知识:
{self._format_knowledge(state['retrieved_knowledge'])}

请生成符合要求的输出。"""

        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await llm.invoke(messages)

        state["tool_results"][f"generation_{state['current_step']}"] = response.content
        self._add_observation(state, f"生成完成: {response.content[:100]}...", "info")

    async def _execute_llm_action(self, state: AgentState, action: str):
        """LLM 执行通用动作"""
        llm = get_llm()

        prompt = f"""任务: {action}

用户问题: {state['user_query']}
检索知识: {len(state['retrieved_knowledge'])} 条

请执行这个任务并输出结果。"""

        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await llm.invoke(messages)

        state["tool_results"][f"llm_action_{state['current_step']}"] = response.content

    def _format_knowledge(self, knowledge: list) -> str:
        if not knowledge:
            return "无"

        lines = []
        for i, item in enumerate(knowledge[:5]):
            if isinstance(item, dict):
                title = item.get("title", "无标题")
                content = item.get("content", "")[:300]
                lines.append(f"### {i+1}. {title}\n{content}")

        return "\n\n".join(lines)

    def _add_observation(
        self, state: AgentState, content: str, obs_type: ObservationType
    ):
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
