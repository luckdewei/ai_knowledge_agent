"""
执行节点（增强版）

集成工具注册表，支持重试和降级
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.agent.state import AgentState, ToolCall, Observation, ObservationType
from app.core.agent.tools import ToolRegistry
from app.core.agent.tools.registry import get_tool_registry
from app.core.agent.tools.base import ToolStatus
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class ExecutorNode:
    """执行节点（增强版）"""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self.tool_registry = tool_registry or get_tool_registry()
        self.llm = get_llm()

    async def execute(self, state: AgentState) -> AgentState:
        """执行节点"""
        logger.info(f"Executing step {state['current_step'] + 1}/{len(state['plan'])}")

        if state["current_step"] >= len(state["plan"]):
            state["is_satisfied"] = True
            return state

        current_action = state["plan"][state["current_step"]]

        # 解析动作类型
        if current_action.startswith("调用"):
            await self._execute_tool_call(state, current_action)
        elif current_action.startswith("生成"):
            await self._execute_generation(state, current_action)
        else:
            await self._execute_llm_action(state, current_action)

        state["current_step"] += 1
        return state

    async def _execute_tool_call(self, state: AgentState, action: str):
        """执行工具调用（带重试和降级）"""
        # 解析工具名称和参数
        tool_name, tool_args = self._parse_tool_call(action)

        # 记录工具调用
        tool_call: ToolCall = {
            "tool_name": tool_name,
            "arguments": tool_args,
            "result": None,
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
        }
        state["tool_calls"].append(tool_call)

        # 执行工具
        result = await self.tool_registry.execute(tool_name, max_retries=3, **tool_args)

        tool_call["result"] = (
            str(result.data)
            if result.status == ToolStatus.SUCCESS
            else result.error
        )
        tool_call["status"] = (
            "success" if result.status == ToolStatus.SUCCESS else "failed"
        )

        if result.status == ToolStatus.SUCCESS:
            state["tool_results"][tool_name] = result.data
            self._add_observation(
                state,
                f"工具 {tool_name} 执行成功 ({result.execution_time_ms:.0f}ms)",
                "success",
            )
        else:
            self._add_observation(
                state, f"工具 {tool_name} 执行失败: {result.error}", "error"
            )

            # 尝试降级策略
            fallback_result = await self._try_fallback(
                tool_name, tool_args, result.error or "unknown error"
            )
            if fallback_result:
                state["tool_results"][f"{tool_name}_fallback"] = fallback_result
                self._add_observation(state, f"工具 {tool_name} 降级成功", "info")

    async def _execute_generation(self, state: AgentState, action: str):
        """执行生成任务"""
        prompt = f"""根据以下信息，{action}

用户问题: {state['user_query']}

检索到的知识:
{self._format_knowledge(state['retrieved_knowledge'])}

请生成符合要求的输出。"""

        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.llm.invoke(messages)

        state["tool_results"][f"generation_{state['current_step']}"] = response.content
        self._add_observation(state, f"生成完成: {response.content[:100]}...", "info")

    async def _execute_llm_action(self, state: AgentState, action: str):
        """LLM 执行通用动作"""
        prompt = f"""任务: {action}

用户问题: {state['user_query']}
检索知识: {len(state['retrieved_knowledge'])} 条
观察记录: {len(state.get('observations', []))} 条

请执行这个任务并输出结果。"""

        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.llm.invoke(messages)

        state["tool_results"][f"llm_action_{state['current_step']}"] = response.content

    async def _try_fallback(self, tool_name: str, tool_args: Dict, error: str) -> Any:
        """尝试降级策略"""
        # 降级策略1：使用 LLM 模拟
        if tool_name in ["search", "calendar"]:
            prompt = f"""工具 {tool_name} 执行失败，错误: {error}
参数: {tool_args}
请根据你的知识直接回答用户的需求。"""

            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await self.llm.invoke(messages)
            return {"fallback": True, "response": response.content}

        return None

    def _parse_tool_call(self, action: str) -> tuple:
        """解析工具调用字符串"""
        alias = {
            "搜索": "search",
            "知识库搜索": "search",
            "待办": "todo",
            "日历": "calendar",
            "邮件": "email",
        }

        parts = action.split(":", 1)
        raw_name = parts[0].replace("调用", "").strip()
        tool_name = alias.get(raw_name, raw_name)

        if tool_name == "todo":
            tool_args = {"action": "list", "status": "pending"}
        elif tool_name == "calendar":
            tool_args = {"action": "query", "days": 7}
        elif tool_name == "search":
            tool_args = {
                "query": parts[1].strip() if len(parts) > 1 else "",
                "source": "both",
                "top_k": 5,
            }
        elif len(parts) > 1:
            tool_args = {"query": parts[1].strip()}
        else:
            tool_args = {}

        return tool_name, tool_args

    def _format_knowledge(self, knowledge: list) -> str:
        """格式化知识"""
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
        """添加观察记录"""
        obs: Observation = {
            "content": content,
            "type": obs_type,
            "timestamp": datetime.now().isoformat(),
        }
        state["observations"].append(obs)
