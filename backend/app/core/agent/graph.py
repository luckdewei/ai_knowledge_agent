"""
LangGraph 状态图构建

定义节点之间的流转关系和条件路由"""

import logging
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.core.agent.state import AgentState, create_initial_state
from app.core.agent.nodes import (
    PlannerNode,
    RetrieverNode,
    ReasonerNode,
    ExecutorNode,
    ReflectorNode,
    ResponderNode,
)

logger = logging.getLogger(__name__)


def route_after_planner(
    state: AgentState,
) -> Literal["retriever", "executor", "responder"]:
    """
    规划后的路由

    - 需要搜索：进入检索节点
    - 需要执行工具：进入执行节点
    - 可以直接回答：进入响应节点
    """
    plan = state.get("plan") or []
    if state.get("plan") and any("调用" in step for step in plan):
        return "executor"
    if state.get("search_queries"):
        return "retriever"
    return "responder"


def route_after_retriever(
    state: AgentState,
) -> Literal["reasoner", "responder"]:
    """检索后：复杂任务才走推理链，普通问答直接生成回复。"""
    from app.core.agent.state import AgentIntent

    intent = state.get("intent")
    if intent in (
        AgentIntent.ORGANIZE,
        AgentIntent.GENERATE,
        AgentIntent.SCHEDULE,
        AgentIntent.ANALYZE,
    ):
        return "reasoner"
    tools = (state.get("memory_context") or {}).get("needs_tools") or []
    if tools:
        return "reasoner"
    return "responder"


def route_after_reflector(state: AgentState) -> Literal["executor", "responder"]:
    """
    反思后的路由

    - 需要继续执行：回到执行节点
    - 执行完成：进入响应节点
    """
    if state.get("should_continue", False) and not state.get("is_satisfied", True):
        return "executor"
    else:
        return "responder"


class PersonalKnowledgeAgent:
    """个人知识 Agent"""

    def __init__(self, db_session, tenant_id):
        self.db_session = db_session
        self.tenant_id = tenant_id

        from app.core.agent.tools.registry import get_tool_registry

        # 初始化节点
        self.planner = PlannerNode()
        self.retriever = RetrieverNode(db_session, tenant_id)
        self.reasoner = ReasonerNode()
        self.executor = ExecutorNode(get_tool_registry())
        self.reflector = ReflectorNode()
        self.responder = ResponderNode()

        # 构建图
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph:
        """构建状态图"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("planner", self.planner.execute)
        workflow.add_node("retriever", self.retriever.execute)
        workflow.add_node("reasoner", self.reasoner.execute)
        workflow.add_node("executor", self.executor.execute)
        workflow.add_node("reflector", self.reflector.execute)
        workflow.add_node("responder", self.responder.execute)

        # 设置入口
        workflow.set_entry_point("planner")

        # planner 后的条件路由
        workflow.add_conditional_edges(
            "planner",
            route_after_planner,
            {
                "retriever": "retriever",
                "executor": "executor",
                "responder": "responder",
            },
        )

        workflow.add_conditional_edges(
            "retriever",
            route_after_retriever,
            {"reasoner": "reasoner", "responder": "responder"},
        )
        workflow.add_edge("reasoner", "executor")
        workflow.add_edge("executor", "reflector")

        # reflector 后的条件路由
        workflow.add_conditional_edges(
            "reflector",
            route_after_reflector,
            {
                "executor": "executor",
                "responder": "responder",
            },
        )

        # responder 结束
        workflow.add_edge("responder", END)

        return workflow.compile(checkpointer=self.memory)

    async def run(
        self,
        user_query: str,
        session_id: str = "default",
        *,
        user_id=None,
        use_memory: bool = True,
    ) -> str:
        """运行 Agent（优先快速路径）。"""
        from app.core.agent.fast_path import (
            classify_query,
            run_chitchat,
            run_knowledge,
            run_with_tools,
        )

        mode = classify_query(user_query)
        if mode == "chitchat":
            logger.info("Agent fast path: chitchat")
            return await run_chitchat(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            )
        if mode == "tools":
            logger.info("Agent fast path: tools")
            return await run_with_tools(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            )
        if mode == "knowledge":
            logger.info("Agent fast path: knowledge")
            return await run_knowledge(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            )

        initial_state = create_initial_state(user_query, session_id)
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        final_state = await self.graph.ainvoke(initial_state, config=config)
        return final_state.get("final_response", "抱歉，我无法生成回复。")

    async def stream_tokens(
        self,
        user_query: str,
        session_id: str = "default",
        *,
        user_id=None,
        use_memory: bool = True,
    ):
        """流式输出：状态事件 dict 或文本 token。"""
        from app.core.agent.fast_path import (
            classify_query,
            stream_chitchat,
            stream_knowledge,
            stream_with_tools,
        )

        mode = classify_query(user_query)
        if mode == "chitchat":
            async for token in stream_chitchat(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            ):
                yield token
            return
        if mode == "tools":
            async for item in stream_with_tools(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            ):
                yield item
            return
        if mode == "knowledge":
            async for token in stream_knowledge(
                self.db_session,
                user_query,
                self.tenant_id,
                session_id=session_id,
                user_id=user_id,
                use_memory=use_memory,
            ):
                yield token
            return

        yield {"type": "status", "content": "正在深度推理（耗时较长）…"}
        text = await self.run(user_query, session_id)
        if text:
            chunk_size = 40
            for i in range(0, len(text), chunk_size):
                yield text[i : i + chunk_size]

    async def stream(self, user_query: str, session_id: str = "default"):
        """流式运行 LangGraph 节点事件（调试用）。"""
        initial_state = create_initial_state(user_query, session_id)
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        async for event in self.graph.astream(initial_state, config=config):
            yield event
