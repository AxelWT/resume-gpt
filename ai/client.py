"""
AI 客户端模块

封装了对 OpenAI 兼容 API 的调用，支持任意兼容 OpenAI 接口的模型服务商
（如 OpenAI、DeepSeek、Moonshot、本地部署的 Ollama 等）。
提供文本聊天和 JSON 格式响应两种调用方式。
"""

import json
import re
from typing import AsyncGenerator, Optional

import httpx


class RequestTimeoutError(Exception):
    """AI 请求超时异常"""
    pass


class AIClient:
    """
    OpenAI 兼容 API 的异步客户端。

    使用 httpx.AsyncClient 发起 HTTP 请求，支持：
    - test(): 测试连接和认证是否正常
    - chat(): 发送消息并获取文本回复
    - chat_json(): 发送消息并获取 JSON 格式的回复（自动解析，支持截断修复和重试）
    """

    def __init__(self, base_url: str, api_key: str, model_name: str):
        """
        初始化 AI 客户端。

        Args:
            base_url: API 基础地址，如 "https://api.openai.com/v1"
            api_key: API 密钥，用于 Bearer Token 认证
            model_name: 模型名称，如 "gpt-4o"、"deepseek-chat"
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.chat_url = f"{self.base_url}/chat/completions"
        # 创建异步 HTTP 客户端，设置 120 秒超时（AI 响应可能较慢）并自动跟随重定向
        self._client = httpx.AsyncClient(timeout=120, follow_redirects=True)

    def _headers(self) -> dict:
        """构造请求头，包含 JSON 内容类型和 Bearer Token 认证"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def test(self) -> bool:
        """
        测试 API 配置是否可用。
        发送一条简短消息来验证 API Key 和模型名是否正确。

        Returns:
            True 表示连接成功

        Raises:
            ValueError: API Key 无效（401）或模型不可用（404）
            httpx.HTTPStatusError: 其他 HTTP 错误
        """
        try:
            resp = await self._client.post(
                self.chat_url,
                headers=self._headers(),
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10,  # 只请求少量 token，节省费用
                },
            )
        except httpx.TimeoutException:
            raise RequestTimeoutError("连接 AI 服务超时，请检查网络或稍后重试")
        # 针对常见错误码给出友好的中文提示
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 404:
            raise ValueError(f"模型 '{self.model_name}' 不可用，请检查")
        resp.raise_for_status()
        return True

    async def _send(self, messages: list[dict], **kwargs) -> tuple[str, str]:
        """
        发送聊天请求并返回内容与结束原因。

        Returns:
            (content, finish_reason) 元组
            finish_reason 常见值: "stop"(正常结束), "length"(达到 max_tokens 截断)
        """
        body = {
            "model": self.model_name,
            "messages": messages,
            **kwargs,
        }
        try:
            resp = await self._client.post(
                self.chat_url,
                headers=self._headers(),
                json=body,
            )
        except httpx.TimeoutException:
            raise RequestTimeoutError("AI 响应超时，请检查网络或稍后重试")
        # 处理常见错误状态码
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 429:
            raise ValueError("请求过于频繁，请稍后重试")
        resp.raise_for_status()
        # 从 OpenAI 兼容的响应格式中提取回复文本
        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason", "stop")
        return content, finish_reason

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """
        发送聊天消息并获取 AI 的文本回复。

        Args:
            messages: OpenAI 格式的消息列表，如 [{"role": "user", "content": "..."}]
            **kwargs: 额外的请求参数，如 temperature、max_tokens 等

        Returns:
            AI 回复的文本内容
        """
        content, _ = await self._send(messages, **kwargs)
        return content

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """
        尝试修复被截断的 JSON 字符串。

        策略：
            1. 跟踪字符串边界，找到所有"安全截断点"
            2. 安全截断点：完整的 key:value 对结尾（值后面跟 , } ] 或文本末尾）
            3. 从最后一个安全截断点截断
            4. 用栈跟踪开括号顺序，按正确嵌套关系补全闭合括号
        """
        in_string = False
        escape_next = False
        safe_positions = []
        bracket_stack = []

        i = 0
        while i < len(text):
            ch = text[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if in_string:
                if ch == "\\":
                    escape_next = True
                elif ch == '"':
                    in_string = False
                i += 1
                continue
            if ch == '"':
                in_string = True
                i += 1
                continue
            if ch in "{[":
                bracket_stack.append(ch)
            elif ch == "}" and bracket_stack and bracket_stack[-1] == "{":
                bracket_stack.pop()
                safe_positions.append(i + 1)
            elif ch == "]" and bracket_stack and bracket_stack[-1] == "[":
                bracket_stack.pop()
                safe_positions.append(i + 1)
            elif ch == ",":
                safe_positions.append(i)
            i += 1

        if not safe_positions:
            return text

        cut = safe_positions[-1]
        trimmed = text[:cut].rstrip().rstrip(",").rstrip()

        closing = []
        for ch in reversed(bracket_stack):
            closing.append("}" if ch == "{" else "]")
        trimmed += "".join(closing)
        return trimmed

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """剥离 markdown 代码块包裹"""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        return text.strip()

    @staticmethod
    def _clean_trailing_commas(text: str) -> str:
        """移除 JSON 中不合法的尾部逗号"""
        return re.sub(r",\s*([}\]])", r"\1", text)

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """
        发送聊天消息并获取 JSON 格式的回复。

        容错策略（按优先级）：
            1. 直接解析 AI 返回的文本为 JSON
            2. 剥离 markdown 代码块后解析
            3. 清理尾部逗号后解析
            4. 如果 finish_reason == "length"（输出被截断），发送 continue 消息重试拼接
            5. 尝试修复截断 JSON（补全缺失的括号）

        Args:
            messages: OpenAI 格式的消息列表
            **kwargs: 额外的请求参数，max_tokens 默认 8192

        Returns:
            解析后的 Python 字典

        Raises:
            json.JSONDecodeError: 所有修复策略均失败
        """
        kwargs.setdefault("max_tokens", 8192)

        content, finish_reason = await self._send(messages, **kwargs)
        text = self._strip_markdown(content)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        cleaned = self._clean_trailing_commas(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        if finish_reason == "length":
            continuation = await self._retry_with_continue(messages, content, **kwargs)
            if continuation is not None:
                return continuation

        repaired = self._repair_truncated_json(cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        raise json.JSONDecodeError(
            f"AI 返回内容无法解析为 JSON，原始内容: {text[:200]}",
            text,
            0,
        )

    async def _retry_with_continue(
        self, original_messages: list[dict], partial_content: str, **kwargs
    ) -> Optional[dict]:
        """
        当 AI 输出因 max_tokens 截断时，发送 continue 消息让模型补全剩余内容，
        拼接后尝试解析 JSON。

        Returns:
            解析成功的字典，或 None（拼接后仍无法解析）
        """
        continue_messages = list(original_messages) + [
            {"role": "assistant", "content": partial_content},
            {
                "role": "user",
                "content": "请继续输出，从中断处接着输出，不要重复已有内容。",
            },
        ]
        try:
            continuation, _ = await self._send(continue_messages, **kwargs)
        except Exception:
            return None

        full_text = partial_content.rstrip() + continuation
        full_text = self._strip_markdown(full_text)

        try:
            return json.loads(full_text)
        except json.JSONDecodeError:
            pass

        cleaned = self._clean_trailing_commas(full_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        repaired = self._repair_truncated_json(cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None

    async def close(self):
        """关闭底层 HTTP 客户端，释放连接池资源"""
        await self._client.aclose()
