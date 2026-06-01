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
    if state.get("search_queries") and len(state["search_queries"]) > 0:
        return "retriever"
    elif state.get("plan") and any("调用" in step for step in state["plan"]):
        return "executor"
    else:
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

    def __init__(self, db_session):
        self.db_session = db_session

        # 初始化节点
        self.planner = PlannerNode()
        self.retriever = RetrieverNode(db_session)
        self.reasoner = ReasonerNode()
        self.executor = ExecutorNode()  # tool_registry 后续注入
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

        # 固定流转
        workflow.add_edge("retriever", "reasoner")
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

    async def run(self, user_query: str, session_id: str = "default") -> str:
        """
        运行 Agent

        Args:
            user_query: 用户输入
            session_id: 会话 ID（用于记忆持久化）

        Returns:
            Agent 的最终响应
        """
        # 创建初始状态
        initial_state = create_initial_state(user_query, session_id)

        # 配置
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}

        # 执行图
        final_state = await self.graph.ainvoke(initial_state, config=config)

        # 返回最终响应
        return final_state.get("final_response", "抱歉，我无法生成回复。")

    async def stream(self, user_query: str, session_id: str = "default"):
        """
        流式运行 Agent（实时输出思考过程）

        Yields: 每个节点的输出
        """
        initial_state = create_initial_state(user_query, session_id)
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}

        async for event in self.graph.astream(initial_state, config=config):
            yield event
