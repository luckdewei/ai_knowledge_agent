"""
工具基类定义

所有工具必须继承 BaseTool 并实现 execute 方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ToolStatus(str, Enum):
    """工具执行状态"""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RETRYING = "retrying"


@dataclass
class ToolResult:
    """工具执行结果"""

    status: ToolStatus
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolParameter:
    """工具参数定义"""

    name: str
    type: str  # string, number, boolean, object, array
    description: str
    required: bool = False
    enum: Optional[List[str]] = None
    default: Any = None


class BaseTool(ABC):
    """工具基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    def parameters(self) -> List[ToolParameter]:
        """工具参数列表"""
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass

    def to_openai_function(self) -> Dict[str, Any]:
        """
        转换为 OpenAI Function Calling 格式

        用于 LLM 的工具调用
        """
        properties = {}
        required = []

        for param in self.parameters:
            param_def: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                param_def["enum"] = param.enum
            if param.default is not None:
                param_def["default"] = param.default

            properties[param.name] = param_def

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
