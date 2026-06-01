"""
Agent 状态定义

使用 TypedDict 确保类型安全，Annotated + operator.add 实现增量更新
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from operator import add
from datetime import datetime
from enum import Enum


class AgentIntent(str, Enum):
    """Agent 意图类型"""

    QUERY = "query"  # 简单查询
    SEARCH = "search"  # 深度搜索
    ORGANIZE = "organize"  # 整理归纳
    GENERATE = "generate"  # 生成内容
    SCHEDULE = "schedule"  # 调度任务
    ANALYZE = "analyze"  # 分析洞察
    UNKNOWN = "unknown"


class ToolCall(TypedDict):
    """工具调用记录"""

    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str]
    status: Literal["pending", "success", "failed"]
    timestamp: str


ObservationType = Literal["info", "warning", "error", "success"]


class Observation(TypedDict):
    """观察记录"""

    content: str
    type: ObservationType
    timestamp: str


class AgentState(TypedDict):
    """Agent 完整状态"""

    # ========== 基础信息 ==========
    messages: Annotated[List[Dict[str, str]], add]
    user_query: str
    session_id: str

    # ========== 规划相关 ==========
    intent: AgentIntent
    plan: List[str]
    current_step: int
    max_steps: int

    # ========== 检索相关 ==========
    retrieved_knowledge: List[Dict[str, Any]]
    search_queries: List[str]

    # ========== 推理相关 ==========
    reasoning: str
    hypotheses: List[str]

    # ========== 执行相关 ==========
    tool_calls: Annotated[List[ToolCall], add]
    tool_results: Dict[str, Any]

    # ========== 反思相关 ==========
    observations: Annotated[List[Observation], add]
    is_satisfied: bool
    needs_retry: bool
    retry_count: int
    should_continue: bool

    # ========== 生成相关 ==========
    final_response: str
    suggested_actions: List[str]

    # ========== 记忆相关 ==========
    memory_context: Dict[str, Any]
    similar_past_cases: List[Dict[str, Any]]

    # ========== 元数据 ==========
    created_at: str
    updated_at: str
    error: Optional[str]


def create_initial_state(user_query: str, session_id: str) -> AgentState:
    """创建初始状态"""
    now = datetime.now().isoformat()

    return {
        # 基础信息
        "messages": [{"role": "user", "content": user_query}],
        "user_query": user_query,
        "session_id": session_id,
        # 规划相关
        "intent": AgentIntent.UNKNOWN,
        "plan": [],
        "current_step": 0,
        "max_steps": 10,
        # 检索相关
        "retrieved_knowledge": [],
        "search_queries": [],
        # 推理相关
        "reasoning": "",
        "hypotheses": [],
        # 执行相关
        "tool_calls": [],
        "tool_results": {},
        # 反思相关
        "observations": [],
        "is_satisfied": False,
        "needs_retry": False,
        "retry_count": 0,
        "should_continue": True,
        # 生成相关
        "final_response": "",
        "suggested_actions": [],
        # 记忆相关
        "memory_context": {},
        "similar_past_cases": [],
        # 元数据
        "created_at": now,
        "updated_at": now,
        "error": None,
    }
