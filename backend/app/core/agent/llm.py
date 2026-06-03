"""
LLM 统一接口模块

支持多种 LLM 提供商（DeepSeek、OpenAI、本地模型等）
通过 OpenAI 兼容 SDK 调用 DeepSeek API
"""

from typing import Optional, List, Dict, Any, cast
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
import logging
import json

from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """消息角色"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """对话消息"""

    role: MessageRole
    content: str
    name: Optional[str] = None  # 工具名称（当 role=tool 时）
    tool_call_id: Optional[str] = None

    def to_param(self) -> ChatCompletionMessageParam:
        """转为 OpenAI SDK 要求的 ChatCompletionMessageParam。"""
        if self.role == MessageRole.SYSTEM:
            return {"role": "system", "content": self.content}
        if self.role == MessageRole.USER:
            param: ChatCompletionMessageParam = {
                "role": "user",
                "content": self.content,
            }
            if self.name:
                param = cast(
                    ChatCompletionMessageParam,
                    {**param, "name": self.name},
                )
            return param
        if self.role == MessageRole.ASSISTANT:
            param = {"role": "assistant", "content": self.content}
            if self.name:
                param = cast(
                    ChatCompletionMessageParam,
                    {**param, "name": self.name},
                )
            return param
        # tool
        return {
            "role": "tool",
            "content": self.content,
            "tool_call_id": self.tool_call_id or "",
        }


@dataclass
class LLMResponse:
    """LLM 响应"""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class BaseLLM:
    """LLM 基类"""

    async def invoke(self, messages: List[Message]) -> LLMResponse:
        """非流式调用"""
        raise NotImplementedError

    async def stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """流式调用（子类需使用 async yield 实现）"""
        raise NotImplementedError
        yield ""  # 使本方法成为 async generator，与实现类签名一致

    async def ainvoke(self, prompt: str) -> LLMResponse:
        """简化的异步调用（接受字符串提示词）"""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return await self.invoke(messages)


class DeepSeekLLM(BaseLLM):
    """DeepSeek LLM 客户端（OpenAI 兼容 SDK）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = base_url or settings.deepseek_base_url
        self.model = model or settings.deepseek_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        if not self.api_key:
            logger.warning("DeepSeek API key not set!")

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (APIStatusError, APITimeoutError, RateLimitError)
        ),
    )
    async def _chat_create(self, messages: List[ChatCompletionMessageParam]):
        """非流式 Chat Completions（与 DeepSeek 官方示例一致）"""
        return await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
        )

    @staticmethod
    def _to_api_messages(messages: List[Message]) -> List[ChatCompletionMessageParam]:
        return [m.to_param() for m in messages]

    async def invoke(self, messages: List[Message]) -> LLMResponse:
        """非流式调用"""
        api_messages = self._to_api_messages(messages)

        try:
            response = await self._chat_create(api_messages)
            choice = response.choices[0]
            message = choice.message

            tool_calls: List[Dict[str, Any]] = []
            if message.tool_calls:
                tool_calls = [tc.model_dump() for tc in message.tool_calls]

            usage: Dict[str, int] = {}
            if response.usage:
                usage = {
                    k: v
                    for k, v in response.usage.model_dump().items()
                    if isinstance(v, int)
                }

            return LLMResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "stop",
                usage=usage,
            )
        except Exception as e:
            logger.error(f"LLM invoke failed: {e}")
            raise

    async def stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """流式调用"""
        api_messages = self._to_api_messages(messages)

        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise

    async def ainvoke(self, prompt: str) -> LLMResponse:
        """简化的异步调用"""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return await self.invoke(messages)


class MockLLM(BaseLLM):
    """Mock LLM，用于测试和开发"""

    async def invoke(self, messages: List[Message]) -> LLMResponse:
        """返回模拟响应"""
        last_message = messages[-1].content

        if "标签" in last_message or "关键词" in last_message:
            content = "AI, 编程, 知识管理"
        elif "摘要" in last_message:
            content = "这是一个关于智能知识库的测试摘要。"
        elif "计划" in last_message:
            content = json.dumps(
                {
                    "intent": "整理知识",
                    "plan": ["检索相关笔记", "聚类分析", "生成摘要"],
                    "reasoning": "用户需要整理零散笔记",
                }
            )
        else:
            content = f"收到消息: {last_message[:100]}..."

        return LLMResponse(content=content, usage={"total_tokens": 100})

    async def stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """模拟流式输出"""
        import asyncio

        response = await self.invoke(messages)
        for char in response.content:
            yield char
            await asyncio.sleep(0.01)


# 全局 LLM 实例
_llm_instance: Optional[BaseLLM] = None


_llm_fast_instance: Optional[BaseLLM] = None


def get_llm(use_mock: bool = False, *, fast: bool = False) -> BaseLLM:
    """
    获取 LLM 实例（单例模式）

    Args:
        use_mock: 是否使用 Mock 模式（用于测试）
        fast: 对话快速路径（更小 max_tokens、更短超时）

    Returns:
        LLM 实例
    """
    global _llm_instance, _llm_fast_instance

    if fast:
        if _llm_fast_instance is None:
            if use_mock or not settings.deepseek_api_key:
                _llm_fast_instance = MockLLM()
            else:
                _llm_fast_instance = DeepSeekLLM(
                    max_tokens=1536,
                    temperature=0.6,
                    timeout=45.0,
                )
        return _llm_fast_instance

    if _llm_instance is None:
        if use_mock or not settings.deepseek_api_key:
            logger.info("Using MockLLM (no API key or mock mode)")
            _llm_instance = MockLLM()
        else:
            logger.info(f"Using DeepSeekLLM with model: {settings.deepseek_model}")
            _llm_instance = DeepSeekLLM()

    return _llm_instance


def reset_llm():
    """重置 LLM 实例（用于测试）"""
    global _llm_instance, _llm_fast_instance
    _llm_instance = None
    _llm_fast_instance = None
