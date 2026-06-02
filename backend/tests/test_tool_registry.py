"""工具注册表测试"""

import pytest  # pyright: ignore[reportMissingImports]
from app.core.agent.tools.registry import ToolRegistry, RateLimiter, RetryStrategy
from app.core.agent.tools.base import BaseTool, ToolResult, ToolStatus, ToolParameter


class MockTool(BaseTool):
    """模拟工具"""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "模拟测试工具"

    @property
    def parameters(self):
        return [
            ToolParameter(
                name="message", type="string", description="测试消息", required=True
            ),
            ToolParameter(
                name="should_fail",
                type="boolean",
                description="是否失败",
                required=False,
                default=False,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        if kwargs.get("should_fail"):
            raise RuntimeError("Mock failure")

        return ToolResult(
            status=ToolStatus.SUCCESS, data={"echo": kwargs.get("message", "")}
        )


class TestToolRegistry:
    """工具注册表测试"""

    def setup_method(self):
        self.registry = ToolRegistry()
        self.tool = MockTool()

    def test_register_tool(self):
        """测试注册工具"""
        self.registry.register(self.tool)

        assert self.registry.get_tool("mock_tool") is not None
        assert len(self.registry.list_tools()) == 1

    def test_unregister_tool(self):
        """测试注销工具"""
        self.registry.register(self.tool)
        self.registry.unregister("mock_tool")

        assert self.registry.get_tool("mock_tool") is None

    def test_list_tools(self):
        """测试列出工具"""
        self.registry.register(self.tool)
        tools = self.registry.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "mock_tool"
        assert "description" in tools[0]

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """测试成功执行"""
        self.registry.register(self.tool)
        result = await self.registry.execute("mock_tool", message="Hello")

        assert result.status == ToolStatus.SUCCESS
        assert result.data["echo"] == "Hello"

    @pytest.mark.asyncio
    async def test_execute_missing_required_param(self):
        """测试缺少必需参数"""
        self.registry.register(self.tool)
        result = await self.registry.execute("mock_tool")

        assert result.status == ToolStatus.FAILED
        assert result.error is not None
        assert "Missing required parameter" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """测试工具不存在"""
        result = await self.registry.execute("nonexistent_tool")

        assert result.status == ToolStatus.FAILED
        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        """测试带重试的执行"""
        self.registry.register(self.tool, retry_config={"max_retries": 2})

        result = await self.registry.execute(
            "mock_tool", message="test", should_fail=True
        )

        assert result.status == ToolStatus.FAILED
        assert result.error is not None
        assert "failed after" in result.error

    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        """测试限流器"""
        limiter = RateLimiter(rate=1, per=1.0)

        # 第一次应该成功
        assert await limiter.acquire() is True

        # 第二次应该等待（在异步环境中测试）
        # 这里简化测试
        assert limiter.tokens < 1


class TestRetryStrategy:
    """重试策略测试"""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """测试失败重试"""
        attempt = 0

        async def failing_func():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError("Temporary failure")
            return "success"

        strategy = RetryStrategy(max_retries=3, initial_delay=0.1)
        result = await strategy.execute_with_retry(failing_func)

        assert result == "success"
        assert attempt == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""

        async def always_fail():
            raise ValueError("Always fails")

        strategy = RetryStrategy(max_retries=2, initial_delay=0.1)

        with pytest.raises(ValueError):
            await strategy.execute_with_retry(always_fail)


class TestRateLimiter:
    """限流器测试"""

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """测试获取令牌"""
        limiter = RateLimiter(rate=10, per=1.0)

        # 应该能获取多个令牌
        for _ in range(5):
            assert await limiter.acquire() is True

    @pytest.mark.asyncio
    async def test_rate_limiter_exhaustion(self):
        """测试令牌耗尽"""
        limiter = RateLimiter(rate=2, per=1.0)

        # 获取 2 个令牌
        assert await limiter.acquire() is True
        assert await limiter.acquire() is True

        # 第 3 个应该等待（但这里不测试等待）
        assert limiter.tokens < 1
