"""
工具注册表

管理所有可用工具，支持注册、获取、执行、限流和重试
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Union
from datetime import datetime
from collections import defaultdict
from enum import Enum

from .base import BaseTool, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class RateLimiter:
    """令牌桶限流器"""

    def __init__(self, rate: float = 10, per: float = 1.0):
        """
        初始化限流器

        Args:
            rate: 每秒允许的请求数
            per: 时间窗口（秒）
        """
        self.rate = rate
        self.per = per
        self.tokens = rate
        self.last_refill = datetime.now()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """获取令牌"""
        async with self.lock:
            now = datetime.now()
            elapsed = (now - self.last_refill).total_seconds()

            # 补充令牌
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            else:
                # 等待一个令牌
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                return await self.acquire()


class RetryStrategy:
    """重试策略"""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """带重试的执行"""
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except self.retryable_exceptions as e:
                if attempt < self.max_retries:
                    # 计算退避时间
                    delay = min(
                        self.initial_delay * (self.backoff_factor**attempt),
                        self.max_delay,
                    )
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}, retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries + 1} attempts failed: {e}")
                    raise

        raise RuntimeError("execute_with_retry failed without capturing an exception")


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._retry_strategies: Dict[str, RetryStrategy] = {}
        self._middlewares: List[Callable] = []

    def register(
        self,
        tool: BaseTool,
        rate_limit: Optional[int] = None,
        retry_config: Optional[Dict] = None,
    ):
        """
        注册工具

        Args:
            tool: 工具实例
            rate_limit: 每分钟最大调用次数
            retry_config: 重试配置
        """
        self._tools[tool.name] = tool

        # 配置限流
        if rate_limit:
            self._rate_limiters[tool.name] = RateLimiter(
                rate=rate_limit / 60, per=1.0  # 转换为每秒
            )

        # 配置重试
        if retry_config:
            self._retry_strategies[tool.name] = RetryStrategy(**retry_config)

        logger.info(f"Registered tool: {tool.name} (rate_limit={rate_limit})")

    def unregister(self, tool_name: str):
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._rate_limiters.pop(tool_name, None)
            self._retry_strategies.pop(tool_name, None)
            logger.info(f"Unregistered tool: {tool_name}")

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": [
                    {"name": p.name, "type": p.type, "required": p.required}
                    for p in tool.parameters
                ],
            }
            for tool in self._tools.values()
        ]

    def get_openai_functions(self) -> List[Dict[str, Any]]:
        """获取 OpenAI Function Calling 格式的工具列表"""
        return [tool.to_openai_function() for tool in self._tools.values()]

    def use(self, middleware: Callable):
        """添加中间件"""
        self._middlewares.append(middleware)
        return self

    async def execute(
        self, tool_name: str, max_retries: Optional[int] = None, **kwargs
    ) -> ToolResult:
        """
        执行工具

        Args:
            tool_name: 工具名称
            max_retries: 最大重试次数（覆盖工具配置）
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        # 1. 获取工具
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                status=ToolStatus.FAILED, error=f"Tool '{tool_name}' not found"
            )

        # 2. 参数验证
        validation_error = self._validate_params(tool, kwargs)
        if validation_error:
            return ToolResult(status=ToolStatus.FAILED, error=validation_error)

        # 3. 限流检查
        if tool_name in self._rate_limiters:
            await self._rate_limiters[tool_name].acquire()

        # 4. 执行（带重试）
        retry_strategy = self._retry_strategies.get(tool_name)
        retry_count = (
            max_retries
            if max_retries is not None
            else (retry_strategy.max_retries if retry_strategy else 0)
        )

        # 包装执行函数
        async def execute_with_middleware():
            result = await tool.execute(**kwargs)

            # 应用中间件
            for middleware in self._middlewares:
                result = await middleware(tool_name, kwargs, result)

            return result

        # 执行
        for attempt in range(retry_count + 1):
            try:
                start_time = datetime.now()

                if retry_strategy and attempt < retry_count:
                    # 使用配置的重试策略
                    result = await retry_strategy.execute_with_retry(
                        execute_with_middleware
                    )
                else:
                    result = await execute_with_middleware()

                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                result.execution_time_ms = execution_time

                logger.info(
                    f"Tool '{tool_name}' executed successfully "
                    f"in {execution_time:.2f}ms"
                )
                return result

            except Exception as e:
                logger.warning(f"Tool '{tool_name}' attempt {attempt + 1} failed: {e}")

                if attempt == retry_count:
                    return ToolResult(
                        status=ToolStatus.FAILED,
                        error=f"Tool '{tool_name}' failed after {retry_count + 1} attempts: {str(e)}",
                    )

                # 退避等待
                await asyncio.sleep(1.0 * (2**attempt))

        # 不应该到达这里
        return ToolResult(status=ToolStatus.FAILED, error="Unexpected execution flow")

    def _validate_params(self, tool: BaseTool, kwargs: Dict) -> Optional[str]:
        """验证工具参数"""
        # 检查必需参数
        for param in tool.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"

        # 类型验证（简化版）
        for param in tool.parameters:
            if param.name in kwargs:
                value = kwargs[param.name]

                if param.type == "string" and not isinstance(value, str):
                    return (
                        f"Parameter '{param.name}' should be string, got {type(value)}"
                    )
                elif param.type == "number" and not isinstance(value, (int, float)):
                    return (
                        f"Parameter '{param.name}' should be number, got {type(value)}"
                    )
                elif param.type == "boolean" and not isinstance(value, bool):
                    return (
                        f"Parameter '{param.name}' should be boolean, got {type(value)}"
                    )

                # 枚举验证
                if param.enum and value not in param.enum:
                    return f"Parameter '{param.name}' must be one of: {param.enum}"

        return None

    async def execute_batch(
        self, calls: List[Dict[str, Any]], parallel: bool = False
    ) -> List[ToolResult]:
        """
        批量执行工具调用

        Args:
            calls: 工具调用列表 [{"tool_name": "xxx", "params": {...}}]
            parallel: 是否并行执行

        Returns:
            执行结果列表
        """
        if parallel:
            # 并行执行
            tasks = [
                self.execute(call["tool_name"], **call.get("params", {}))
                for call in calls
            ]
            return await asyncio.gather(*tasks)
        else:
            # 串行执行
            results = []
            for call in calls:
                result = await self.execute(call["tool_name"], **call.get("params", {}))
                results.append(result)
            return results


# 全局注册表实例
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def reset_tool_registry():
    """重置工具注册表（用于测试）"""
    global _tool_registry
    _tool_registry = None
